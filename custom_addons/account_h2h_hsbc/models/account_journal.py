# -*- coding: utf-8 -*-
from odoo import models, fields


class AccountJournal(models.Model):
    _inherit = "account.journal"

    # ── Configuración HSBC H2H ────────────────────────────────────────────────
    is_h2h_enabled = fields.Boolean(
        string="Habilitar integración HSBC H2H",
        default=False,
        help="Activa la integración Host-to-Host con HSBC para este diario.",
    )
    hsbc_client_id = fields.Char(
        string="ID de cliente HSBC",
        help="Identificador de empresa asignado por HSBC (ej. PC000032364). "
             "Se incluye en el campo InitgPty/Id del XML pain.001.",
    )
    hsbc_bic = fields.Char(
        string="BIC / SWIFT HSBC",
        default="BIMEMXMM",
        help="Código BIC del banco ordenante (HSBC México = BIMEMXMM).",
    )
    hsbc_nomina_account = fields.Char(
        string="Cuenta HSBC Nómina",
        help="Número de cuenta HSBC de dispersión de nómina (10 dígitos). "
             "Es la cuenta interna HSBC desde la que se dispersa la nómina a empleados. "
             "Requerida únicamente para pagos de tipo Nómina HSBC.",
    )
