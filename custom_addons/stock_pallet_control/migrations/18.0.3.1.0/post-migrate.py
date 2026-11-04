# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Bases que ya tenían el módulo: activar Paquetes y Propietario para los usuarios internos.

    Al instalar lo hace security/pallet_security.xml, pero Odoo no reaplica cambios a
    base.group_user al actualizar.
    """
    env = api.Environment(cr, SUPERUSER_ID, {})
    env.ref('base.group_user').write({'implied_ids': [
        (4, env.ref('stock.group_tracking_lot').id),
        (4, env.ref('stock.group_tracking_owner').id),
    ]})
