# -*- coding: utf-8 -*-
"""
Generador XML SPEI para HSBC H2H.
Implementa BaseH2HGenerator y produce un archivo pain.001.001.03.
"""
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime

from ..generators.base_generator import BaseH2HGenerator
from .constants import (
    XML_NAMESPACE, XML_NAMESPACE_XSI,
    SVC_LVL_CODE, PMT_MTD, CURRENCY, COUNTRY, BIC_DEFAULT,
)
from .spei_validator import validar_pago_spei, validar_xml_spei


class SpeiGenerator(BaseH2HGenerator):

    METHOD_CODE = "SPEI"

    # =========================================================================
    def validate(self, payment) -> None:
        """Delega al validador dedicado de SPEI."""
        validar_pago_spei(payment)

    # =========================================================================
    def generate(self, payment) -> bytes:
        """
        Genera el XML pain.001.001.03 para SPEI HSBC.
        Devuelve bytes UTF-8 listos para guardar o enviar.
        """
        # Validar antes de construir
        self.validate(payment)

        # ── Datos del ordenante (empresa) ─────────────────────────────────────
        company      = payment.company_id
        journal      = payment.journal_id
        safe_name    = self._get_safe_name(payment)
        now          = datetime.now()
        msg_id       = f"HSBC-{safe_name}-{now.strftime('%Y%m%d%H%M%S')}"
        fecha_hora   = now.strftime("%Y-%m-%dT%H:%M:%S")
        fecha_ejec   = str(payment.date or now.strftime("%Y-%m-%d"))
        client_id    = journal.hsbc_client_id or ""
        bic_ord      = journal.hsbc_bic or BIC_DEFAULT
        cuenta_ord   = journal.bank_account_id.acc_number or ""

        # ── Datos del beneficiario ────────────────────────────────────────────
        partner           = payment.partner_id
        cuenta_ben        = payment.partner_bank_id.acc_number or ""
        banco_ben_clave   = cuenta_ben[:3] if len(cuenta_ben) >= 3 else "000"
        monto             = payment.amount

        # ── Construcción del árbol XML ────────────────────────────────────────
        document = ET.Element("Document", {
            "xmlns:xsi": XML_NAMESPACE_XSI,
            "xmlns":     XML_NAMESPACE,
        })

        cstmr = ET.SubElement(document, "CstmrCdtTrfInitn")

        # GrpHdr
        grp = ET.SubElement(cstmr, "GrpHdr")
        ET.SubElement(grp, "MsgId").text    = msg_id
        ET.SubElement(grp, "CreDtTm").text  = fecha_hora
        ET.SubElement(grp, "NbOfTxs").text  = "1"
        ET.SubElement(grp, "CtrlSum").text  = f"{monto:.2f}"

        initg = ET.SubElement(grp, "InitgPty")
        id1   = ET.SubElement(initg, "Id")
        org   = ET.SubElement(id1, "OrgId")
        othr  = ET.SubElement(org, "Othr")
        ET.SubElement(othr, "Id").text = client_id

        # PmtInf
        ptm = ET.SubElement(cstmr, "PmtInf")
        ET.SubElement(ptm, "PmtInfId").text = safe_name
        ET.SubElement(ptm, "PmtMtd").text   = PMT_MTD

        pmt_tp  = ET.SubElement(ptm, "PmtTpInf")
        svc_lvl = ET.SubElement(pmt_tp, "SvcLvl")
        ET.SubElement(svc_lvl, "Cd").text = SVC_LVL_CODE

        ET.SubElement(ptm, "ReqdExctnDt").text = fecha_ejec

        # Ordenante
        dbtr     = ET.SubElement(ptm, "Dbtr")
        ET.SubElement(dbtr, "Nm").text = company.name or ""
        pstl_ord = ET.SubElement(dbtr, "PstlAdr")
        ET.SubElement(pstl_ord, "StrtNm").text = company.street or ""
        ET.SubElement(pstl_ord, "PstCd").text  = company.zip or ""
        ET.SubElement(pstl_ord, "TwnNm").text  = company.city or ""
        ET.SubElement(pstl_ord, "Ctry").text   = COUNTRY

        # Cuenta ordenante
        dbtr_acct = ET.SubElement(ptm, "DbtrAcct")
        acct_id   = ET.SubElement(dbtr_acct, "Id")
        othr_d    = ET.SubElement(acct_id, "Othr")
        ET.SubElement(othr_d, "Id").text = cuenta_ord

        # Banco ordenante
        dbtr_agt  = ET.SubElement(ptm, "DbtrAgt")
        fi_id     = ET.SubElement(dbtr_agt, "FinInstnId")
        ET.SubElement(fi_id, "BIC").text = bic_ord
        pstl_bank = ET.SubElement(fi_id, "PstlAdr")
        ET.SubElement(pstl_bank, "Ctry").text = COUNTRY

        # Instrucción de transferencia
        cdt = ET.SubElement(ptm, "CdtTrfTxInf")
        pmt_id = ET.SubElement(cdt, "PmtId")
        ET.SubElement(pmt_id, "InstrId").text    = safe_name
        ET.SubElement(pmt_id, "EndToEndId").text = safe_name

        # Monto
        amt      = ET.SubElement(cdt, "Amt")
        instd    = ET.SubElement(amt, "InstdAmt")
        instd.set("Ccy", CURRENCY)
        instd.text = f"{monto:.2f}"

        # Banco beneficiario (clave derivada de la CLABE)
        cdtr_agt  = ET.SubElement(cdt, "CdtrAgt")
        fi_id2    = ET.SubElement(cdtr_agt, "FinInstnId")
        clr_sys   = ET.SubElement(fi_id2, "ClrSysMmbId")
        ET.SubElement(clr_sys, "MmbId").text = banco_ben_clave
        pstl_b2   = ET.SubElement(fi_id2, "PstlAdr")
        ET.SubElement(pstl_b2, "Ctry").text = COUNTRY

        # Beneficiario
        cdtr     = ET.SubElement(cdt, "Cdtr")
        ET.SubElement(cdtr, "Nm").text = partner.name or ""
        pstl_ben = ET.SubElement(cdtr, "PstlAdr")
        ET.SubElement(pstl_ben, "StrtNm").text = partner.street or ""
        ET.SubElement(pstl_ben, "PstCd").text  = partner.zip or ""
        ET.SubElement(pstl_ben, "TwnNm").text  = partner.city or ""
        ET.SubElement(pstl_ben, "Ctry").text   = COUNTRY

        # Cuenta beneficiario
        cdtr_acct = ET.SubElement(cdt, "CdtrAcct")
        acct_id2  = ET.SubElement(cdtr_acct, "Id")
        othr_b    = ET.SubElement(acct_id2, "Othr")
        ET.SubElement(othr_b, "Id").text = cuenta_ben

        # ── Serializar con formato bonito ─────────────────────────────────────
        raw = ET.tostring(document, encoding="UTF-8")
        pretty = minidom.parseString(raw).toprettyxml(indent="    ", encoding="UTF-8")

        # HSBC requiere espacio antes del ?> en la declaración XML
        pretty = pretty.replace(
            b'<?xml version="1.0" encoding="UTF-8"?>',
            b'<?xml version="1.0" encoding="UTF-8" ?>',
            1,
        )

        # Validar el XML generado con el validador estructural de SPEI
        validar_xml_spei(pretty)

        return pretty
