# -*- coding: utf-8 -*-
from odoo import models


class AccountMove(models.Model):
    _inherit = "account.move"

    def _get_invoice_in_payment_state(self):
        """
        Mientras un pago HSBC H2H no haya sido aceptado por el banco, la factura
        queda en "En proceso de pago" y no en "Pagado".

        Odoo Community regresa 'paid' en cuanto el pago se cruza con la factura
        (Enterprise regresa 'in_payment' hasta conciliar con el estado de cuenta).
        Registrar el pago en Odoo solo instruye el pago; el dinero sale hasta que
        HSBC lo procesa, así que se fuerza 'in_payment' para los pagos H2H
        salientes pendientes. Una vez aceptado por HSBC, se usa el comportamiento
        estándar de la edición instalada.
        """
        pagos_h2h_pendientes = self.reconciled_payment_ids.filtered(
            lambda p: p.is_hsbc_journal
            and p.payment_type == "outbound"
            and p.h2h_state != "accepted"
        )
        if pagos_h2h_pendientes:
            return "in_payment"
        return super()._get_invoice_in_payment_state()
