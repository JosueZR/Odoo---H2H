# -*- coding: utf-8 -*-
from odoo import fields, models


class StockQuantPackage(models.Model):
    _inherit = 'stock.quant.package'

    pallet_content = fields.Char('Contenido', compute='_compute_pallet_content')

    def _compute_pallet_content(self):
        for package in self:
            lines = []
            by_product = {}
            for quant in package.quant_ids.filtered(lambda q: q.quantity):
                by_product[quant.product_id] = by_product.get(quant.product_id, 0.0) + quant.quantity
            for product, qty in by_product.items():
                lines.append('%s: %g %s' % (product.display_name, qty, product.uom_id.name))
            package.pallet_content = '; '.join(lines)

    def action_print_pallet_label(self):
        return self.env.ref('stock_pallet_control.action_report_pallet_label').report_action(self)
