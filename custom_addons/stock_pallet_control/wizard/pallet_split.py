# -*- coding: utf-8 -*-
import math

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_compare

MAX_PALLETS = 500


class PalletSplit(models.TransientModel):
    """Reparte las líneas de una recepción en tarimas: un paquete por tarima.

    No crea documentos nuevos: trabaja sobre la recepción que generó la orden de compra.
    Después se valida la recepción como siempre e imprimen las etiquetas.
    """
    _name = 'stock.pallet.split'
    _description = 'Separar recepción en tarimas'

    def _default_package_type(self):
        return self.env.ref('stock_pallet_control.package_type_tarima', raise_if_not_found=False)

    picking_id = fields.Many2one('stock.picking', 'Recepción', required=True, readonly=True)
    package_type_id = fields.Many2one(
        'stock.package.type', 'Tipo de paquete', required=True, default=_default_package_type)
    line_ids = fields.One2many('stock.pallet.split.line', 'wizard_id', 'Productos')
    pallet_count = fields.Integer('Tarimas a crear', compute='_compute_pallet_count')

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        picking = self.env['stock.picking'].browse(res.get('picking_id'))
        if picking and 'line_ids' in fields_list:
            res['line_ids'] = [Command.create({
                'move_line_id': ml.id,
                'quantity': ml.quantity,
                'lot_name': ml.lot_id.name or ml.lot_name or False,
                'qty_per_pallet': ml.quantity,
            }) for ml in picking.move_line_ids.filtered(
                lambda ml: not ml.result_package_id and ml.quantity > 0)]
        return res

    @api.depends('line_ids.pallet_count')
    def _compute_pallet_count(self):
        for wizard in self:
            wizard.pallet_count = sum(wizard.line_ids.mapped('pallet_count'))

    def _check(self):
        self.ensure_one()
        picking = self.picking_id
        if picking.picking_type_code != 'incoming' or picking.state != 'assigned':
            raise UserError(_('La recepción debe estar en estado "Listo".'))
        if not self.line_ids:
            raise UserError(_('No hay productos pendientes de poner en tarima en esta recepción.'))
        if self.pallet_count > MAX_PALLETS:
            raise UserError(_('Máximo %(max)s tarimas por vez (serían %(count)s).',
                              max=MAX_PALLETS, count=self.pallet_count))
        for line in self.line_ids:
            product = line.product_id
            if line.quantity <= 0 or line.qty_per_pallet <= 0:
                raise UserError(_('Las cantidades de %s deben ser mayores que cero.', product.display_name))
            if product.tracking == 'serial':
                raise UserError(_(
                    '%s usa números de serie; ponlo en tarima con "Poner en paquete".',
                    product.display_name))
            if product.tracking == 'lot' and not line.lot_name:
                raise UserError(_('Captura el lote de %s.', product.display_name))

    def action_split(self):
        self.ensure_one()
        self._check()
        picking = self.picking_id
        origin = picking.origin or picking.name
        total = self.pallet_count
        index = 0
        MoveLine = self.env['stock.move.line']
        for line in self.line_ids:
            ml = line.move_line_id
            rounding = ml.product_uom_id.rounding
            remaining = line.quantity
            # Lote: si ya existe con ese nombre en la línea, se respeta; si no, Odoo lo crea al validar.
            lot_vals = ({'lot_id': ml.lot_id.id, 'lot_name': False}
                        if ml.lot_id and ml.lot_id.name == line.lot_name
                        else {'lot_id': False, 'lot_name': line.lot_name or False})
            chunks = []
            while float_compare(remaining, 0, precision_rounding=rounding) > 0:
                chunk = min(line.qty_per_pallet, remaining)
                chunks.append(chunk)
                remaining -= chunk
            for position, chunk in enumerate(chunks):
                index += 1
                package = self.env['stock.quant.package'].create({
                    'package_type_id': self.package_type_id.id,
                    'pallet_index': index,
                    'pallet_total': total,
                    'pallet_origin': origin,
                })
                vals = dict(lot_vals, quantity=chunk, result_package_id=package.id, picked=True)
                if position == 0:
                    ml.write(vals)
                else:
                    ml.copy(dict(vals, move_id=ml.move_id.id, picking_id=picking.id))
            # Si se capturó menos de lo pedido, al validar Odoo ofrece la entrega parcial (backorder).
        return {'type': 'ir.actions.act_window_close'}


class PalletSplitLine(models.TransientModel):
    _name = 'stock.pallet.split.line'
    _description = 'Producto a separar en tarimas'

    wizard_id = fields.Many2one('stock.pallet.split', required=True, ondelete='cascade')
    move_line_id = fields.Many2one('stock.move.line', required=True, readonly=True)
    product_id = fields.Many2one(related='move_line_id.product_id', string='Producto')
    tracking = fields.Selection(related='move_line_id.product_id.tracking')
    uom_name = fields.Char(related='move_line_id.product_uom_id.name', string='Unidad')
    lot_name = fields.Char('Lote')
    quantity = fields.Float('Cantidad recibida', digits='Product Unit of Measure', required=True)
    qty_per_pallet = fields.Float('Cantidad por tarima', digits='Product Unit of Measure', required=True)
    pallet_count = fields.Integer('Tarimas', compute='_compute_pallet_count')

    @api.depends('quantity', 'qty_per_pallet')
    def _compute_pallet_count(self):
        for line in self:
            if line.quantity > 0 and line.qty_per_pallet > 0:
                line.pallet_count = math.ceil(round(line.quantity / line.qty_per_pallet, 6))
            else:
                line.pallet_count = 0
