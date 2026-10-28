# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError

MAX_LOCATIONS = 500


class PalletLocationGenerator(models.TransientModel):
    _name = 'stock.pallet.location.generator'
    _description = 'Generar ubicaciones para tarimas'

    def _default_parent(self):
        return self.env.ref('stock.stock_location_stock', raise_if_not_found=False)

    def _default_category(self):
        return self.env.ref('stock_pallet_control.storage_category_tarima', raise_if_not_found=False)

    parent_id = fields.Many2one(
        'stock.location', 'Ubicación padre', required=True,
        domain="[('usage', 'in', ('internal', 'view'))]", default=_default_parent)
    prefix = fields.Char('Rack / pasillo', required=True, help='Por ejemplo: A, B, P1…')
    position_from = fields.Integer('Posición inicial', default=1, required=True)
    position_to = fields.Integer('Posición final', default=10, required=True)
    level_from = fields.Integer('Nivel inicial', default=1, required=True)
    level_to = fields.Integer('Nivel final', default=3, required=True)
    storage_category_id = fields.Many2one(
        'stock.storage.category', 'Categoría de almacenamiento', default=_default_category,
        help='La categoría "Tarima" permite 1 tarima por ubicación y activa la asignación automática.')
    preview = fields.Char('Ejemplo', compute='_compute_preview')

    def _name_for(self, position, level):
        return '%s-%02d-%d' % (self.prefix.strip(), position, level)

    def _compute_preview(self):
        for wizard in self:
            if wizard.prefix:
                count = max(wizard.position_to - wizard.position_from + 1, 0) * \
                        max(wizard.level_to - wizard.level_from + 1, 0)
                first = wizard._name_for(wizard.position_from, wizard.level_from)
                last = wizard._name_for(wizard.position_to, wizard.level_to)
                wizard.preview = _('%(count)s ubicaciones: de %(first)s a %(last)s',
                                   count=count, first=first, last=last)
            else:
                wizard.preview = False

    def action_generate(self):
        self.ensure_one()
        if self.position_to < self.position_from or self.level_to < self.level_from:
            raise UserError(_('Los rangos finales deben ser mayores o iguales a los iniciales.'))
        total = (self.position_to - self.position_from + 1) * (self.level_to - self.level_from + 1)
        if total > MAX_LOCATIONS:
            raise UserError(_('Máximo %s ubicaciones por vez (pediste %s).', MAX_LOCATIONS, total))
        Location = self.env['stock.location']
        names = [
            self._name_for(position, level)
            for position in range(self.position_from, self.position_to + 1)
            for level in range(self.level_from, self.level_to + 1)
        ]
        existing = Location.with_context(active_test=False).search([
            ('barcode', 'in', names), ('company_id', 'in', [self.parent_id.company_id.id, False])])
        existing_barcodes = set(existing.mapped('barcode'))
        to_create = [name for name in names if name not in existing_barcodes]
        # Un rack (ubicación de tipo "vista", no guarda mercancía) agrupa sus posiciones.
        rack = Location.search([
            ('name', '=', self.prefix.strip()), ('location_id', '=', self.parent_id.id)], limit=1)
        if not rack:
            rack = Location.create({
                'name': self.prefix.strip(),
                'location_id': self.parent_id.id,
                'usage': 'view',
            })
        created = Location.create([{
            'name': name,
            'barcode': name,
            'location_id': rack.id,
            'usage': 'internal',
            'storage_category_id': self.storage_category_id.id or False,
        } for name in to_create])
        action = self.env['ir.actions.act_window']._for_xml_id(
            'stock_pallet_control.action_pallet_locations')
        action['domain'] = [('id', 'in', created.ids)] if created else [('id', '=', False)]
        action['context'] = {'search_default_group_parent': 0}
        action['name'] = _('Ubicaciones creadas (%(created)s nuevas, %(skipped)s ya existían)',
                           created=len(created), skipped=len(names) - len(created))
        return action
