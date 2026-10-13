# -*- coding: utf-8 -*-
"""
Generador XML SPID para HSBC H2H.
Implementa BaseH2HGenerator y produce un archivo pain.001.001.03 en USD.

Reglas específicas de SPID validadas por HSBC:
- SvcLvl: URGP (urgente).
- Moneda: USD.
- Banco beneficiario ≠ 021 (los primeros 3 dígitos de la CLABE = MmbId).
- EndToEndId: numérico, máximo 15 dígitos.
- RFC del beneficiario obligatorio (Tax/Cdtr/TaxId).
- Código de operación obligatorio (RgltryRptg/Dtls/Inf = "/SPID/OC/{Codigo}").
- Referencia larga (RmtInf/Ustrd): máximo 40 caracteres.
- Cuenta ordenante: 10 dígitos, inicia con "70".
"""
import xml.etree.ElementTree as ET
from xml.dom import minidom
from decimal import Decimal
from datetime import datetime

from ..generators.base_generator import BaseH2HGenerator
from .constants import (
    XML_NAMESPACE, XML_NAMESPACE_XSI,
    PMT_MTD, SVC_LVL_CODE,
    CURRENCY, COUNTRY, BIC_DEFAULT,
    USTRD_MAX_LENGTH,
)
from .spid_validator import validar_pago_spid, validar_xml_spid, referencia_end_to_end


