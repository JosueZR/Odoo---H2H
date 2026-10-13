# -*- coding: utf-8 -*-
import base64
import xml.etree.ElementTree as ET
from odoo import models, fields, api
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    # ── Valores por defecto para inicialización al crear un pago nuevo ────────
    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        # Si no se especificó diario o el diario no es HSBC, pero existe un diario HSBC H2H en la compañía,
        # sugerirlo para que los cuadros H2H aparezcan inmediatamente desde que se abre el formulario.
        company_id = res.get("company_id") or self.env.company.id
        current_journal_id = res.get("journal_id")
        hsbc_journal = None

        if current_journal_id:
            journal = self.env["account.journal"].browse(current_journal_id)
            if journal.is_h2h_enabled:
                hsbc_journal = journal

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
        string="Es diario HSBC H2H",
        compute="_compute_is_hsbc_journal",
        store=False,
    )

    @api.depends("journal_id", "journal_id.is_h2h_enabled")
    def _compute_is_hsbc_journal(self):
        for rec in self:
            rec.is_hsbc_journal = bool(rec.journal_id and rec.journal_id.is_h2h_enabled)

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
        help="Método H2H seleccionado: SPEI, SPID, Nómina, Servicios.",
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
        # 1. Moneda adecuada según el nuevo método
        if code == "SPID":
            # SPID opera en USD
            moneda_usd = self.env["res.currency"].search([("name", "=", "USD")], limit=1)
            if moneda_usd:
                vals["currency_id"] = moneda_usd.id
        elif metodo_anterior == "SPID" and code in ("SPEI", "NOMINA", "SERVICIOS"):
            # Si venía de SPID (USD) y pasa a un método nacional, ajustar a MXN
            moneda_mxn = self.env["res.currency"].search([("name", "=", "MXN")], limit=1)
            if moneda_mxn:
                vals["currency_id"] = moneda_mxn.id

        # 2. Si venía de SPID y pasa a otro método, limpiar campos residuales de SPID
        if metodo_anterior == "SPID" and code != "SPID":
            vals.update({
                "h2h_spid_codigo": False,
                "h2h_spid_rfc": False,
                "h2h_spid_referencia_larga": False,
            })

        # 3. Si pasa a Nómina y ya existen líneas capturadas con importe, sincronizar el total
        if code == "NOMINA" and self.h2h_nomina_line_ids:
            total_nomina = sum(self.h2h_nomina_line_ids.mapped("amount"))
            if total_nomina > 0:
                vals["amount"] = total_nomina

        # Registrar en el chatter el cambio de método si ya había uno seleccionado
        if metodo_anterior and metodo_anterior != code:
            self.message_post(
                body=(
                    f"Método de pago H2H cambiado de <b>{metodo_anterior}</b> a <b>{code}</b>. "
                    f"Se actualizaron los campos del formulario para el nuevo método."
                )
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
            raise UserError("Este pago no pertenece a un diario con HSBC H2H habilitado.")

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
            body=(
                f"<b>XML {self.h2h_method.name} generado y validado correctamente.</b><br/>"
                f"Archivo: <i>{attachment_name}</i><br/>"
                f"Puede descargarlo desde los adjuntos o usando el botón Descargar XML."
            ),
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
            body=(
                f"<b>XML enviado a HSBC H2H (simulacion).</b><br/>"
                f"<br/>"
                f"<b>Metodo:</b> {metodo}<br/>"
                f"<b>Referencia de transmision:</b> {ref_simulada}<br/>"
                f"<b>Fecha/hora:</b> {timestamp}<br/>"
                f"<b>Archivo:</b> {self.h2h_xml_attachment_id.name}<br/>"
                f"<b>Canal:</b> HSBC H2H / pain.001.001.03<br/>"
                f"<b>Estado en banco:</b> Instruccion recibida — en cola de procesamiento<br/>"
                f"<br/>"
                f"<i>Aviso: Este es un envio simulado. "
                f"Cuando se configure la conexion real (SFTP/API), "
                f"este paso transmitira el archivo automaticamente a HSBC.</i>"
            ),
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

        self.write({"h2h_state": "accepted"})
        self.message_post(
            body=(
                "<b>HSBC confirmo la aceptacion del pago.</b><br/>"
                "El pago fue procesado por el banco y se marca como Pagado en Odoo."
            ),
        )
        self.action_validate()

    # =========================================================================
    # Acción 3b — Registrar rechazo bancario
    # =========================================================================
    def action_h2h_confirm_rejected(self):
        """HSBC rechazó la instrucción."""
        self.ensure_one()

        if self.h2h_state != "sent_to_bank":
            raise UserError("Solo se puede registrar rechazo de un pago que fue enviado a HSBC.")

        self.write({"h2h_state": "rejected"})
        self.message_post(
            body=(
                "<b>HSBC rechazo el pago.</b><br/>"
                "Revise los datos del beneficiario (CLABE, nombre) y regenere el XML."
            ),
        )
        self.action_reject()

    # =========================================================================
    # Restablecer a borrador
    # =========================================================================
    def action_draft(self):
        """Al restablecer a borrador, desbloquea la edición del método H2H."""
        res = super().action_draft()
        for rec in self:
            if rec.is_hsbc_journal and rec.h2h_state not in ("draft", "method_selected"):
                rec.h2h_state = "method_selected" if rec.h2h_method else "draft"
        return res

