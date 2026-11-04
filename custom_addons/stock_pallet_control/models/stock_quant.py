# -*- coding: utf-8 -*-
from odoo import models
from odoo.osv import expression


class StockQuant(models.Model):
    _inherit = 'stock.quant'

    def _get_gather_domain(self, product_id, location_id, lot_id=None, package_id=None, owner_id=None, strict=False):
        """Protege la mercancía de clientes (con propietario).

        Odoo, al apartar para una entrega que no indica propietario ni tarima, toma cualquier
        existencia, incluida la de clientes. Aquí, en ese caso, solo se toma mercancía propia
        (sin propietario o de una compañía propia). Si se indica la tarima (paquete) o el
        propietario, se respeta: así se saca la tarima del cliente escaneándola.
        """
        domain = super()._get_gather_domain(
            product_id, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict)
        if not strict and not owner_id and not package_id:
            own_partners = self.env['res.company'].sudo().search([]).partner_id.ids
            domain = expression.AND([
                ['|', ('owner_id', '=', False), ('owner_id', 'in', own_partners)], domain])
        return domain
