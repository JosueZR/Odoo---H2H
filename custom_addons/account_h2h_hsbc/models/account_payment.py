# -*- coding: utf-8 -*-
import base64
import xml.etree.ElementTree as ET
from markupsafe import Markup
from odoo import models, fields, api
from odoo.exceptions import UserError


# Moneda en la que opera cada método H2H. OPI opera en cualquier divisa excepto MXN.
H2H_MONEDA_METODO = {
    "SPEI": "MXN",
    "SERVICIOS": "MXN",
    "NOMINA": "MXN",
    "SPID": "USD",
}
H2H_NOMBRE_METODO = {
    "SPEI": "SPEI",
    "SERVICIOS": "Servicios",
    "NOMINA": "Nómina HSBC",
    "SPID": "SPID",
    "OPI": "OPI",
}


# Campos del pago que se escriben en el XML. Si cambian después de generarlo, el
# archivo ya no corresponde al pago y debe generarse de nuevo.
H2H_CAMPOS_XML = (
    "amount", "currency_id", "partner_id", "partner_bank_id", "journal_id", "date",
    "h2h_spid_rfc", "h2h_spid_codigo", "h2h_spid_referencia_larga",
    "h2h_opi_purp_code", "h2h_opi_reg_code", "h2h_opi_referencia_larga",
    "h2h_nomina_line_ids",
)
# El memo solo se usa como respaldo de la referencia OPI: invalida el XML, pero
# corregirlo después del envío no cambia lo que recibió el banco.
H2H_CAMPOS_XML_INVALIDAN = H2H_CAMPOS_XML + ("memo",)

# Estados H2H en los que el archivo ya está (o estuvo) en manos de HSBC.
H2H_ESTADOS_EN_BANCO = ("sent_to_bank", "accepted")


def h2h_metodo_compatible(code, moneda):
    """True si el método H2H puede operar en la moneda indicada (código ISO)."""
    if code == "OPI":
        return moneda != "MXN"
    requerida = H2H_MONEDA_METODO.get(code)
    return requerida is None or requerida == moneda


