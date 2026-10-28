# -*- coding: utf-8 -*-
from odoo import Command, _, api, fields, models
from odoo.exceptions import UserError, ValidationError

MAX_PALLETS = 200


class PalletReceive(models.TransientModel):
    _name = 'stock.pallet.receive'
    _description = 'Recibir tarimas'

    def _default_warehouse(self):
        return self.env['stock.warehouse'].search(
            [('company_id', '=', self.env.company.id)], limit=1)

    def _default_package_type(self):
        return self.env.ref('stock_pallet_control.package_type_tarima', raise_if_not_found=False)

    state = fields.Selection([('draft', 'Captura'), ('done', 'Registrada')], default='draft')
    warehouse_id = fields.Many2one(
        'stock.warehouse', 'Almacén', required=True, default=_default_warehouse)
    owner_id = fields.Many2one(
        'res.partner', 'Propietario de la mercancía',
        help='Compañía dueña de la mercancía. Déjalo vacío si el inventario es propio.')
    partner_id = fields.Many2one(
        'res.partner', 'Remitente / proveedor',
        help='Quien entrega la mercancía. Si se deja vacío se usa el propietario.')
    origin = fields.Char('Referencia', help='Remisión, folio o documento de origen.')
    package_type_id = fields.Many2one(
        'stock.package.type', 'Tipo de paquete', required=True, default=_default_package_type)
    pallet_count = fields.Integer(
        'No. de tarimas iguales', default=1,
        help='Si llegan varias tarimas con el mismo contenido, captúralo una vez y '
             'Odoo crea una etiqueta y una ubicación por cada una.')
    location_dest_id = fields.Many2one(
        'stock.location', 'Ubicación (opcional)',
        domain="[('usage', '=', 'internal')]",
        help='Déjalo vacío para que Odoo asigne la primera ubicación libre.')
    line_ids = fields.One2many('stock.pallet.receive.line', 'wizard_id', 'Contenido de cada tarima')

    picking_id = fields.Many2one('stock.picking', 'Recepción', readonly=True)
    package_ids = fields.Many2many('stock.quant.package', string='Tarimas registradas', readonly=True)
    note = fields.Char('Aviso', readonly=True)

    @api.depends('state')
    def _compute_display_name(self):
        for wizard in self:
            wizard.display_name = _('Recibir tarimas')

    # ------------------------------------------------------------------ helpers
    def _check_data(self):
        self.ensure_one()
        if not self.line_ids:
            raise UserError(_('Agrega al menos un producto al contenido de la tarima.'))
        if not 1 <= self.pallet_count <= MAX_PALLETS:
            raise UserError(_('El número de tarimas debe estar entre 1 y %s.', MAX_PALLETS))
        if self.location_dest_id and self.pallet_count > 1:
            raise UserError(_(
                'Para recibir varias tarimas deja la ubicación vacía; '
                'Odoo asigna una ubicación libre distinta a cada una.'))
        for line in self.line_ids:
            product = line.product_id
            if line.quantity <= 0:
                raise UserError(_('La cantidad de %s debe ser mayor que cero.', product.display_name))
            if not product.is_storable:
                raise UserError(_(
                    '%s no es un producto almacenable, por eso Odoo no llevaría su inventario. '
                    'Márcalo como "Rastrear inventario" en su ficha.', product.display_name))
            if product.tracking == 'serial':
                raise UserError(_(
                    '%s usa números de serie; este asistente maneja productos sin rastreo o por lote.',
                    product.display_name))
            if product.tracking == 'lot' and not line.lot_name:
                raise UserError(_('Captura el lote de %s.', product.display_name))

    def _putaway_location(self, stock_location, move_lines, package):
        """Ubicación libre para la tarima según las reglas de ubicación."""
        category = self.env.ref('stock_pallet_control.storage_category_tarima', raise_if_not_found=False)
        candidates = stock_location.child_internal_location_ids.filtered(
            lambda loc: category and loc.storage_category_id == category)
        destination = stock_location.with_context(
            products=move_lines.product_id,
            exclude_sml_ids=set(move_lines.ids),
        )._get_putaway_strategy(self.env['product.product'], package=package)
        if candidates and destination not in candidates:
            raise UserError(_(
                'No hay ubicaciones libres para más tarimas (%s ubicaciones con capacidad de tarima, '
                'todas ocupadas o apartadas). Libera espacio o genera más ubicaciones.',
                len(candidates)))
        return destination

    def _reload_action(self):
        return {
            'type': 'ir.actions.act_window',
            'res_model': self._name,
            'res_id': self.id,
            'view_mode': 'form',
            'target': 'current',
        }

    # ------------------------------------------------------------------ actions
    def action_confirm(self):
        self.ensure_one()
        self._check_data()
        warehouse = self.warehouse_id
        picking_type = warehouse.in_type_id
        stock_location = warehouse.lot_stock_id
        source_location = (picking_type.default_location_src_id
                           or self.env.ref('stock.stock_location_suppliers'))
        partner = self.partner_id or self.owner_id

        picking = self.env['stock.picking'].create({
            'picking_type_id': picking_type.id,
            'partner_id': partner.id or False,
            'owner_id': self.owner_id.id or False,
            'origin': self.origin or False,
            'location_id': source_location.id,
            'location_dest_id': stock_location.id,
        })
        moves = {}
        for line in self.line_ids:
            moves[line.id] = self.env['stock.move'].create({
                'name': line.product_id.display_name,
                'picking_id': picking.id,
                'product_id': line.product_id.id,
                'product_uom_qty': line.quantity * self.pallet_count,
                'product_uom': line.product_id.uom_id.id,
                'location_id': source_location.id,
                'location_dest_id': stock_location.id,
            })
        picking.action_confirm()
        # Odoo propone una línea por producto; la reemplazamos por una línea por tarima.
        picking.move_line_ids.unlink()

        packages = self.env['stock.quant.package']
        for _index in range(self.pallet_count):
            package = self.env['stock.quant.package'].create({
                'package_type_id': self.package_type_id.id,
            })
            packages |= package
            move_lines = self.env['stock.move.line']
            for line in self.line_ids:
                vals = moves[line.id]._prepare_move_line_vals(quantity=line.quantity)
                vals.update({
                    'result_package_id': package.id,
                    'lot_name': line.lot_name or False,
                    'picked': True,
                })
                move_lines |= self.env['stock.move.line'].create(vals)
            destination = self.location_dest_id or self._putaway_location(
                stock_location, move_lines, package)
            move_lines.write({'location_dest_id': destination.id})

        result = picking.with_context(skip_sms=True, skip_backorder=True).button_validate()
        if result is not True:
            raise UserError(_(
                'Odoo no pudo validar la recepción %s automáticamente. Ábrela y revísala.',
                picking.name))

        note = False
        if all(package.location_id == stock_location for package in packages):
            note = _('Las tarimas quedaron en %s porque no hay ubicaciones con categoría '
                     '"Tarima" creadas. Usa Tarimas > Generar ubicaciones.', stock_location.display_name)
        self.write({
            'state': 'done',
            'picking_id': picking.id,
            'package_ids': [Command.set(packages.ids)],
            'note': note,
        })
        return self._reload_action()

    def action_print_labels(self):
        self.ensure_one()
        return self.package_ids.action_print_pallet_label()

    def action_open_picking(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'stock.picking',
            'res_id': self.picking_id.id,
            'view_mode': 'form',
        }

    def action_new(self):
        return self.env['ir.actions.act_window']._for_xml_id(
            'stock_pallet_control.action_pallet_receive')


class PalletReceiveLine(models.TransientModel):
    _name = 'stock.pallet.receive.line'
    _description = 'Contenido de la tarima a recibir'

    wizard_id = fields.Many2one('stock.pallet.receive', required=True, ondelete='cascade')
    product_id = fields.Many2one(
        'product.product', 'Producto', required=True,
        domain="[('is_storable', '=', True)]")
    tracking = fields.Selection(related='product_id.tracking')
    quantity = fields.Float('Cantidad por tarima', required=True, default=1.0,
                            digits='Product Unit of Measure')
    product_uom_name = fields.Char(related='product_id.uom_id.name', string='Unidad')
    lot_name = fields.Char('Lote')

    @api.constrains('quantity')
    def _check_quantity(self):
        for line in self:
            if line.quantity <= 0:
                raise ValidationError(_('La cantidad debe ser mayor que cero.'))
