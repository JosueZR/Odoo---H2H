# -*- coding: utf-8 -*-
from odoo import SUPERUSER_ID, api


def migrate(cr, version):
    """Bases que ya tenían una versión anterior: aplicar una vez lo que la instalación hace."""
    env = api.Environment(cr, SUPERUSER_ID, {})
    env['stock.picking.type']._pallet_setup_operation_types()
