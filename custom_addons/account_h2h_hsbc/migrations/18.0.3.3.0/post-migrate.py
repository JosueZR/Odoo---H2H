# -*- coding: utf-8 -*-
"""
Recalcula el estado de las facturas y pagos H2H salientes que se registraron
antes de este cambio y quedaron en "Pagado" sin que HSBC aceptara el pago.
Pasan a "En proceso de pago" (factura) y "En proceso" (pago).
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    env = api.Environment(cr, SUPERUSER_ID, {})
    pagos = env["account.payment"].search([
        ("journal_id.is_h2h_enabled", "=", True),
        ("payment_type", "=", "outbound"),
        ("h2h_state", "!=", "accepted"),
        ("state", "in", ("paid", "in_process")),
    ])
    if not pagos:
        return
    facturas = pagos.reconciled_bill_ids | pagos.reconciled_invoice_ids
    facturas._compute_payment_state()
    pagos._compute_state()
    env.flush_all()