class SpidGenerator(BaseH2HGenerator):
    """
    Generador XML para pagos SPID (Sistema de Pagos Interbancarios en Dólares).

    Campos adicionales en account.payment requeridos por SPID:
    - h2h_spid_rfc           — RFC del beneficiario (obligatorio).
    - h2h_spid_codigo        — Código de operación SPID (01-08, obligatorio).
    - h2h_spid_referencia_larga — Referencia al beneficiario, máx. 40 chars.
    """

    METHOD_CODE = "SPID"

    # =========================================================================
    def validate(self, payment) -> None:
        """Delega al validador dedicado de SPID."""
        validar_pago_spid(payment)

    # =========================================================================
    def generate(self, payment) -> bytes:
        """
        Genera el XML pain.001.001.03 para pago SPID HSBC.
        Devuelve bytes UTF-8 listos para guardar o enviar.
        """
        # Validar antes de construir
        self.validate(payment)

        # ── Datos del ordenante (empresa) ─────────────────────────────────────
        company    = payment.company_id
        journal    = payment.journal_id
        safe_name  = self._get_safe_name(payment)
        now        = datetime.now()

        msg_id      = f"HSBC-SPID-{safe_name}-{now.strftime('%Y%m%d%H%M%S')}"
        fecha_hora  = now.strftime("%Y-%m-%dT%H:%M:%S")
        fecha_ejec  = str(payment.date or now.strftime("%Y-%m-%d"))
        client_id   = journal.hsbc_client_id or ""
        bic_ord     = journal.hsbc_bic or BIC_DEFAULT
        cuenta_ord  = journal.bank_account_id.acc_number or ""

        # ── Datos del beneficiario ─────────────────────────────────────────────
        partner     = payment.partner_id
        cuenta_ben  = payment.partner_bank_id.acc_number or ""
        banco_ben   = cuenta_ben[:3] if len(cuenta_ben) >= 3 else "000"
        monto       = Decimal(str(payment.amount))

        # Datos específicos de SPID
        rfc_ben     = getattr(payment, 'h2h_spid_rfc', None) or \
                      getattr(partner, 'vat', None) or ''
        codigo_op   = getattr(payment, 'h2h_spid_codigo', None) or '08'
        ref_larga   = getattr(payment, 'h2h_spid_referencia_larga', None) or ''

        # Truncar referencia larga si supera el límite (defensivo, el validador ya lo rechaza)
        if len(ref_larga) > USTRD_MAX_LENGTH:
            ref_larga = ref_larga[:USTRD_MAX_LENGTH]

        # Referencia SPID: identificador único del pago
        ref_spid    = f"SPID{now.strftime('%Y%m%d')}-{safe_name}"

        # EndToEndId: debe ser numérico (extraemos dígitos de safe_name)
        end_to_end  = referencia_end_to_end(safe_name)

        # PmtInfId
        ref_pago    = safe_name

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
        id1   = ET.SubElement(initg, "Id")
        org   = ET.SubElement(id1, "OrgId")
        othr  = ET.SubElement(org, "Othr")
        ET.SubElement(othr, "Id").text = client_id

        # PmtInf
        ptm = ET.SubElement(cstmr, "PmtInf")
        ET.SubElement(ptm, "PmtInfId").text = ref_pago
        ET.SubElement(ptm, "PmtMtd").text   = PMT_MTD

        # Tipo de pago: URGP
        pmt_tp  = ET.SubElement(ptm, "PmtTpInf")
        svc_lvl = ET.SubElement(pmt_tp, "SvcLvl")
        ET.SubElement(svc_lvl, "Cd").text = SVC_LVL_CODE  # URGP

        ET.SubElement(ptm, "ReqdExctnDt").text = fecha_ejec

        # Ordenante
        dbtr = ET.SubElement(ptm, "Dbtr")
        ET.SubElement(dbtr, "Nm").text = company.name or ""
        pstl_ord = ET.SubElement(dbtr, "PstlAdr")
        ET.SubElement(pstl_ord, "StrtNm").text = company.street or ""
        ET.SubElement(pstl_ord, "PstCd").text  = company.zip or ""
        ET.SubElement(pstl_ord, "TwnNm").text  = company.city or ""
        ET.SubElement(pstl_ord, "Ctry").text   = COUNTRY

        # Cuenta ordenante (10 dígitos, inicia con "70")
        dbtr_acct = ET.SubElement(ptm, "DbtrAcct")
        acct_id   = ET.SubElement(dbtr_acct, "Id")
        othr_d    = ET.SubElement(acct_id, "Othr")
        ET.SubElement(othr_d, "Id").text = cuenta_ord

        # Banco ordenante
        dbtr_agt = ET.SubElement(ptm, "DbtrAgt")
        fi_id    = ET.SubElement(dbtr_agt, "FinInstnId")
        ET.SubElement(fi_id, "BIC").text = bic_ord
        pstl_bank = ET.SubElement(fi_id, "PstlAdr")
        ET.SubElement(pstl_bank, "Ctry").text = COUNTRY

        # Instrucción de transferencia
        cdt    = ET.SubElement(ptm, "CdtTrfTxInf")
        pmt_id = ET.SubElement(cdt, "PmtId")

        # InstrId: referencia interna (mapea en estado de cuenta HSBC)
        ET.SubElement(pmt_id, "InstrId").text    = ref_spid
        # EndToEndId: DEBE ser numérico para SPID (entregado al beneficiario)
        ET.SubElement(pmt_id, "EndToEndId").text = end_to_end

        # Monto en USD
        amt   = ET.SubElement(cdt, "Amt")
        instd = ET.SubElement(amt, "InstdAmt")
        instd.set("Ccy", CURRENCY)  # USD
        instd.text = f"{monto:.2f}"

        # Banco beneficiario (primeros 3 dígitos de la CLABE ≠ 021)
        cdtr_agt = ET.SubElement(cdt, "CdtrAgt")
        fi_id2   = ET.SubElement(cdtr_agt, "FinInstnId")
        clr_sys  = ET.SubElement(fi_id2, "ClrSysMmbId")
        ET.SubElement(clr_sys, "MmbId").text = banco_ben
        pstl_b2  = ET.SubElement(fi_id2, "PstlAdr")
        ET.SubElement(pstl_b2, "Ctry").text = COUNTRY

        # Beneficiario
        cdtr     = ET.SubElement(cdt, "Cdtr")
        ET.SubElement(cdtr, "Nm").text = partner.name or ""
        pstl_ben_el = ET.SubElement(cdtr, "PstlAdr")
        ET.SubElement(pstl_ben_el, "StrtNm").text = partner.street or ""
        ET.SubElement(pstl_ben_el, "PstCd").text  = partner.zip or ""
        ET.SubElement(pstl_ben_el, "TwnNm").text  = partner.city or ""
        ET.SubElement(pstl_ben_el, "Ctry").text   = COUNTRY

        # Cuenta beneficiaria (CLABE 18 dígitos)
        cdtr_acct = ET.SubElement(cdt, "CdtrAcct")
        acct_id2  = ET.SubElement(cdtr_acct, "Id")
        othr_b    = ET.SubElement(acct_id2, "Othr")
        ET.SubElement(othr_b, "Id").text = cuenta_ben

        # ── Código de clasificación de operación SPID (obligatorio) ───────────
        # Formato: /SPID/OC/{codigo}  — sin espacios
        rgltryrptg = ET.SubElement(cdt, "RgltryRptg")
        dtls        = ET.SubElement(rgltryrptg, "Dtls")
        ET.SubElement(dtls, "Inf").text = f"/SPID/OC/{codigo_op}"

        # ── RFC del beneficiario (obligatorio para SPID) ───────────────────────
        tax  = ET.SubElement(cdt, "Tax")
        cdtr_tax = ET.SubElement(tax, "Cdtr")
        ET.SubElement(cdtr_tax, "TaxId").text = rfc_ben

        # ── Referencia al beneficiario (Ustrd, max 40 chars) ──────────────────
        if ref_larga:
            rmtinf = ET.SubElement(cdt, "RmtInf")
            ET.SubElement(rmtinf, "Ustrd").text = ref_larga

        # ── Serializar con formato bonito ─────────────────────────────────────
        raw    = ET.tostring(document, encoding="UTF-8")
        pretty = minidom.parseString(raw).toprettyxml(indent="    ", encoding="UTF-8")

        # HSBC requiere espacio antes del ?> en la declaración XML
        pretty = pretty.replace(
            b'<?xml version="1.0" encoding="UTF-8"?>',
            b'<?xml version="1.0" encoding="UTF-8" ?>',
            1,
        )

        # Validar el XML generado con el validador estructural de SPID
        validar_xml_spid(pretty)

        return pretty
