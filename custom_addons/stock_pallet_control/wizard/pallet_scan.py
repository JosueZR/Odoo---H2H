# -*- coding: utf-8 -*-
from collections import defaultdict

from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError


class PalletScan(models.TransientModel):
    _name = 'stock.pallet.scan'
    _inherit = ['barcodes.barcode_events_mixin']
    _description = 'Escáner de tarimas'

    mode = fields.Selection(
        [('exit', 'Salida de tarimas'), ('move', 'Cambio de ubicación')],
        string='Operación', required=True, default='exit')
    state = fields.Selection([('draft', 'Escaneando'), ('done', 'Registrada')], default='draft')
    package_ids = fields.Many2many(
        'stock.quant.package', 'stock_pallet_scan_package_rel', 'scan_id', 'package_id',
        string='Tarimas escaneadas')
    location_dest_id = fields.Many2one(
        'stock.location', 'Ubicación destino', domain="[('usage', '=', 'internal')]")
    partner_id = fields.Many2one(
        'res.partner', 'Cliente / destino',
        help='A quién se entregan las tarimas. Si se deja vacío van a la ubicación genérica de clientes.')
    origin = fields.Char('Referencia', help='Pedido, remisión o folio de la salida.')
    scan_input = fields.Char(
        'Escribir código', store=False,
        help='Alternativa al lector: escribe el código de la tarima o ubicación y presiona Enter.')
    last_scan = fields.Char('Último escaneo', readonly=True)
    last_scan_ok = fields.Boolean(readonly=True)
    picking_ids = fields.Many2many(
        'stock.picking', 'stock_pallet_scan_picking_rel', 'scan_id', 'picking_id',
        string='Operaciones generadas', readonly=True)

    @api.depends('mode')
    def _compute_display_name(self):
        for wizard in self:
            wizard.display_name = _('Escáner de tarimas')

    # ------------------------------------------------------------------ escaneo
    def _set_result(self, ok, message):
        self.last_scan_ok = ok
        self.last_scan = message

    @api.onchange('scan_input')
    def _onchange_scan_input(self):
        code = self.scan_input
        if code:
            self.scan_input = False
            return self.on_barcode_scanned(code)

    def on_barcode_scanned(self, barcode):
        barcode = (barcode or '').strip()
        if not barcode or self.state == 'done':
            return
        package = self.env['stock.quant.package'].search([('name', '=', barcode)], limit=1)
        if package:
            return self._scan_package(package)
        location = self.env['stock.location'].search(
            [('barcode', '=', barcode), ('usage', '=', 'internal')], limit=1)
        if location:
            return self._scan_location(location)
        self._set_result(False, _('Código no reconocido: %s', barcode))

    def _scan_package(self, package):
        if package in self.package_ids:
            self._set_result(False, _('La tarima %s ya estaba en la lista.', package.name))
            return
        quants = package.quant_ids.filtered(
            lambda q: q.quantity > 0 and q.location_id.usage == 'internal')
        if not quants:
            self._set_result(False, _(
                'La tarima %s no tiene existencias en el almacén (¿ya salió o no se ha recibido?).',
                package.name))
            return
        self.package_ids = [Command.link(package.id)]
        self._set_result(True, _('Tarima %(name)s agregada: %(content)s en %(location)s.',
                                 name=package.name,
                                 content=package.pallet_content,
                                 location=package.location_id.display_name))

    def _scan_location(self, location):
        if self.mode != 'move':
            self._set_result(False, _(
                'En "Salida" solo se escanean tarimas. Cambia a "Cambio de ubicación" para escanear un lugar.'))
            return
        self.location_dest_id = location
        self._set_result(True, _('Ubicación destino: %s.', location.display_name))

    # ------------------------------------------------------------------ confirmación
    def _check_destination_capacity(self, packages, destination):
        category = destination.storage_category_id
        if not category:
            return
        for package_type in packages.package_type_id:
            capacity = category.package_capacity_ids.filtered(
                lambda c: c.package_type_id == package_type)[:1]
            moving = len(packages.filtered(lambda p: p.package_type_id == package_type))
            occupied = len(destination.quant_ids.filtered(
                lambda q: q.quantity > 0 and q.package_id.package_type_id == package_type
            ).package_id - packages)
            if capacity and occupied + moving > capacity.quantity:
                raise UserError(_(
                    'La ubicación %(location)s no tiene espacio: capacidad %(cap)g, ocupada por %(occ)s.',
                    location=destination.display_name, cap=capacity.quantity, occ=occupied))

    def _groups(self):
        groups = defaultdict(lambda: self.env['stock.quant.package'])
        for package in self.package_ids:
            quants = package.quant_ids.filtered(
                lambda q: q.quantity > 0 and q.location_id.usage == 'internal')
            if not quants:
                raise UserError(_('La tarima %s ya no tiene existencias en el almacén.', package.name))
            owners = quants.owner_id
            if len(owners) > 1:
                raise UserError(_(
                    'La tarima %s mezcla mercancía de varios propietarios; sepárala antes de moverla.',
                    package.name))
            warehouse = package.location_id.warehouse_id
            if not warehouse:
                raise UserError(_('No se pudo determinar el almacén de la tarima %s.', package.name))
            groups[(warehouse, owners[:1])] |= package
        return groups

    def _create_picking(self, warehouse, owner, packages):
        if self.mode == 'exit':
            picking_type = warehouse.out_type_id
            destination = (self.partner_id.property_stock_customer
                           or self.env.ref('stock.stock_location_customers'))
        else:
            picking_type = warehouse.int_type_id
            destination = self.location_dest_id
        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'partner_id': self.partner_id.id or False,
            'owner_id': owner.id or False,
            'origin': self.origin or False,
            'location_id': warehouse.lot_stock_id.id,
            'location_dest_id': destination.id,
        })
        for package in packages:
            self.env['stock.package_level'].create({
                'package_id': package.id,
                'picking_id': picking.id,
                'location_dest_id': destination.id,
                'company_id': picking.company_id.id,
            })
        picking.action_confirm()
        picking.action_assign()
        unavailable = picking.package_level_ids.filtered(lambda pl: pl.state != 'assigned')
        if unavailable:
            raise UserError(_(
                'No se pudo apartar la(s) tarima(s) %s: probablemente están reservadas en otra '
                'operación pendiente.', ', '.join(unavailable.package_id.mapped('name'))))
        picking.package_level_ids.write({'is_done': True})
        result = picking.with_context(skip_sms=True, skip_backorder=True).button_validate()
        if result is not True:
            raise UserError(_(
                'Odoo no pudo validar %s automáticamente. Ábrela y revísala.', picking.name))
        return picking

    def action_confirm(self):
        self.ensure_one()
        if not self.package_ids:
            raise UserError(_('Escanea al menos una tarima.'))
        if self.mode == 'move':
            if not self.location_dest_id:
                raise UserError(_('Escanea la etiqueta de la ubicación destino.'))
            self._check_destination_capacity(self.package_ids, self.location_dest_id)
        pickings = self.env['stock.picking']
        for (warehouse, owner), packages in self._groups().items():
            if self.mode == 'move' and self.location_dest_id.warehouse_id != warehouse:
                raise UserError(_('La ubicación destino pertenece a otro almacén.'))
            pickings |= self._create_picking(warehouse, owner, packages)
        self.write({
            'state': 'done',
            'picking_ids': [Command.set(pickings.ids)],
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_clear(self):
        self.ensure_one()
        self.write({
            'package_ids': [Command.clear()],
            'location_dest_id': False,
            'last_scan': False,
        })
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def action_new(self):
        return self.env['ir.actions.act_window']._for_xml_id(
            'stock_pallet_control.action_pallet_scan')
