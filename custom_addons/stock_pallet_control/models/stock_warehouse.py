# -*- coding: utf-8 -*-
from odoo import models


class StockWarehouse(models.Model):
    _inherit = 'stock.warehouse'

    def _get_picking_type_create_values(self, max_sequence):
        """Almacenes nuevos: sus Entregas e internas nacen con "Mover paquetes completos"."""
        values, next_sequence = super()._get_picking_type_create_values(max_sequence)
        for vals in values.values():
            if vals.get('code') in ('outgoing', 'internal'):
                vals['show_entire_packs'] = True
        return values, next_sequence
