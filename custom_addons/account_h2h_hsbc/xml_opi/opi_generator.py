# -*- coding: utf-8 -*-
"""
Generador XML OPI (Orden de Pago Internacional / Cross Border) para HSBC H2H.
Implementa BaseH2HGenerator y produce un archivo pain.001.001.03 en moneda extranjera.

Portado del script de pruebas 'Generar XML Pago OPI.py' (validado contra HSBC 09/2026).
Los datos salen de Odoo en lugar de diccionarios y contadores en archivos .txt:
  - Beneficiario ........ partner_id (nombre, calle, CP, ciudad, país)
  - Banco beneficiario .. partner_bank_id.bank_id.bic
  - Cuenta beneficiaria . partner_bank_id.acc_number (IBAN si acc_type == 'iban')
  - Cliente HSBC ........ journal_id.hsbc_client_id
  - Campos propios OPI .. h2h_opi_chrgbr, h2h_opi_purp_code, h2h_opi_reg_code,
                          h2h_opi_referencia_larga
"""
import xml.etree.ElementTree as ET
from xml.dom import minidom
from decimal import Decimal
from datetime import datetime

from ..generators.base_generator import BaseH2HGenerator
from .constants import (
    XML_NAMESPACE, XML_NAMESPACE_XSI,
    PMT_MTD, SVC_LVL_CODE, COUNTRY, BIC_DEFAULT,
    USTRD_MAX_LENGTH, RGLTRY_PREFIJO, RGLTRY_ANTES_DE_PURP,
)
from .opi_validator import (
    validar_pago_opi, validar_xml_opi,
    texto_swift, referencia_opi,
    obtener_bic_beneficiario, obtener_cuenta_beneficiario, obtener_pais_beneficiario,
)


