# -*- coding: utf-8 -*-
"""
Modelo de líneas individuales de empleados para dispersión de Nómina HSBC H2H.
Permite seleccionar múltiples empleados, capturar o autocompletar sus datos bancarios
y definir importes individuales independientes en una tabla editable.
"""
from odoo import models, fields, api
from odoo.exceptions import UserError
from .constants import BANCO_HSBC, CUENTA_NOMINA_LENGTH


class H2hNominaLine(models.Model):
    _name = "h2h.nomina.line"
    _description = "Linea de Empleado para Pago de Nomina HSBC"
    _order = "sequence, id"

    payment_id = fields.Many2one(
        comodel_name="account.payment",
        string="Pago",
        required=True,
        ondelete="cascade",
        index=True,
    )
    sequence = fields.Integer(
        string="Secuencia",
        default=10,
    )

    # Empleado / Beneficiario
    partner_id = fields.Many2one(
        comodel_name="res.partner",
        string="Empleado",
        required=True,
        help="Empleado o beneficiario que recibira el pago de nomina.",
    )

    # Cuenta bancaria registrada
    partner_bank_id = fields.Many2one(
        comodel_name="res.partner.bank",
        string="Cuenta bancaria registrada",
        domain="[('partner_id', '=', partner_id)]",
        help="Cuenta bancaria registrada del empleado en Odoo.",
    )

    acc_number = fields.Char(
        string="Cuenta HSBC (10 digitos)",
        compute="_compute_bank_info",
        store=True,
        readonly=False,
        help="Numero de cuenta interna HSBC de 10 digitos para dispersion de nomina.",
    )

    bank_name = fields.Char(
        string="Banco",
        compute="_compute_bank_info",
        store=True,
        readonly=True,
        help="Institucion bancaria asignada a la cuenta.",
    )

    # Importe individual editable independiente
    amount = fields.Monetary(
        string="Importe individual",
        required=True,
        default=0.0,
        currency_field="currency_id",
        help="Importe neto a transferir a este empleado.",
    )

    currency_id = fields.Many2one(
        comodel_name="res.currency",
        related="payment_id.currency_id",
        string="Moneda",
        readonly=True,
    )

    # Estado de validacion individual
    validation_status = fields.Selection(
        selection=[
            ("pending", "Pendiente"),
            ("valid", "Valido"),
            ("error", "Error"),
        ],
        string="Estado de validacion",
        default="pending",
        readonly=True,
        help="Resultado de la validacion de datos bancarios de este empleado.",
    )

    error_details = fields.Char(
        string="Detalles / Error",
        readonly=True,
        help="Mensaje explicativo en caso de datos faltantes o incorrectos.",
    )

    # Referencia unica individual asignada en el XML
    referencia_empleado = fields.Char(
        string="Referencia",
        readonly=True,
        copy=False,
        help="Identificador unico de la transferencia en el archivo XML (InstrId / EndToEndId).",
    )

    xml_attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        string="Archivo XML",
        readonly=True,
        copy=False,
        help="Archivo XML generado asociado a esta operacion de nomina.",
    )

    # ── Autocompletado de datos bancarios ─────────────────────────────────────
    @api.depends("partner_id", "partner_bank_id")
    def _compute_bank_info(self):
        for line in self:
            if line.partner_bank_id:
                line.acc_number = (line.partner_bank_id.acc_number or "").strip()
                bank = line.partner_bank_id.bank_id
                line.bank_name = bank.name if bank else "HSBC"
            elif line.partner_id and line.partner_id.bank_ids:
                first_bank = line.partner_id.bank_ids[0]
                line.partner_bank_id = first_bank
                line.acc_number = (first_bank.acc_number or "").strip()
                bank = first_bank.bank_id
                line.bank_name = bank.name if bank else "HSBC"
            elif not line.acc_number:
                line.acc_number = ""
                line.bank_name = ""

    @api.onchange("partner_id")
    def _onchange_partner_id(self):
        if self.partner_id:
            if self.partner_id.bank_ids:
                first_bank = self.partner_id.bank_ids[0]
                self.partner_bank_id = first_bank
                self.acc_number = (first_bank.acc_number or "").strip()
                self.bank_name = first_bank.bank_id.name if first_bank.bank_id else "HSBC"
            else:
                self.partner_bank_id = False
                self.acc_number = ""
                self.bank_name = ""
            self.validation_status = "pending"
            self.error_details = ""

    @api.onchange("partner_bank_id")
    def _onchange_partner_bank_id(self):
        if self.partner_bank_id:
            self.acc_number = (self.partner_bank_id.acc_number or "").strip()
            bank = self.partner_bank_id.bank_id
            self.bank_name = bank.name if bank else "HSBC"
            self.validation_status = "pending"
            self.error_details = ""

    @api.onchange("acc_number", "amount")
    def _onchange_acc_or_amount(self):
        self.validation_status = "pending"
        self.error_details = ""

    def validate_line_data(self) -> bool:
        """
        Valida que la linea de empleado tenga todos los datos requeridos
        para la generacion del XML de nomina HSBC.
        Actualiza validation_status y error_details.
        """
        self.ensure_one()
        cuenta = (self.acc_number or "").strip()

        if not self.partner_id:
            self.validation_status = "error"
            self.error_details = "Falta seleccionar el empleado."
            return False

        if not cuenta:
            self.validation_status = "error"
            self.error_details = "El empleado no tiene numero de cuenta registrado."
            return False

        if not cuenta.isdigit() or len(cuenta) != CUENTA_NOMINA_LENGTH:
            self.validation_status = "error"
            self.error_details = (
                f"La cuenta '{cuenta}' no es valida. Debe tener exactamente "
                f"{CUENTA_NOMINA_LENGTH} digitos numericos."
            )
            return False

        if not self.amount or self.amount <= 0:
            self.validation_status = "error"
            self.error_details = "El importe individual debe ser mayor a cero."
            return False

        self.validation_status = "valid"
        self.error_details = "Datos bancarios e importe correctos."
        return True
