# -*- coding: utf-8 -*-
from odoo import api, fields, models


class StockLocation(models.Model):
    _inherit = 'stock.location'

    pallet_ids = fields.Many2many(
        'stock.quant.package', string='Tarimas', compute='_compute_pallet_info')
    pallet_count = fields.Integer('No. de tarimas', compute='_compute_pallet_info')
    pallet_owner_ids = fields.Many2many(
        'res.partner', string='Propietarios', compute='_compute_pallet_info')
    pallet_state = fields.Selection(
        [('free', 'Libre'), ('occupied', 'Ocupada')],
        string='Estado', compute='_compute_pallet_info', search='_search_pallet_state')

    def _pallet_quants_domain(self):
        return [('package_id', '!=', False), ('quantity', '>', 0)]

    @api.depends('usage')
    def _compute_pallet_info(self):
        quants = self.env['stock.quant']
        real_ids = [loc.id for loc in self if isinstance(loc.id, int)]
        if real_ids:
            quants = self.env['stock.quant'].sudo().search(
                self._pallet_quants_domain() + [('location_id', 'in', real_ids)])
        by_location = {}
        for quant in quants:
            by_location.setdefault(quant.location_id.id, self.env['stock.quant'])
            by_location[quant.location_id.id] |= quant
        for location in self:
            location_quants = by_location.get(location.id, self.env['stock.quant'])
            packages = location_quants.package_id
            location.pallet_ids = packages
            location.pallet_count = len(packages)
            location.pallet_owner_ids = location_quants.owner_id
            if location.usage == 'internal':
                location.pallet_state = 'occupied' if packages else 'free'
            else:
                location.pallet_state = False

    @api.model
    def _search_pallet_state(self, operator, value):
        if operator not in ('=', '!=', 'in', 'not in'):
            raise NotImplementedError('Operador no soportado para el estado de la ubicación.')
        values = value if isinstance(value, (list, tuple)) else [value]
        occupied_locations = self.env['stock.quant'].sudo()._read_group(
            self._pallet_quants_domain() + [('location_id.usage', '=', 'internal')],
            ['location_id'])
        occupied_ids = [location.id for (location,) in occupied_locations]
        wanted = set(values) if operator in ('=', 'in') else {'free', 'occupied'} - set(values)
        if wanted >= {'free', 'occupied'}:
            return [('usage', '=', 'internal')]
        if 'occupied' in wanted:
            return [('id', 'in', occupied_ids)]
        if 'free' in wanted:
            return [('usage', '=', 'internal'), ('id', 'not in', occupied_ids)]
        return [('id', '=', False)]

    def action_view_pallets(self):
        self.ensure_one()
        action = self.env['ir.actions.act_window']._for_xml_id(
            'stock_pallet_control.action_pallet_packages')
        action['domain'] = [('id', 'in', self.pallet_ids.ids)]
        return action
