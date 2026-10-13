# -*- coding: utf-8 -*-
"""
Generador XML de Nomina HSBC H2H.
Implementa BaseH2HGenerator y produce un archivo ISO 20022 pain.001.001.03.

Reglas especificas de Nomina validadas por HSBC:
- SvcLvl: NURG (no urgente).
- CtgyPurp: SALA (codigo de proposito = salarios). Obligatorio para nomina.
- Banco beneficiario: siempre 021 (HSBC Mexico).
- Cuenta beneficiaria: 10 digitos (cuenta HSBC interna).
- InstrId y EndToEndId DEBEN contener la palabra "NOMINA".
- Soporta multiples transferencias agrupadas en un unico XML consolidado.
- Moneda: MXN.
"""
from decimal import Decimal
import xml.etree.ElementTree as ET
from xml.dom import minidom
from datetime import datetime

from ..generators.base_generator import BaseH2HGenerator
from .constants import (
    XML_NAMESPACE, XML_NAMESPACE_XSI,
    PMT_MTD, SVC_LVL_CODE, CTGY_PURP_CODE,
    CURRENCY, COUNTRY, BIC_DEFAULT, BANCO_HSBC,
    NOMINA_KEYWORD,
)
from .nomina_validator import validar_pago_nomina, validar_xml_nomina


