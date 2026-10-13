# -*- coding: utf-8 -*-
"""
Catálogo de métodos de pago HSBC H2H.
Cada registro representa un tipo de pago (SPEI, SPID, Nómina, etc.).
Los métodos con is_available=False aparecen visualmente en la UI
pero están deshabilitados hasta que se implemente su generador.
"""
from odoo import models, fields


class H2hPaymentMethod(models.Model):
    _name        = "h2h.payment.method"
    _description = "Método de Pago HSBC H2H"
    _order       = "sequence, id"

    code = fields.Char(
        string="Código",
        required=True,
        help="Código interno del método: SPEI, SPID, ACH, etc. "
             "Debe coincidir con el METHOD_CODE del generador correspondiente.",
    )
    name = fields.Char(
        string="Nombre",
        required=True,
        translate=True,
    )
    description = fields.Char(
        string="Descripción",
        translate=True,
        help="Descripción breve que se muestra al usuario en la tarjeta del método.",
    )
    is_available = fields.Boolean(
        string="Disponible",
        default=False,
        help="Si está desactivado, el método aparece en la UI como 'En desarrollo' "
             "y no puede seleccionarse para generar pagos.",
    )
    sequence = fields.Integer(
        string="Secuencia",
        default=10,
        help="Orden de aparición en la pantalla de selección de método.",
    )

    _sql_constraints = [
        ("code_unique", "UNIQUE(code)", "El código del método H2H debe ser único."),
    ]