class OpiGenerator(BaseH2HGenerator):
    """
    Generador XML para pagos OPI (Cross Border).

    Campos adicionales en account.payment requeridos por OPI:
    - h2h_opi_chrgbr            — Quién paga comisiones (DEBT/CRED/SHAR).
    - h2h_opi_purp_code         — Propósito ISO global (CINV, GDDS, ...).
    - h2h_opi_reg_code          — Propósito regulatorio 01..22.
    - h2h_opi_referencia_larga  — Texto libre para RmtInf/Ustrd (máx. 140).
    """

    METHOD_CODE = "OPI"

    # =========================================================================
    def validate(self, payment) -> None:
        """Delega al validador dedicado de OPI."""
        validar_pago_opi(payment)

    # =========================================================================
    def generate(self, payment) -> bytes:
        """
        Genera el XML pain.001.001.03 para pago OPI HSBC.
        Devuelve bytes UTF-8 listos para guardar o enviar.
        """
        self.validate(payment)

        # ── Datos del ordenante (empresa) ─────────────────────────────────────
        company   = payment.company_id
        journal   = payment.journal_id
        safe_name = self._get_safe_name(payment)
        now       = datetime.now()

        # MsgId: Max35Text. Incluye id del pago + timestamp para no repetirse.
        msg_id     = f"OPI-{payment.id}-{now.strftime('%Y%m%d%H%M%S')}"[:35]
        fecha_hora = now.strftime("%Y-%m-%dT%H:%M:%S")
        fecha_ejec = str(payment.date or now.strftime("%Y-%m-%d"))
        client_id  = journal.hsbc_client_id or ""
        bic_ord    = journal.hsbc_bic or BIC_DEFAULT
        cuenta_ord = journal.bank_account_id.acc_number or ""

        # ── Datos del beneficiario ────────────────────────────────────────────
        partner        = payment.partner_id
        bic_ben        = obtener_bic_beneficiario(payment)
        tipo_cta, cta  = obtener_cuenta_beneficiario(payment)
        pais_ben       = obtener_pais_beneficiario(payment)
        monto          = Decimal(str(payment.amount))
        moneda         = payment.currency_id.name

        chrgbr    = payment.h2h_opi_chrgbr
        purp_code = payment.h2h_opi_purp_code
        reg_code  = payment.h2h_opi_reg_code
        ref_larga = texto_swift(getattr(payment, "h2h_opi_referencia_larga", None)
                                or getattr(payment, "memo", None) or "")[:USTRD_MAX_LENGTH]

        ref_pago = safe_name
        ref_tx   = referencia_opi(safe_name, now.strftime("%Y%m%d"))

        # ── Construcción del árbol XML ────────────────────────────────────────
        document = ET.Element("Document", {
            "xmlns:xsi": XML_NAMESPACE_XSI,
            "xmlns":     XML_NAMESPACE,
        })
        cstmr = ET.SubElement(document, "CstmrCdtTrfInitn")

        # GrpHdr
        grp = ET.SubElement(cstmr, "GrpHdr")
        ET.SubElement(grp, "MsgId").text   = msg_id
        ET.SubElement(grp, "CreDtTm").text = fecha_hora
        ET.SubElement(grp, "NbOfTxs").text = "1"
        ET.SubElement(grp, "CtrlSum").text = f"{monto:.2f}"
        initg = ET.SubElement(grp, "InitgPty")
        othr  = ET.SubElement(ET.SubElement(ET.SubElement(initg, "Id"), "OrgId"), "Othr")
        ET.SubElement(othr, "Id").text = client_id

        # PmtInf
        ptm = ET.SubElement(cstmr, "PmtInf")
        ET.SubElement(ptm, "PmtInfId").text = ref_pago
        ET.SubElement(ptm, "PmtMtd").text   = PMT_MTD
        svc_lvl = ET.SubElement(ET.SubElement(ptm, "PmtTpInf"), "SvcLvl")
        ET.SubElement(svc_lvl, "Cd").text = SVC_LVL_CODE  # URGP
        ET.SubElement(ptm, "ReqdExctnDt").text = fecha_ejec

        # Ordenante (empresa en México)
        dbtr = ET.SubElement(ptm, "Dbtr")
        ET.SubElement(dbtr, "Nm").text = texto_swift(company.name)
        pstl_ord = ET.SubElement(dbtr, "PstlAdr")
        ET.SubElement(pstl_ord, "StrtNm").text = texto_swift(company.street)
        ET.SubElement(pstl_ord, "PstCd").text  = company.zip or ""
        ET.SubElement(pstl_ord, "TwnNm").text  = texto_swift(company.city)
        ET.SubElement(pstl_ord, "Ctry").text   = COUNTRY

        # Cuenta ordenante
        othr_d = ET.SubElement(ET.SubElement(ET.SubElement(ptm, "DbtrAcct"), "Id"), "Othr")
        ET.SubElement(othr_d, "Id").text = cuenta_ord

        # Banco ordenante (BIC, porque es pago internacional)
        fi_id = ET.SubElement(ET.SubElement(ptm, "DbtrAgt"), "FinInstnId")
        ET.SubElement(fi_id, "BIC").text = bic_ord
        ET.SubElement(ET.SubElement(fi_id, "PstlAdr"), "Ctry").text = COUNTRY

        # ── Instrucción de transferencia ──────────────────────────────────────
        cdt    = ET.SubElement(ptm, "CdtTrfTxInf")
        pmt_id = ET.SubElement(cdt, "PmtId")
        ET.SubElement(pmt_id, "InstrId").text    = ref_tx
        ET.SubElement(pmt_id, "EndToEndId").text = ref_tx

        # Monto y moneda (la moneda varía por pago; nunca MXN)
        instd = ET.SubElement(ET.SubElement(cdt, "Amt"), "InstdAmt")
        instd.set("Ccy", moneda)
        instd.text = f"{monto:.2f}"

        # Quién paga las comisiones
        ET.SubElement(cdt, "ChrgBr").text = chrgbr

        # Banco beneficiario: BIC del banco extranjero
        fi_id2 = ET.SubElement(ET.SubElement(cdt, "CdtrAgt"), "FinInstnId")
        ET.SubElement(fi_id2, "BIC").text = bic_ben
        ET.SubElement(ET.SubElement(fi_id2, "PstlAdr"), "Ctry").text = pais_ben

        # Beneficiario (con código postal, pedido por HSBC 09/2026)
        cdtr = ET.SubElement(cdt, "Cdtr")
        ET.SubElement(cdtr, "Nm").text = texto_swift(partner.name)
        pstl_ben = ET.SubElement(cdtr, "PstlAdr")
        ET.SubElement(pstl_ben, "StrtNm").text = texto_swift(partner.street)
        ET.SubElement(pstl_ben, "PstCd").text  = (partner.zip or "").strip()
        ET.SubElement(pstl_ben, "TwnNm").text  = texto_swift(partner.city)
        ET.SubElement(pstl_ben, "Ctry").text   = pais_ben

        # Cuenta beneficiaria: IBAN si aplica, si no número de cuenta normal
        acct_id2 = ET.SubElement(ET.SubElement(cdt, "CdtrAcct"), "Id")
        if tipo_cta == "IBAN":
            ET.SubElement(acct_id2, "IBAN").text = cta
        else:
            ET.SubElement(ET.SubElement(acct_id2, "Othr"), "Id").text = cta

        # ── RgltryRptg y Purp ─────────────────────────────────────────────────
        # Orden configurable en constants.RGLTRY_ANTES_DE_PURP (ver nota allí).
        def _agregar_rgltry():
            rg = ET.SubElement(cdt, "RgltryRptg")
            dt = ET.SubElement(rg, "Dtls")
            ET.SubElement(dt, "Inf").text = f"{RGLTRY_PREFIJO}{reg_code}"

        def _agregar_purp():
            ET.SubElement(ET.SubElement(cdt, "Purp"), "Cd").text = purp_code

        if RGLTRY_ANTES_DE_PURP:
            _agregar_rgltry()
            _agregar_purp()
        else:
            _agregar_purp()
            _agregar_rgltry()

        # Referencia / concepto
        if ref_larga:
            ET.SubElement(ET.SubElement(cdt, "RmtInf"), "Ustrd").text = ref_larga

        # ── Serializar con formato bonito ─────────────────────────────────────
        raw    = ET.tostring(document, encoding="UTF-8")
        pretty = minidom.parseString(raw).toprettyxml(indent="    ", encoding="UTF-8")

        # HSBC requiere espacio antes del ?> en la declaración XML
        pretty = pretty.replace(
            b'<?xml version="1.0" encoding="UTF-8"?>',
            b'<?xml version="1.0" encoding="UTF-8" ?>',
            1,
        )

        # Validación estructural del XML ya generado
        validar_xml_opi(pretty)

        return pretty
