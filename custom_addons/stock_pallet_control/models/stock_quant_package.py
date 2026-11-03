# -*- coding: utf-8 -*-
from odoo import fields, models


class StockQuantPackage(models.Model):
    _inherit = 'stock.quant.package'

    pallet_content = fields.Char('Contenido', compute='_compute_pallet_content')
    # Número de tarima dentro de un lote (ej. 1 de 3)
    pallet_index = fields.Integer('No. de tarima', default=0)
    # Total de tarimas registradas en el mismo lote
    pallet_total = fields.Integer('Total de tarimas en el lote', default=0)
    # Referencia del lote/recepción de origen
    pallet_origin = fields.Char('Referencia de entrada')

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