class AccountPayment(models.Model):
    _inherit = "account.payment"

    # ── Compatibilidad método / moneda ────────────────────────────────────────
    def _h2h_metodo_sugerido(self):
        """
        Método H2H que corresponde a la moneda del pago:
        MXN -> SPEI; USD -> SPID si el beneficiario es de México, si no OPI;
        cualquier otra divisa -> OPI.
        """
        self.ensure_one()
        moneda = self.currency_id.name
        if moneda == "MXN":
            code = "SPEI"
        elif moneda == "USD" and (not self.partner_id.country_id or self.partner_id.country_id.code == "MX"):
            code = "SPID"
        else:
            code = "OPI"
        return self.env["h2h.payment.method"].search(
            [("code", "=", code), ("is_available", "=", True)], limit=1
        )

    def _h2h_ajustar_metodo_a_moneda(self):
        """Si el método preseleccionado no opera en la moneda del pago, usar el sugerido."""
        for pago in self:
            if (
                pago.is_hsbc_journal
                and pago.h2h_method
                and pago.h2h_state in ("draft", "method_selected")
                and not h2h_metodo_compatible(pago.h2h_method.code, pago.currency_id.name)
            ):
                sugerido = pago._h2h_metodo_sugerido()
                if sugerido:
                    pago.write({"h2h_method": sugerido.id, "h2h_state": "method_selected"})

    @api.model_create_multi
    def create(self, vals_list):
        pagos = super().create(vals_list)
        # Pagos creados por código (p. ej. "Pagar" desde la factura): default_get no
        # conoce el tipo de pago, así que el método se elige aquí según la moneda.
        for pago in pagos:
            if pago.is_hsbc_journal and not pago.h2h_method:
                sugerido = pago._h2h_metodo_sugerido()
                if sugerido:
                    pago.write({"h2h_method": sugerido.id, "h2h_state": "method_selected"})
        # default_get preselecciona SPEI antes de conocer la moneda (p. ej. al abrir el
        # formulario de un pago en USD o EUR); se corrige con la moneda real.
        pagos._h2h_ajustar_metodo_a_moneda()
        return pagos

    # ── Protección del XML ya generado o enviado ─────────────────────────────
    def _h2h_campos_xml_cambiados(self, vals, campos):
        """Campos de `campos` cuyo valor en `vals` es distinto del actual del pago."""
        self.ensure_one()
        cambiados = []
        for campo in campos:
            if campo not in vals:
                continue
            field = self._fields[campo]
            nuevo = vals[campo]
            actual = self[campo]
            if field.type == "one2many":
                distinto = bool(nuevo)  # cualquier comando sobre las líneas
            elif field.type == "many2one":
                if isinstance(nuevo, models.BaseModel):
                    nuevo = nuevo.id
                distinto = (actual.id or False) != (nuevo or False)
            elif field.type in ("monetary", "float"):
                distinto = fields.Float.compare(actual or 0.0, nuevo or 0.0, precision_digits=2) != 0
            elif field.type == "date":
                distinto = actual != fields.Date.to_date(nuevo)
            else:
                distinto = (actual or False) != (nuevo or False)
            if distinto:
                cambiados.append(field.string)
        return cambiados

    def write(self, vals):
        invalidar = self.browse()
        # Las migraciones que reparan datos contables pasan h2h_sin_proteccion_xml=True.
        if not self.env.context.get("h2h_sin_proteccion_xml") and any(
            campo in vals for campo in H2H_CAMPOS_XML_INVALIDAN
        ):
            for pago in self:
                if pago.h2h_state in H2H_ESTADOS_EN_BANCO:
                    cambiados = pago._h2h_campos_xml_cambiados(vals, H2H_CAMPOS_XML)
                    if cambiados:
                        raise UserError(
                            f"El pago {pago.name or ''} ya se envió a HSBC con los datos actuales, "
                            f"así que no se puede modificar: {', '.join(cambiados)}.\n\n"
                            "Si los datos estaban mal, espere la respuesta del banco; si lo rechaza, "
                            "registre el rechazo, restablezca el pago a borrador y corríjalo."
                        )
                elif pago.h2h_state == "xml_generated" and pago._h2h_campos_xml_cambiados(
                    vals, H2H_CAMPOS_XML_INVALIDAN
                ):
                    invalidar |= pago

        res = super().write(vals)

        if invalidar:
            # El XML ya no refleja el pago: se exige generarlo de nuevo antes de enviar.
            invalidar.write({"h2h_state": "method_selected"})
            for pago in invalidar:
                pago.message_post(body=Markup(
                    "<b>El XML generado quedó desactualizado</b> porque cambiaron datos del pago.<br/>"
                    "Genere el XML de nuevo antes de enviarlo a HSBC."
                ))
        return res

    @api.onchange("currency_id")
    def _onchange_currency_h2h(self):
        if (
            self.is_hsbc_journal
            and self.h2h_method
            and self.h2h_state in ("draft", "method_selected")
            and not h2h_metodo_compatible(self.h2h_method.code, self.currency_id.name)
        ):
            sugerido = self._h2h_metodo_sugerido()
            if sugerido:
                self.h2h_method = sugerido
                self.h2h_method_code = sugerido.code

    # ── Valores por defecto para inicialización al crear un pago nuevo ────────
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # H2H solo se usa para pagos a proveedores: los cobros conservan su diario.
        tipo = res.get("payment_type") or self.env.context.get("default_payment_type")
        if tipo != "outbound":
            return res

        # Si el usuario abrió el pago desde un diario concreto (p. ej. Efectivo), se respeta.
        # Solo cuando no eligió diario se sugiere el de HSBC, para que los cuadros H2H
        # aparezcan desde que se abre el formulario.
        company_id = res.get("company_id") or self.env.company.id
        current_journal_id = res.get("journal_id")
        hsbc_journal = None

        if current_journal_id:
            journal = self.env["account.journal"].browse(current_journal_id)
            if journal.is_h2h_enabled:
                hsbc_journal = journal
            elif self.env.context.get("default_journal_id"):
                return res

        if not hsbc_journal:
            hsbc_journal = self.env["account.journal"].search([
                ("company_id", "=", company_id),
                ("type", "=", "bank"),
                ("is_h2h_enabled", "=", True),
            ], limit=1)

        if hsbc_journal:
            res["journal_id"] = hsbc_journal.id
            # Pre-seleccionar SPEI si no hay método elegido
            metodo_spei = self.env["h2h.payment.method"].search(
                [("code", "=", "SPEI"), ("is_available", "=", True)], limit=1
            )
            if metodo_spei:
                res["h2h_method"] = metodo_spei.id
                res["h2h_state"] = "method_selected"

        return res

    # ── Detección de diario HSBC ──────────────────────────────────────────────
    is_hsbc_journal = fields.Boolean(
        string="Pago saliente HSBC H2H",
        compute="_compute_is_hsbc_journal",
        store=False,
        help="Pago a proveedor (saliente) en un diario con HSBC H2H habilitado. "
             "H2H solo se usa para pagar; los cobros no muestran la sección H2H.",
    )

    @api.depends("journal_id", "journal_id.is_h2h_enabled", "payment_type")
    def _compute_is_hsbc_journal(self):
        for rec in self:
            rec.is_hsbc_journal = bool(
                rec.journal_id
                and rec.journal_id.is_h2h_enabled
                and rec.payment_type == "outbound"
            )

    @api.onchange("journal_id")
    def _onchange_journal_h2h(self):
        """
        Cuando se selecciona un diario HSBC H2H, auto-selecciona
        el primer método disponible si no hay uno seleccionado.
        Conserva la selección existente para evitar restablecerla.
        Cuando se cambia a un diario no-HSBC, limpia el método.
        """
        if self.journal_id and self.journal_id.is_h2h_enabled:
            if not self.h2h_method:
                metodo_spei = self.env["h2h.payment.method"].search(
                    [("code", "=", "SPEI"), ("is_available", "=", True)], limit=1
                )
                self.h2h_method = metodo_spei or False
                if metodo_spei:
                    self.h2h_state = "method_selected"
                    self.h2h_method_code = metodo_spei.code
        else:
            self.h2h_method = False
            self.h2h_method_code = False
            self.h2h_state = "draft"

    # ── Código de método para control visual en la UI ────────────────────────
    h2h_method_code = fields.Char(
        string="Código de método H2H",
        compute="_compute_h2h_method_code",
        store=True,
        readonly=True,
        help="Código técnico del método H2H para control de visibilidad en interfaz.",
    )

    @api.depends("h2h_method", "h2h_method.code")
    def _compute_h2h_method_code(self):
        for rec in self:
            rec.h2h_method_code = rec.h2h_method.code if rec.h2h_method else False

    @api.onchange("h2h_method")
    def _onchange_h2h_method(self):
        """
        Sincroniza el código del método y el estado cuando se selecciona
        el método de pago.
        """
        if self.h2h_method:
            self.h2h_method_code = self.h2h_method.code
            if self.h2h_state == "draft":
                self.h2h_state = "method_selected"
        else:
            self.h2h_method_code = False

    # ── Estado interno H2H (no toca el state de Odoo) ────────────────────────
    h2h_state = fields.Selection(
        selection=[
            ("draft",           "Sin iniciar"),
            ("method_selected", "Método seleccionado"),
            ("xml_generated",   "XML generado"),
            ("xml_validated",   "XML validado"),
            ("sent_to_bank",    "Enviado a HSBC"),
            ("accepted",        "Aceptado por HSBC"),
            ("rejected",        "Rechazado por HSBC"),
        ],
        string="Estado H2H",
        default="draft",
        copy=False,
        tracking=True,
        help="Seguimiento interno del proceso HSBC H2H, independiente del estado contable de Odoo.",
    )

    # ── Método H2H seleccionado ───────────────────────────────────────────────
    h2h_method = fields.Many2one(
        comodel_name="h2h.payment.method",
        string="Método de pago HSBC",
        copy=False,
        domain="[('is_available', '=', True)]",
        help="Método H2H seleccionado: SPEI, SPID, Nómina, Servicios, OPI.",
    )

    # ── Campo auxiliar para la vista ─────────────────────────────────────────
    h2h_xml_attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        string="XML H2H generado",
        copy=False,
        readonly=True,
    )

    # ── Campos específicos de SPID ─────────────────────────────────────────────
    h2h_spid_rfc = fields.Char(
        string="RFC Beneficiario SPID",
        copy=False,
        help="RFC del beneficiario. Obligatorio para pagos SPID. "
             "Si está vacío, se toma del RFC del proveedor (campo Vat).",
    )
    h2h_spid_codigo = fields.Selection(
        selection=[
            ("01", "01 — Liquidación de operación con valores"),
            ("02", "02 — Liquidación de operación derivada"),
            ("03", "03 — Liquidación de operación cambiaria"),
            ("04", "04 — Pago de servicios"),
            ("05", "05 — Pago de bienes"),
            ("06", "06 — Otorgamiento de préstamo"),
            ("07", "07 — Pago de préstamo"),
            ("08", "08 — Otros"),
        ],
        string="Código de operación SPID",
        default="04",
        copy=False,
        help="Código de clasificación de la operación SPID. Obligatorio para pagos SPID. "
             "Se incluye en RgltryRptg/Dtls/Inf como '/SPID/OC/{codigo}'.",
    )
    h2h_spid_referencia_larga = fields.Char(
        string="Referencia SPID (Ustrd)",
        copy=False,
        size=40,
        help="Referencia que se entrega al beneficiario SPID. "
             "Máximo 40 caracteres. Se incluye en RmtInf/Ustrd del XML.",
    )

    # ── Campos específicos de OPI (Orden de Pago Internacional / Cross Border) ──
    h2h_opi_chrgbr = fields.Selection(
        selection=[
            ("DEBT", "DEBT — Las paga el ordenante"),
        ],
        string="Comisiones OPI (ChrgBr)",
        default="DEBT",
        copy=False,
        help="Quién paga las comisiones del pago internacional. "
             "Siempre DEBT: la comisión la paga la empresa ordenante, nunca el beneficiario.",
    )
    h2h_opi_purp_code = fields.Selection(
        selection=[
            ("CINV", "CINV — Pago de factura comercial"),
            ("GDDS", "GDDS — Pago de bienes"),
            ("INTC", "INTC — Transferencia entre cuentas propias"),
            ("SUPP", "SUPP — Pago a proveedor"),
            ("SALA", "SALA — Pago de nómina"),
            ("TAXS", "TAXS — Pago de impuestos"),
        ],
        string="Propósito ISO OPI (Purp)",
        default="CINV",
        copy=False,
        help="Código ISO 20022 global del propósito del pago (Purp/Cd).",
    )
    h2h_opi_reg_code = fields.Selection(
        selection=[
            ("01", "01 — Pago a proveedores"),
            ("02", "02 — Pago de impuestos"),
            ("03", "03 — Envío de pago a casa matriz"),
            ("04", "04 — Pago a filiales o subsidiarias"),
            ("05", "05 — Pago de créditos"),
            ("06", "06 — Pago de seguros"),
            ("07", "07 — Pago Fideicomisos"),
            ("08", "08 — Pago de servicios"),
            ("09", "09 — Pago a tarjeta de crédito"),
            ("10", "10 — Pago a tarjeta de débito"),
            ("11", "11 — Pago de nómina"),
            ("12", "12 — Pago de inversiones"),
            ("13", "13 — Pago otras operaciones"),
            ("14", "14 — Pago a proveedores locales"),
            ("15", "15 — Pago a clientes locales"),
            ("16", "16 — Pago de proveedores fronterizos"),
            ("17", "17 — Pago a clientes fronterizos"),
            ("18", "18 — Inversión"),
            ("19", "19 — Pago de bienes"),
            ("20", "20 — Otorgamiento de préstamo"),
            ("21", "21 — Pago de préstamo"),
            ("22", "22 — Otros"),
        ],
        string="Propósito regulatorio OPI",
        default="01",
        copy=False,
        help="Catálogo 'Propósito del Pago' (01 a 22) para el reporte regulatorio. "
             "Se incluye en RgltryRptg/Dtls/Inf como '/BENEFRES/MX//{codigo}'.",
    )
    h2h_opi_referencia_larga = fields.Char(
        string="Referencia OPI (Ustrd)",
        copy=False,
        size=140,
        help="Texto libre para el beneficiario (ej. número de factura). Máximo 140 caracteres. "
             "Si se deja vacío se usa el Memo del pago.",
    )

    # ── Gestión de Nómina Multi-Empleado (tabla editable) ──────────────────────
    h2h_nomina_line_ids = fields.One2many(
        comodel_name="h2h.nomina.line",
        inverse_name="payment_id",
        string="Empleados para dispersión de nómina",
        copy=True,
        help="Tabla de empleados para dispersión de nómina con cuentas e importes individuales.",
    )

    h2h_nomina_total = fields.Monetary(
        string="Total Nómina",
        compute="_compute_h2h_nomina_totals",
        store=True,
        currency_field="currency_id",
        help="Suma total de los importes individuales de nómina.",
    )

    h2h_nomina_count = fields.Integer(
        string="Empleados seleccionados",
        compute="_compute_h2h_nomina_totals",
        store=True,
        help="Número total de empleados seleccionados en la tabla de nómina.",
    )

    @api.depends("h2h_nomina_line_ids.amount", "h2h_method_code")
    def _compute_h2h_nomina_totals(self):
        for rec in self:
            total = sum(rec.h2h_nomina_line_ids.mapped("amount"))
            rec.h2h_nomina_total = total
            rec.h2h_nomina_count = len(rec.h2h_nomina_line_ids)
            # En modo nómina, el importe global del pago refleja la suma de empleados
            if rec.h2h_method_code == "NOMINA" and total > 0:
                rec.amount = total

    # =========================================================================
    # Acciones de selección interactiva de método (desde los cuadros visuales)
    # =========================================================================
    def action_select_h2h_spei(self):
        """Selecciona el método SPEI desde el cuadro visual."""
        self._select_h2h_method_by_code("SPEI")

    def action_select_h2h_spid(self):
        """Selecciona el método SPID desde el cuadro visual."""
        self._select_h2h_method_by_code("SPID")

    def action_select_h2h_nomina(self):
        """Selecciona el método Nómina desde el cuadro visual."""
        self._select_h2h_method_by_code("NOMINA")

    def action_select_h2h_servicios(self):
        """Selecciona el método Servicios desde el cuadro visual."""
        self._select_h2h_method_by_code("SERVICIOS")

    def action_select_h2h_opi(self):
        """Selecciona el método OPI (Cross Border) desde el cuadro visual."""
        self._select_h2h_method_by_code("OPI")

    def _select_h2h_method_by_code(self, code: str):
        """
        Asigna el método de pago por su código técnico y actualiza el estado.
        Permite cambiar de método mientras el pago esté en borrador y no se haya
        confirmado o enviado de forma irreversible al banco (sent_to_bank o accepted).
        Al cambiar de método, limpia configuraciones incompatibles (moneda USD/MXN,
        campos específicos de SPID) y preserva la información e historial generados.
        """
        self.ensure_one()
        if self.h2h_state in ("sent_to_bank", "accepted"):
            raise UserError(
                "No se puede cambiar el método de pago porque la instrucción ya fue enviada o procesada por el banco."
            )

        if self.state not in ("draft", "in_process"):
            raise UserError("El pago debe estar en estado borrador para cambiar el método de pago.")

        # Si ya se encuentra en el mismo método, no se requiere reconfiguración
        if self.h2h_method_code == code:
            return

        # Verificar o auto-asignar diario HSBC si no está activo
        vals = {}
        if not self.journal_id or not self.journal_id.is_h2h_enabled:
            hsbc_journal = self.env["account.journal"].search([
                ("company_id", "=", self.company_id.id),
                ("type", "=", "bank"),
                ("is_h2h_enabled", "=", True),
            ], limit=1)
            if not hsbc_journal:
                raise UserError(
                    "No se encontró un diario bancario con integración HSBC H2H habilitada en esta empresa. "
                    "Vaya a Contabilidad -> Configuración -> Diarios y active la integración HSBC H2H."
                )
            vals["journal_id"] = hsbc_journal.id

        metodo = self.env["h2h.payment.method"].search(
            [("code", "=", code), ("is_available", "=", True)], limit=1
        )
        if not metodo:
            raise UserError(f"El método '{code}' no está disponible actualmente.")

        metodo_anterior = self.h2h_method_code

        vals.update({
            "h2h_method": metodo.id,
            "h2h_state": "method_selected",
        })

        # ── Ajustes de compatibilidad al cambiar de método ───────────────────
        # 1. La moneda NO se cambia: la define la factura / el pago y, si el pago
        #    ya está registrado, su asiento contable (que Odoo no resincroniza).
        #    Si el método no opera en la moneda del pago, se explica qué hacer.
        moneda = self.currency_id.name
        if not h2h_metodo_compatible(code, moneda):
            compatibles = [
                H2H_NOMBRE_METODO[c] for c in ("SPEI", "SERVICIOS", "NOMINA", "SPID", "OPI")
                if h2h_metodo_compatible(c, moneda)
            ]
            opera = "cualquier divisa distinta de MXN" if code == "OPI" else H2H_MONEDA_METODO[code]
            if self.move_id:
                accion = (
                    f"Este pago ya está registrado en {moneda}. Para pagar por "
                    f"{H2H_NOMBRE_METODO[code]} registra la factura y el pago en {opera}."
                )
            else:
                accion = f"Cambia primero el campo Moneda del pago a {opera}."
            raise UserError(
                f"{H2H_NOMBRE_METODO[code]} opera en {opera} y este pago está en {moneda}.\n\n"
                f"{accion}\n\n"
                f"Métodos disponibles para {moneda}: {', '.join(compatibles)}."
            )

        # 1b. Al entrar a SPID, precargar los datos obligatorios que se puedan deducir
        if code == "SPID":
            if not self.h2h_spid_codigo:
                vals["h2h_spid_codigo"] = "04"
            if not self.h2h_spid_rfc and self.partner_id.vat:
                vals["h2h_spid_rfc"] = self.partner_id.vat

        # 2. Si venía de SPID y pasa a otro método, limpiar campos residuales de SPID
        if metodo_anterior == "SPID" and code != "SPID":
            vals.update({
                "h2h_spid_codigo": False,
                "h2h_spid_rfc": False,
                "h2h_spid_referencia_larga": False,
            })

        # 2b. Si venía de OPI y pasa a otro método, restablecer los campos residuales de OPI
        if metodo_anterior == "OPI" and code != "OPI":
            vals.update({
                "h2h_opi_chrgbr": "DEBT",
                "h2h_opi_purp_code": "CINV",
                "h2h_opi_reg_code": "01",
                "h2h_opi_referencia_larga": False,
            })

        # 3. Si pasa a Nómina y ya existen líneas capturadas con importe, sincronizar el total
        if code == "NOMINA" and self.h2h_nomina_line_ids:
            total_nomina = sum(self.h2h_nomina_line_ids.mapped("amount"))
            if total_nomina > 0:
                vals["amount"] = total_nomina

        # Registrar en el chatter el cambio de método si ya había uno seleccionado
        if metodo_anterior and metodo_anterior != code:
            self.message_post(
                body=Markup(
                    "Método de pago H2H cambiado de <b>{}</b> a <b>{}</b>. "
                    "Se actualizaron los campos del formulario para el nuevo método."
                ).format(metodo_anterior, code)
            )

        self.write(vals)
        self._compute_h2h_method_code()

    # =========================================================================
    # Acción 1 — Generar XML
    # =========================================================================
    def action_h2h_generate_xml(self):
        """
        Valida los datos, genera el XML pain.001 y lo guarda como adjunto.
        Disponible en borrador o confirmado. No altera el estado del pago a pagado.
        Valida la estructura XML antes de marcar como listo.
        Cambia h2h_state a 'xml_generated'.
        """
        self.ensure_one()

        if self.state == "cancel":
            raise UserError("No se puede generar un archivo XML para un pago cancelado.")

        if not self.is_hsbc_journal:
            raise UserError(
                "Solo se genera XML para pagos a proveedores (salientes) "
                "en un diario con HSBC H2H habilitado."
            )

        if self.h2h_state not in ("draft", "method_selected"):
            if self.h2h_state in H2H_ESTADOS_EN_BANCO:
                raise UserError(
                    "Este pago ya se envió a HSBC. No se puede generar otro XML, "
                    "porque enviarlo de nuevo duplicaría el pago."
                )
            if self.h2h_state == "rejected":
                raise UserError(
                    "HSBC rechazó este pago. Restablézcalo a borrador, corrija los datos "
                    "y vuelva a generar el XML."
                )
            raise UserError(
                "El XML de este pago ya está generado y vigente. Puede descargarlo o enviarlo a HSBC; "
                "si cambia algún dato del pago, se habilitará generarlo de nuevo."
            )

        if not self.h2h_method:
            raise UserError("Selecciona un método de pago HSBC antes de generar el XML.")

        # Delegar la generación al generador registrado para este método
        from ..generators.registry import get_generator
        generator = get_generator(self.h2h_method.code)
        xml_bytes = generator.generate(self)

        # ── Validación estructural del XML generado ────────────────────────────
        self._validar_xml_generado(xml_bytes, self.h2h_method.code)

        # Nombre seguro para el adjunto
        safe_name = (self.name or f"Draft_{self.id}").replace("/", "_")
        attachment_name = f"H2H_{self.h2h_method.code}_{safe_name}.xml"

        # Crear nuevo adjunto XML (se conserva cualquier archivo previo en el historial)

        attachment = self.env["ir.attachment"].create({
            "name": attachment_name,
            "type": "binary",
            "datas": base64.b64encode(xml_bytes),
            "res_model": "account.payment",
            "res_id": self.id,
            "mimetype": "application/xml",
        })

        self.write({
            "h2h_state": "xml_generated",
            "h2h_xml_attachment_id": attachment.id,
        })

        # Si es nómina, vincular el XML a cada una de las líneas de empleado
        if self.h2h_method_code == "NOMINA" and self.h2h_nomina_line_ids:
            self.h2h_nomina_line_ids.write({
                "xml_attachment_id": attachment.id,
                "validation_status": "valid",
                "error_details": "XML de nómina generado y validado exitosamente.",
            })

        self.message_post(
            body=Markup(
                "<b>XML {} generado y validado correctamente.</b><br/>"
                "Archivo: <i>{}</i><br/>"
                "Puede descargarlo desde los adjuntos o usando el botón Descargar XML."
            ).format(self.h2h_method.name, attachment_name),
        )

        # Devolvemos notificación sin recarga disruptiva
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "XML generado y validado",
                "message": (
                    f"El archivo {attachment_name} fue generado, validado y guardado como adjunto. "
                    f"Use el botón 'Descargar XML' para obtenerlo."
                ),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    # =========================================================================
    # Validación estructural del XML generado
    # =========================================================================
    @staticmethod
    def _validar_xml_generado(xml_bytes: bytes, method_code: str) -> None:
        """
        Valida que el XML generado tenga una estructura bien formada
        y que contenga las etiquetas mínimas requeridas por HSBC H2H.
        """
        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError as e:
            raise UserError(
                f"El XML generado para {method_code} no es válido (mal formado):\n{e}\n\n"
                f"Esto indica un error en el generador. Contacte al administrador del sistema."
            )

        ns = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"
        if not (root.tag == "Document" or root.tag == f"{{{ns}}}Document"):
            raise UserError(
                f"El XML generado para {method_code} no tiene la etiqueta raíz 'Document' "
                f"con el namespace ISO 20022 correcto.\n"
                f"Etiqueta encontrada: {root.tag}"
            )

        def find_tag(parent, tag_name):
            node = parent.find(tag_name)
            if node is None:
                node = parent.find(f"{{{ns}}}{tag_name}")
            return node

        cstmr = find_tag(root, "CstmrCdtTrfInitn")
        if cstmr is None:
            raise UserError(
                f"El XML {method_code} no contiene la etiqueta 'CstmrCdtTrfInitn'. "
                f"La estructura pain.001.001.03 es inválida."
            )

        grp_hdr = find_tag(cstmr, "GrpHdr")
        if grp_hdr is None:
            raise UserError(
                f"El XML {method_code} no contiene 'GrpHdr' dentro de 'CstmrCdtTrfInitn'."
            )

        # Campos obligatorios del GrpHdr
        campos_grphdr = ["MsgId", "CreDtTm", "NbOfTxs", "CtrlSum"]
        for campo in campos_grphdr:
            nodo = find_tag(grp_hdr, campo)
            if nodo is None or not (nodo.text or "").strip():
                raise UserError(
                    f"El XML {method_code} no contiene o tiene vacío el campo "
                    f"obligatorio GrpHdr/{campo}."
                )

        pmt_inf = find_tag(cstmr, "PmtInf")
        if pmt_inf is None:
            raise UserError(
                f"El XML {method_code} no contiene 'PmtInf'. "
                f"La estructura pain.001.001.03 es inválida."
            )

        campos_pmtinf = ["PmtInfId", "PmtMtd", "ReqdExctnDt"]
        for campo in campos_pmtinf:
            nodo = find_tag(pmt_inf, campo)
            if nodo is None or not (nodo.text or "").strip():
                raise UserError(
                    f"El XML {method_code} no contiene o tiene vacío el campo "
                    f"obligatorio PmtInf/{campo}."
                )

        cdt_trf = find_tag(pmt_inf, "CdtTrfTxInf")
        if cdt_trf is None:
            raise UserError(
                f"El XML {method_code} no contiene ninguna instrucción 'CdtTrfTxInf'."
            )

        AccountPayment._validar_xml_por_metodo(root, cstmr, pmt_inf, cdt_trf,
                                               method_code, ns)

    @staticmethod
    def _validar_xml_por_metodo(root, cstmr, pmt_inf, cdt_trf,
                                method_code: str, ns: str) -> None:
        """
        Validaciones adicionales específicas de cada tipo de pago.
        """
        def find_tag(parent, tag_name):
            node = parent.find(tag_name)
            if node is None:
                node = parent.find(f"{{{ns}}}{tag_name}")
            return node

        def get_text(parent, tag_name) -> str:
            node = find_tag(parent, tag_name)
            return (node.text or "").strip() if node is not None else ""

        # ── SPEI ──────────────────────────────────────────────────────────────
        if method_code == "SPEI":
            pmt_tp = find_tag(pmt_inf, "PmtTpInf")
            if pmt_tp is not None:
                svc_lvl = find_tag(pmt_tp, "SvcLvl")
                if svc_lvl is not None:
                    cd = get_text(svc_lvl, "Cd")
                    if cd != "URGP":
                        raise UserError(
                            f"SPEI requiere SvcLvl/Cd = 'URGP'. Valor encontrado: '{cd}'."
                        )
            amt = find_tag(cdt_trf, "Amt")
            if amt is not None:
                instd = find_tag(amt, "InstdAmt")
                if instd is not None and instd.get("Ccy") != "MXN":
                    raise UserError(
                        f"SPEI requiere moneda MXN. Moneda encontrada: '{instd.get('Ccy')}'."
                    )

        # ── NOMINA ─────────────────────────────────────────────────────────────
        elif method_code == "NOMINA":
            pmt_tp = find_tag(pmt_inf, "PmtTpInf")
            if pmt_tp is not None:
                svc_lvl = find_tag(pmt_tp, "SvcLvl")
                if svc_lvl is not None:
                    cd = get_text(svc_lvl, "Cd")
                    if cd != "NURG":
                        raise UserError(
                            f"Nómina HSBC requiere SvcLvl/Cd = 'NURG'. Valor encontrado: '{cd}'."
                        )
                ctgy = find_tag(pmt_tp, "CtgyPurp")
                if ctgy is None:
                    raise UserError(
                        "Nómina HSBC requiere CtgyPurp/Cd = 'SALA' en PmtTpInf. "
                        "Este campo identifica el pago como nómina ante HSBC."
                    )
                else:
                    cd_ctgy = get_text(ctgy, "Cd")
                    if cd_ctgy != "SALA":
                        raise UserError(
                            f"Nómina HSBC requiere CtgyPurp/Cd = 'SALA'. "
                            f"Valor encontrado: '{cd_ctgy}'."
                        )
            pmt_id = find_tag(cdt_trf, "PmtId")
            if pmt_id is not None:
                instr_id = get_text(pmt_id, "InstrId")
                if "NOMINA" not in instr_id.upper():
                    raise UserError(
                        f"Nómina HSBC requiere que InstrId contenga la palabra 'NOMINA'. "
                        f"Valor encontrado: '{instr_id}'."
                    )

        # ── SERVICIOS ──────────────────────────────────────────────────────────
        elif method_code == "SERVICIOS":
            pmt_tp = find_tag(pmt_inf, "PmtTpInf")
            if pmt_tp is not None:
                svc_lvl = find_tag(pmt_tp, "SvcLvl")
                if svc_lvl is not None:
                    cd = get_text(svc_lvl, "Cd")
                    if cd != "NURG":
                        raise UserError(
                            f"Servicios HSBC requiere SvcLvl/Cd = 'NURG'. "
                            f"Valor encontrado: '{cd}'."
                        )

        # ── OPI ───────────────────────────────────────────────────────────────
        elif method_code == "OPI":
            pmt_tp = find_tag(pmt_inf, "PmtTpInf")
            if pmt_tp is not None:
                svc_lvl = find_tag(pmt_tp, "SvcLvl")
                if svc_lvl is not None:
                    cd = get_text(svc_lvl, "Cd")
                    if cd != "URGP":
                        raise UserError(
                            f"OPI requiere SvcLvl/Cd = 'URGP'. Valor encontrado: '{cd}'."
                        )
            amt = find_tag(cdt_trf, "Amt")
            if amt is not None:
                instd = find_tag(amt, "InstdAmt")
                if instd is not None and instd.get("Ccy") == "MXN":
                    raise UserError("OPI requiere moneda extranjera. No se permite MXN.")
            if find_tag(cdt_trf, "ChrgBr") is None:
                raise UserError("OPI requiere el elemento ChrgBr (DEBT).")
            if find_tag(cdt_trf, "RgltryRptg") is None:
                raise UserError(
                    "OPI requiere el elemento RgltryRptg con el propósito regulatorio. "
                    "El XML OPI está incompleto."
                )

        # ── SPID ──────────────────────────────────────────────────────────────
        elif method_code == "SPID":
            amt = find_tag(cdt_trf, "Amt")
            if amt is not None:
                instd = find_tag(amt, "InstdAmt")
                if instd is not None and instd.get("Ccy") != "USD":
                    raise UserError(
                        f"SPID requiere moneda USD. Moneda encontrada: '{instd.get('Ccy')}'."
                    )
            rgltryrptg = find_tag(cdt_trf, "RgltryRptg")
            if rgltryrptg is None:
                raise UserError(
                    "SPID requiere el elemento RgltryRptg con el código de operación. "
                    "El XML SPID está incompleto."
                )
            dtls = find_tag(rgltryrptg, "Dtls")
            if dtls is not None:
                inf = get_text(dtls, "Inf")
                if not inf.startswith("/SPID/OC/"):
                    raise UserError(
                        f"SPID requiere RgltryRptg/Dtls/Inf con formato '/SPID/OC/{{codigo}}'. "
                        f"Valor encontrado: '{inf}'."
                    )
            tax = find_tag(cdt_trf, "Tax")
            if tax is None:
                raise UserError(
                    "SPID requiere el elemento Tax con el RFC del beneficiario. "
                    "El XML SPID está incompleto."
                )
            cdtr_tax = find_tag(tax, "Cdtr")
            if cdtr_tax is not None:
                tax_id = get_text(cdtr_tax, "TaxId")
                if not tax_id:
                    raise UserError(
                        "SPID requiere Tax/Cdtr/TaxId (RFC del beneficiario) con valor. "
                        "El XML SPID está incompleto."
                    )

    # =========================================================================
    # Acción auxiliar — Descargar XML (sin cambiar estado)
    # =========================================================================
    def action_h2h_descargar_xml(self):
        """Descarga el XML adjunto sin modificar el estado H2H."""
        self.ensure_one()
        if not self.h2h_xml_attachment_id:
            raise UserError("No hay XML generado para este pago. Use 'Generar XML HSBC' primero.")
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{self.h2h_xml_attachment_id.id}?download=true",
            "target": "new",
        }

    # =========================================================================
    # Acción 2 — Enviar a HSBC (simulación)
    # =========================================================================
    def action_h2h_send_to_bank(self):
        """
        Simula el envío del XML a HSBC H2H.
        Fase 1 (actual): simulación — muestra mensaje de éxito y cambia estado.
        Fase 2 (futuro): conexión real por SFTP/API a HSBC.
        """
        self.ensure_one()

        if self.h2h_state != "xml_generated":
            raise UserError(
                "Primero debe generar el XML antes de enviarlo.\n"
                "Use el botón 'Generar XML HSBC'."
            )

        if not self.h2h_xml_attachment_id:
            raise UserError(
                "No se encontró el XML adjunto. "
                "Genere el XML nuevamente con el botón 'Generar XML HSBC'."
            )

        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ref_simulada = f"HSBC-SIM-{self.id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"
        metodo = self.h2h_method.name if self.h2h_method else "H2H"

        self.write({"h2h_state": "sent_to_bank"})

        self.message_post(
            body=Markup(
                "<b>XML enviado a HSBC H2H (simulación).</b><br/>"
                "<br/>"
                "<b>Método:</b> {}<br/>"
                "<b>Referencia de transmisión:</b> {}<br/>"
                "<b>Fecha/hora:</b> {}<br/>"
                "<b>Archivo:</b> {}<br/>"
                "<b>Canal:</b> HSBC H2H / pain.001.001.03<br/>"
                "<b>Estado en banco:</b> Instrucción recibida — en cola de procesamiento<br/>"
                "<br/>"
                "<i>Aviso: Este es un envío simulado. "
                "Cuando se configure la conexión real (SFTP/API), "
                "este paso transmitirá el archivo automáticamente a HSBC.</i>"
            ).format(metodo, ref_simulada, timestamp, self.h2h_xml_attachment_id.name),
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Enviado a HSBC (simulacion)",
                "message": (
                    f"Referencia: {ref_simulada}. "
                    f"El pago quedo en estado 'Enviado a HSBC'. "
                    f"Use 'HSBC: Confirmar pago' cuando el banco procese la operacion."
                ),
                "type": "success",
                "sticky": True,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    # =========================================================================
    # Acción 3a — Confirmar recepción bancaria
    # =========================================================================
    def action_h2h_confirm_accepted(self):
        """HSBC aceptó la instrucción. Marca el pago como pagado en Odoo."""
        self.ensure_one()

        if self.h2h_state != "sent_to_bank":
            raise UserError("Solo se puede confirmar un pago que ya fue enviado a HSBC.")
        self._h2h_exigir_pago_vigente()

        self.write({"h2h_state": "accepted"})
        self.message_post(
            body=Markup(
                "<b>HSBC confirmó la aceptación del pago.</b><br/>"
                "El pago fue procesado por el banco y se marca como Pagado en Odoo."
            ),
        )
        self.action_validate()

    def _h2h_exigir_pago_vigente(self):
        """El pago debe seguir vivo en Odoo para registrar la respuesta de HSBC."""
        self.ensure_one()
        if self.state in ("canceled", "rejected"):
            estado = dict(self._fields["state"]._description_selection(self.env))[self.state]
            raise UserError(
                f"El pago {self.name or ''} está en estado '{estado}' en Odoo, "
                "así que no se puede registrar la respuesta de HSBC sobre él. "
                "Revise con el banco qué pasó con la instrucción enviada."
            )

    # =========================================================================
    # Acción 3b — Registrar rechazo bancario
    # =========================================================================
    def action_h2h_confirm_rejected(self):
        """
        HSBC rechazó la instrucción: el dinero nunca salió del banco.
        Se deshace el cruce con las facturas y se cancela el asiento del pago,
        para que las facturas regresen a "Sin pagar" y puedan pagarse de nuevo.
        """
        self.ensure_one()

        if self.h2h_state != "sent_to_bank":
            raise UserError("Solo se puede registrar rechazo de un pago que fue enviado a HSBC.")
        self._h2h_exigir_pago_vigente()

        facturas = self.reconciled_bill_ids | self.reconciled_invoice_ids
        asiento = self.move_id
        if asiento:
            # button_draft quita la conciliación con las facturas; luego se cancela el asiento.
            if asiento.state == "posted":
                asiento.button_draft()
            if asiento.state == "draft":
                asiento.button_cancel()

        self.write({"h2h_state": "rejected"})
        self.action_reject()

        nombres = ", ".join(facturas.mapped("name")) or "ninguna"
        self.message_post(
            body=Markup(
                "<b>HSBC rechazó el pago.</b><br/>"
                "Se canceló el asiento del pago y se liberó la factura ({}), "
                "que regresa a 'Sin pagar'.<br/>"
                "Revise los datos del beneficiario (CLABE, nombre) y registre un pago nuevo."
            ).format(nombres),
        )

    # =========================================================================
    # Restablecer a borrador / Cancelar
    # =========================================================================
    def _h2h_bloquear_si_en_banco(self, accion):
        """
        Un pago que ya está en HSBC no se puede regresar a borrador ni cancelar en Odoo:
        reabriría los botones de generar y enviar (pago duplicado) o dejaría el pago
        cancelado en Odoo mientras el banco lo procesa.
        """
        for pago in self:
            if pago.h2h_state == "sent_to_bank":
                raise UserError(
                    f"El pago {pago.name or ''} ya se envió a HSBC y está esperando respuesta del banco, "
                    f"así que no se puede {accion}.\n\n"
                    "Primero registre la respuesta con 'HSBC: Confirmar pago' o 'HSBC: Registrar rechazo'."
                )
            if pago.h2h_state == "accepted":
                raise UserError(
                    f"HSBC ya aceptó el pago {pago.name or ''}: el dinero salió de la cuenta, "
                    f"así que no se puede {accion}, porque permitiría enviarlo otra vez.\n\n"
                    "Si hay que revertirlo, gestione la devolución con el proveedor y regístrela "
                    "como un movimiento aparte."
                )

    def action_cancel(self):
        self._h2h_bloquear_si_en_banco("cancelar")
        return super().action_cancel()

    def action_draft(self):
        """Al restablecer a borrador, desbloquea la edición del método H2H."""
        self._h2h_bloquear_si_en_banco("restablecer a borrador")
        res = super().action_draft()
        for rec in self:
            if rec.is_hsbc_journal and rec.h2h_state not in ("draft", "method_selected"):
                rec.h2h_state = "method_selected" if rec.h2h_method else "draft"
        return res