class NominaGenerator(BaseH2HGenerator):
    """
    Generador XML para dispersion de Nomina HSBC (ACH interno HSBC).
    Permite generar archivos consolidados para multiples empleados seleccionados.
    """

    METHOD_CODE = "NOMINA"

    # =========================================================================
    def validate(self, payment) -> None:
        """Delega al validador dedicado de Nomina."""
        validar_pago_nomina(payment)

    # =========================================================================
    def generate(self, payment) -> bytes:
        """
        Genera el XML pain.001.001.03 para Nomina HSBC.
        Si el pago cuenta con lineas de empleados (h2h_nomina_line_ids),
        genera un lote agrupando todas las transferencias con sus importes individuales.
        Si no, genera una transferencia individual para el partner del pago.
        Devuelve bytes UTF-8 listos para guardar o enviar.
        """
        # Validar antes de construir
        self.validate(payment)

        # ── Datos del ordenante (empresa) ─────────────────────────────────────
        company    = payment.company_id
        journal    = payment.journal_id
        safe_name  = self._get_safe_name(payment)
        now        = datetime.now()

        # MsgId: identificador unico del mensaje
        msg_id       = f"HSBC-NOM-{safe_name}-{now.strftime('%Y%m%d%H%M%S')}"
        fecha_hora   = now.strftime("%Y-%m-%dT%H:%M:%S")
        fecha_ejec   = str(payment.date or now.strftime("%Y-%m-%d"))
        client_id    = journal.hsbc_client_id or ""
        bic_ord      = journal.hsbc_bic or BIC_DEFAULT

        # Cuenta de dispersion de nomina HSBC (10 digitos)
        cuenta_ord   = getattr(journal, 'hsbc_nomina_account', '') or ''

        # ── Preparar transferencias de empleados ──────────────────────────────
        lines = getattr(payment, 'h2h_nomina_line_ids', None)
        transferencias = []

        if lines and len(lines) > 0:
            for idx, line in enumerate(lines, start=1):
                monto_line = Decimal(str(line.amount)).quantize(Decimal("0.01"))
                cuenta_line = (line.acc_number or "").strip()
                ref_line = f"NOMINA{now.strftime('%Y%m%d')}{idx:04d}"
                # Guardar referencia en la línea para trazabilidad
                try:
                    line.referencia_empleado = ref_line
                except Exception:
                    pass

                emp = line.partner_id
                transferencias.append({
                    "referencia": ref_line,
                    "monto": monto_line,
                    "beneficiario": emp.name or "",
                    "cuenta": cuenta_line,
                    "calle": emp.street or "Domicilio Conocido",
                    "cp": emp.zip or "01000",
                    "ciudad": emp.city or "Mexico",
                    "line_record": line,
                })
        else:
            # Modo individual retrocompatible
            monto_ind = Decimal(str(payment.amount)).quantize(Decimal("0.01"))
            cuenta_ind = (payment.partner_bank_id.acc_number or "").strip()
            ref_ind = f"NOMINA{now.strftime('%Y%m%d')}-0001"
            transferencias.append({
                "referencia": ref_ind,
                "monto": monto_ind,
                "beneficiario": payment.partner_id.name or "",
                "cuenta": cuenta_ind,
                "calle": payment.partner_id.street or "Domicilio Conocido",
                "cp": payment.partner_id.zip or "01000",
                "ciudad": payment.partner_id.city or "Mexico",
                "line_record": None,
            })

        total_monto = sum(t["monto"] for t in transferencias)
        num_txs = len(transferencias)

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
        ET.SubElement(grp, "NbOfTxs").text = str(num_txs)
        ET.SubElement(grp, "CtrlSum").text = f"{total_monto:.2f}"

        initg = ET.SubElement(grp, "InitgPty")
        id1   = ET.SubElement(initg, "Id")
        org   = ET.SubElement(id1, "OrgId")
        othr  = ET.SubElement(org, "Othr")
        ET.SubElement(othr, "Id").text = client_id

        # PmtInf
        ptm = ET.SubElement(cstmr, "PmtInf")
        ET.SubElement(ptm, "PmtInfId").text = safe_name
        ET.SubElement(ptm, "PmtMtd").text   = PMT_MTD

        # Tipo de pago: NURG + propósito SALA (obligatorio para nómina HSBC)
        pmt_tp = ET.SubElement(ptm, "PmtTpInf")
        svc_lvl = ET.SubElement(pmt_tp, "SvcLvl")
        ET.SubElement(svc_lvl, "Cd").text = SVC_LVL_CODE  # NURG
        ctgy_purp = ET.SubElement(pmt_tp, "CtgyPurp")
        ET.SubElement(ctgy_purp, "Cd").text = CTGY_PURP_CODE  # SALA

        ET.SubElement(ptm, "ReqdExctnDt").text = fecha_ejec

        # Ordenante
        dbtr = ET.SubElement(ptm, "Dbtr")
        ET.SubElement(dbtr, "Nm").text = company.name or ""
        pstl_ord = ET.SubElement(dbtr, "PstlAdr")
        ET.SubElement(pstl_ord, "StrtNm").text = company.street or ""
        ET.SubElement(pstl_ord, "PstCd").text  = company.zip or ""
        ET.SubElement(pstl_ord, "TwnNm").text  = company.city or ""
        ET.SubElement(pstl_ord, "Ctry").text   = COUNTRY

        # Cuenta ordenante (cuenta HSBC de dispersion de nomina, 10 digitos)
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

        # ── Instrucciones de transferencia para cada empleado ─────────────────
        for t in transferencias:
            cdt = ET.SubElement(ptm, "CdtTrfTxInf")
            pmt_id = ET.SubElement(cdt, "PmtId")

            # InstrId y EndToEndId DEBEN contener la palabra NOMINA
            ref_nomina = t["referencia"]
            ET.SubElement(pmt_id, "InstrId").text    = ref_nomina
            ET.SubElement(pmt_id, "EndToEndId").text = ref_nomina

            # Monto individual
            amt   = ET.SubElement(cdt, "Amt")
            instd = ET.SubElement(amt, "InstdAmt")
            instd.set("Ccy", CURRENCY)
            instd.text = f"{t['monto']:.2f}"

            # Banco beneficiario: siempre 021 (HSBC México) para nómina
            cdtr_agt = ET.SubElement(cdt, "CdtrAgt")
            fi_id2   = ET.SubElement(cdtr_agt, "FinInstnId")
            clr_sys  = ET.SubElement(fi_id2, "ClrSysMmbId")
            ET.SubElement(clr_sys, "MmbId").text = BANCO_HSBC
            pstl_b2  = ET.SubElement(fi_id2, "PstlAdr")
            ET.SubElement(pstl_b2, "Ctry").text = COUNTRY

            # Beneficiario (empleado)
            cdtr     = ET.SubElement(cdt, "Cdtr")
            ET.SubElement(cdtr, "Nm").text = t["beneficiario"]
            pstl_ben = ET.SubElement(cdtr, "PstlAdr")
            ET.SubElement(pstl_ben, "StrtNm").text = t["calle"]
            ET.SubElement(pstl_ben, "PstCd").text  = t["cp"]
            ET.SubElement(pstl_ben, "TwnNm").text  = t["ciudad"]
            ET.SubElement(pstl_ben, "Ctry").text   = COUNTRY

            # Cuenta beneficiaria (10 dígitos HSBC)
            cdtr_acct = ET.SubElement(cdt, "CdtrAcct")
            acct_id2  = ET.SubElement(cdtr_acct, "Id")
            othr_b    = ET.SubElement(acct_id2, "Othr")
            ET.SubElement(othr_b, "Id").text = t["cuenta"]

        # ── Serializar con formato bonito ─────────────────────────────────────
        raw    = ET.tostring(document, encoding="UTF-8")
        pretty = minidom.parseString(raw).toprettyxml(indent="    ", encoding="UTF-8")

        # HSBC requiere espacio antes del ?> en la declaracion XML
        pretty = pretty.replace(
            b'<?xml version="1.0" encoding="UTF-8"?>',
            b'<?xml version="1.0" encoding="UTF-8" ?>',
            1,
        )

        # Validar el XML generado con el validador estructural de Nomina
        validar_xml_nomina(pretty)

        return pretty
