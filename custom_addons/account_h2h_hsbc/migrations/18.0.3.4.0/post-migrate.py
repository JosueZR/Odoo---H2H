# -*- coding: utf-8 -*-
"""
Antes, al cambiar de método H2H el módulo cambiaba la moneda del pago (p. ej. a USD
al elegir SPID) sin tocar el importe. En pagos ya registrados Odoo no resincroniza
el asiento publicado, así que el pago quedaba en una moneda distinta a la de su
asiento contable.

Este script regresa esos pagos a la moneda e importe de su asiento y, si el método
H2H seleccionado no opera en esa moneda, le asigna el método sugerido.
"""
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    # Reparar el asiento es necesario aunque el pago ya esté enviado a HSBC, así que
    # se omite la protección que bloquea editar pagos enviados.
    env = api.Environment(cr, SUPERUSER_ID, {"h2h_sin_proteccion_xml": True})
    pagos = env["account.payment"].search([
        ("journal_id.is_h2h_enabled", "=", True),
        ("move_id.state", "=", "posted"),
    ])
    reparados = env["account.payment"]
    for pago in pagos:
        liquidez, _contrapartida, _otros = pago._seek_for_lines()
        moneda_asiento = liquidez.currency_id[:1]
        if moneda_asiento and moneda_asiento != pago.currency_id:
            pago.write({
                "currency_id": moneda_asiento.id,
                "amount": abs(sum(liquidez.mapped("amount_currency"))),
            })
            reparados |= pago
    reparados._h2h_ajustar_metodo_a_moneda()
