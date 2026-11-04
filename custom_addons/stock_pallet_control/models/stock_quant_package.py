# -*- coding: utf-8 -*-
from odoo import fields, models


class StockQuantPackage(models.Model):
    _inherit = 'stock.quant.package'

    pallet_content = fields.Char('Contenido', compute='_compute_pallet_content')
    # Número de tarima dentro de una misma recepción (ej. 2 de 5); va en la etiqueta.
    pallet_index = fields.Integer('No. de tarima', default=0)
    pallet_total = fields.Integer('Total de tarimas en la recepción', default=0)
    pallet_origin = fields.Char('Documento de origen', help='Orden de compra o recepción de donde vino la tarima.')

    def _compute_pallet_content(self):
        for package in self:
            by_product = {}
            for quant in package.quant_ids.filtered(lambda q: q.quantity):
                by_product[quant.product_id] = by_product.get(quant.product_id, 0.0) + quant.quantity
            package.pallet_content = '; '.join(
                '%s: %g %s' % (product.display_name, qty, product.uom_id.name)
                for product, qty in by_product.items())
