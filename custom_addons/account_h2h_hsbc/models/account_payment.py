# -*- coding: utf-8 -*-
import base64
from odoo import models, fields, api
from odoo.exceptions import UserError


class AccountPayment(models.Model):
    _inherit = "account.payment"

    # ── Detección de diario HSBC ──────────────────────────────────────────────
    is_hsbc_journal = fields.Boolean(
        string="Es diario HSBC H2H",
        compute="_compute_is_hsbc_journal",
        store=False,
    )

    @api.depends("journal_id", "journal_id.is_h2h_enabled")
    def _compute_is_hsbc_journal(self):
        for rec in self:
            rec.is_hsbc_journal = bool(rec.journal_id.is_h2h_enabled)

    @api.onchange("journal_id")
    def _onchange_journal_h2h(self):
        """
        Cuando se selecciona un diario HSBC H2H, auto-selecciona
        el primer método disponible (actualmente SPEI).
        Cuando se cambia a un diario no-HSBC, limpia el método.
        """
        if self.journal_id.is_h2h_enabled:
            metodo_spei = self.env["h2h.payment.method"].search(
                [("code", "=", "SPEI"), ("is_available", "=", True)], limit=1
            )
            self.h2h_method = metodo_spei or False
            if metodo_spei:
                self.h2h_state = "method_selected"
        else:
            self.h2h_method = False
            self.h2h_state = "draft"

    # ── Estado interno H2H (no toca el state de Odoo) ────────────────────────
    h2h_state = fields.Selection(
        selection=[
            ("draft",           "Sin iniciar"),
            ("method_selected", "Método seleccionado"),
            ("xml_generated",   "XML generado"),
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
        help="Método H2H seleccionado: SPEI, SPID, etc.",
    )

    # ── Campo auxiliar para la vista ─────────────────────────────────────────
    h2h_xml_attachment_id = fields.Many2one(
        comodel_name="ir.attachment",
        string="XML H2H generado",
        copy=False,
        readonly=True,
    )

    # =========================================================================
    # Acción 1 — Generar XML
    # =========================================================================
    def action_h2h_generate_xml(self):
        """
        Valida los datos, genera el XML pain.001 y lo guarda como adjunto.
        Cambia h2h_state a 'xml_generated'.
        """
        self.ensure_one()

        if not self.is_hsbc_journal:
            raise UserError("Este pago no pertenece a un diario con HSBC H2H habilitado.")

        if self.state != "in_process":
            raise UserError("El pago debe estar confirmado (En proceso) antes de generar el XML.")

        if not self.h2h_method:
            raise UserError("Selecciona un método de pago HSBC antes de generar el XML.")

        # Delegar la generación al generador registrado para este método
        from ..generators.registry import get_generator
        generator = get_generator(self.h2h_method.code)
        xml_bytes = generator.generate(self)

        # Nombre seguro para el adjunto
        safe_name = (self.name or f"Draft_{self.id}").replace("/", "_")
        attachment_name = f"H2H_{self.h2h_method.code}_{safe_name}.xml"

        # Eliminar adjunto anterior si existe para evitar duplicados
        if self.h2h_xml_attachment_id:
            self.h2h_xml_attachment_id.unlink()

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

        self.message_post(
            body=(
                f"✅ <b>XML {self.h2h_method.name} generado correctamente.</b><br/>"
                f"Archivo: <i>{attachment_name}</i><br/>"
                f"Puedes descargarlo desde los adjuntos o usando el botón "
                f"<b>Descargar XML</b>."
            ),
        )

        # ── IMPORTANTE: devolvemos una notificación, NO un act_url con
        # target='self'. El act_url con target='self' navegaba el browser
        # y el form no recargaba el campo h2h_state correctamente,
        # dejando los botones en estado incorrecto. ───────────────────────────
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "✅ XML generado",
                "message": (
                    f"El archivo {attachment_name} fue generado y guardado como adjunto. "
                    f"Usa el botón 'Descargar XML' para obtenerlo."
                ),
                "type": "success",
                "sticky": False,
                "next": {"type": "ir.actions.act_window_close"},
            },
        }

    # =========================================================================
    # Acción auxiliar — Descargar XML (sin cambiar estado)
    # =========================================================================
    def action_h2h_descargar_xml(self):
        """Descarga el XML adjunto sin modificar el estado H2H."""
        self.ensure_one()
        if not self.h2h_xml_attachment_id:
            raise UserError("No hay XML generado para este pago. Usa 'Generar XML HSBC' primero.")
        return {
            "type": "ir.actions.act_url",
            "url": f"/web/content/{self.h2h_xml_attachment_id.id}?download=true",
            "target": "new",   # abre en pestaña nueva: no afecta el form actual
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
                "Primero debes generar el XML antes de enviarlo.\n"
                "Usa el botón 'Generar XML HSBC'."
            )

        if not self.h2h_xml_attachment_id:
            raise UserError(
                "No se encontró el XML adjunto. "
                "Genera el XML nuevamente con el botón 'Generar XML HSBC'."
            )

        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ref_simulada = f"HSBC-SIM-{self.id}-{datetime.now().strftime('%Y%m%d%H%M%S')}"

        self.write({"h2h_state": "sent_to_bank"})

        self.message_post(
            body=(
                f"📤 <b>XML enviado a HSBC H2H (simulación).</b><br/>"
                f"<br/>"
                f"<b>Referencia de transmisión:</b> {ref_simulada}<br/>"
                f"<b>Fecha/hora:</b> {timestamp}<br/>"
                f"<b>Archivo:</b> {self.h2h_xml_attachment_id.name}<br/>"
                f"<b>Canal:</b> HSBC H2H / pain.001.001.03<br/>"
                f"<b>Estado en banco:</b> Instrucción recibida — en cola de procesamiento<br/>"
                f"<br/>"
                f"<i>⚠️ Este es un envío simulado. "
                f"Cuando se configure la conexión real (SFTP/API), "
                f"este paso transmitirá el archivo automáticamente a HSBC.</i>"
            ),
        )

        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "📤 Enviado a HSBC (simulación)",
                "message": (
                    f"Referencia: {ref_simulada}. "
                    f"El pago quedó en estado 'Enviado a HSBC'. "
                    f"Usa 'HSBC: Confirmar pago' cuando el banco procese la operación."
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
                "✅ <b>HSBC confirmó la aceptación del pago.</b><br/>"
                "El pago fue procesado por el banco y se marca como Pagado en Odoo."
            ),
        )
        # Llama el método público de Odoo: in_process → paid
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
                "❌ <b>HSBC rechazó el pago.</b><br/>"
                "Revisa los datos del proveedor (CLABE, nombre) y regenera el XML."
            ),
        )
        # Llama el método público de Odoo: in_process → rejected
        self.action_reject()
