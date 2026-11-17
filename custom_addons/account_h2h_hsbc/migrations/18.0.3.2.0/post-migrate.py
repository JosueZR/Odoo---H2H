# -*- coding: utf-8 -*-
"""
En OPI la comisión siempre la paga la empresa ordenante (ChrgBr = DEBT).
Corrige los pagos que quedaron con SHAR, CRED o vacío antes de este cambio.
"""


def migrate(cr, version):
    cr.execute(
        """
        UPDATE account_payment
           SET h2h_opi_chrgbr = 'DEBT'
         WHERE h2h_opi_chrgbr IS DISTINCT FROM 'DEBT'
        """
    )
