# -*- coding: utf-8 -*-
"""
Generador XML de Servicios HSBC H2H.
Implementa BaseH2HGenerator y produce un archivo pain.001.001.03.

Reglas específicas de Servicios validadas por HSBC:
- SvcLvl: NURG (no urgente, igual que Nómina).
- Sin CtgyPurp (a diferencia de Nómina que usa SALA).
- Cuenta beneficiaria: 10 dígitos (B2B HSBC) o 18 dígitos (CLABE SPEI).
- Banco derivado de los primeros 3 dígitos de la cuenta.
- Moneda: MXN.
- Un pago por XML (una transferencia).
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
)
from .servicios_validator import validar_pago_servicios, validar_xml_servicios


class ServiciosGenerator(BaseH2HGenerator):
    """
    Generador XML para pagos de Servicios/Proveedores HSBC.
    Pago en MXN a proveedores, B2B (10 dígitos) o SPEI (CLABE 18 dígitos).
    """

    METHOD_CODE = "SERVICIOS"

    # =========================================================================
    def validate(self, payment) -> None:
        """Delega al validador dedicado de Servicios."""
        validar_pago_servicios(payment)

    # =========================================================================
    def generate(self, payment) -> bytes:
        """
        Genera el XML pain.001.001.03 para pago de Servicios HSBC.
        Devuelve bytes UTF-8 listos para guardar o enviar.
        """
        # Validar antes de construir
        self.validate(payment)

        # ── Datos del ordenante (empresa) ─────────────────────────────────────
        company    = payment.company_id
        journal    = payment.journal_id
        safe_name  = self._get_safe_name(payment)
        now        = datetime.now()

        msg_id      = f"HSBC-SRV-{safe_name}-{now.strftime('%Y%m%d%H%M%S')}"
        fecha_hora  = now.strftime("%Y-%m-%dT%H:%M:%S")
        fecha_ejec  = str(payment.date or now.strftime("%Y-%m-%d"))
        client_id   = journal.hsbc_client_id or ""
        bic_ord     = journal.hsbc_bic or BIC_DEFAULT
        cuenta_ord  = journal.bank_account_id.acc_number or ""

        # ── Datos del beneficiario ─────────────────────────────────────────────
        partner    = payment.partner_id
        cuenta_ben = payment.partner_bank_id.acc_number or ""
        monto      = Decimal(str(payment.amount))

        # Banco beneficiario: primeros 3 dígitos de la cuenta
        banco_ben = cuenta_ben[:3] if len(cuenta_ben) >= 3 else "000"

        # Referencia de instrucción (identificación única)
        ref_srv   = f"RefS{now.strftime('%Y%m%d')}-{safe_name}"
        ref_pago  = safe_name

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

        # Tipo de pago: NURG (sin CtgyPurp, distinto de Nómina)
        pmt_tp  = ET.SubElement(ptm, "PmtTpInf")
        svc_lvl = ET.SubElement(pmt_tp, "SvcLvl")
        ET.SubElement(svc_lvl, "Cd").text = SVC_LVL_CODE  # NURG

        ET.SubElement(ptm, "ReqdExctnDt").text = fecha_ejec

        # Ordenante
        dbtr = ET.SubElement(ptm, "Dbtr")
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
        dbtr_agt = ET.SubElement(ptm, "DbtrAgt")
        fi_id    = ET.SubElement(dbtr_agt, "FinInstnId")
        ET.SubElement(fi_id, "BIC").text = bic_ord
        pstl_bank = ET.SubElement(fi_id, "PstlAdr")
        ET.SubElement(pstl_bank, "Ctry").text = COUNTRY

        # Instrucción de transferencia
        cdt    = ET.SubElement(ptm, "CdtTrfTxInf")
        pmt_id = ET.SubElement(cdt, "PmtId")
        ET.SubElement(pmt_id, "InstrId").text    = ref_srv
        ET.SubElement(pmt_id, "EndToEndId").text = ref_srv

        # Monto
        amt   = ET.SubElement(cdt, "Amt")
        instd = ET.SubElement(amt, "InstdAmt")
        instd.set("Ccy", CURRENCY)
        instd.text = f"{monto:.2f}"

        # Banco beneficiario (derivado de los primeros 3 dígitos de la cuenta)
        cdtr_agt = ET.SubElement(cdt, "CdtrAgt")
        fi_id2   = ET.SubElement(cdtr_agt, "FinInstnId")
        clr_sys  = ET.SubElement(fi_id2, "ClrSysMmbId")
        ET.SubElement(clr_sys, "MmbId").text = banco_ben
        pstl_b2  = ET.SubElement(fi_id2, "PstlAdr")
        ET.SubElement(pstl_b2, "Ctry").text = COUNTRY

        # Beneficiario
        cdtr     = ET.SubElement(cdt, "Cdtr")
        ET.SubElement(cdtr, "Nm").text = partner.name or ""
        pstl_ben = ET.SubElement(cdtr, "PstlAdr")
        ET.SubElement(pstl_ben, "StrtNm").text = partner.street or ""
        ET.SubElement(pstl_ben, "PstCd").text  = partner.zip or ""
        ET.SubElement(pstl_ben, "TwnNm").text  = partner.city or ""
        ET.SubElement(pstl_ben, "Ctry").text   = COUNTRY

        # Cuenta beneficiaria
        cdtr_acct = ET.SubElement(cdt, "CdtrAcct")
        acct_id2  = ET.SubElement(cdtr_acct, "Id")
        othr_b    = ET.SubElement(acct_id2, "Othr")
        ET.SubElement(othr_b, "Id").text = cuenta_ben

        # ── Serializar con formato bonito ─────────────────────────────────────
        raw    = ET.tostring(document, encoding="UTF-8")
        pretty = minidom.parseString(raw).toprettyxml(indent="    ", encoding="UTF-8")

        # HSBC requiere espacio antes del ?> en la declaración XML
        pretty = pretty.replace(
            b'<?xml version="1.0" encoding="UTF-8"?>',
            b'<?xml version="1.0" encoding="UTF-8" ?>',
            1,
        )

        # Validar el XML generado con el validador estructural de Servicios
        validar_xml_servicios(pretty)

        return pretty
