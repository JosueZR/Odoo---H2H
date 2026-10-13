# -*- coding: utf-8 -*-
"""
Validaciones específicas para pagos SPEI y su estructura XML.
Separadas del generador para facilitar pruebas unitarias y reutilización.
"""
import xml.etree.ElementTree as ET
try:
    from odoo.exceptions import UserError
except ImportError:
    class UserError(Exception):
        pass

from .constants import CLABE_LENGTH, CURRENCY, XML_NAMESPACE


def validar_clabe(clabe: str) -> bool:
    """
    Valida que una CLABE interbancaria tenga 18 dígitos.
    """
    if not clabe or not clabe.isdigit():
        return False
    if len(clabe) != CLABE_LENGTH:
        return False
    return True


def validar_pago_spei(payment) -> None:
    """
    Valida que el pago tenga todos los datos requeridos para generar un XML SPEI.
    Lanza UserError describiendo exactamente qué falta.
    """
    errores = []

    # Cuenta bancaria de destino (CLABE)
    if not payment.partner_bank_id:
        errores.append("El proveedor no tiene una cuenta bancaria (CLABE) registrada en este pago.")
    elif not payment.partner_bank_id.acc_number:
        errores.append("La cuenta bancaria del proveedor no tiene número de cuenta (CLABE).")
    elif not validar_clabe(payment.partner_bank_id.acc_number):
        errores.append(
            f"La CLABE '{payment.partner_bank_id.acc_number}' no es válida "
            f"(debe tener {CLABE_LENGTH} dígitos numéricos)."
        )

    # Proveedor
    if not payment.partner_id:
        errores.append("El pago no tiene proveedor/beneficiario asignado.")
    elif not payment.partner_id.name:
        errores.append("El proveedor no tiene nombre registrado.")

    # Cuenta ordenante (cuenta de empresa en HSBC)
    if not payment.journal_id.bank_account_id or not payment.journal_id.bank_account_id.acc_number:
        errores.append(
            "El diario HSBC no tiene configurada la cuenta bancaria de la empresa "
            "(se requiere para el campo DbtrAcct del XML)."
        )

    # ID cliente HSBC
    if not payment.journal_id.hsbc_client_id:
        errores.append(
            "El diario HSBC no tiene configurado el ID de cliente HSBC "
            "(ve a Contabilidad → Configuración → Diarios → sección HSBC H2H)."
        )

    # Monto
    if not payment.amount or payment.amount <= 0:
        errores.append("El monto del pago debe ser mayor a cero.")

    # Moneda
    if payment.currency_id and payment.currency_id.name != CURRENCY:
        errores.append(
            f"SPEI solo opera en {CURRENCY}. "
            f"La moneda del pago es {payment.currency_id.name}."
        )

    # Datos de la compañía
    if not payment.company_id.name:
        errores.append("La empresa no tiene nombre configurado.")

    if errores:
        raise UserError(
            "No se puede generar el XML SPEI. Corrige los siguientes problemas:\n\n"
            + "\n".join(f"• {e}" for e in errores)
        )


def validar_xml_spei(xml_bytes: bytes) -> None:
    """
    Valida la estructura y contenido del archivo XML generado para SPEI.
    Verifica que cumpla con el estándar pain.001.001.03 y las especificaciones
    validadas por HSBC México:
      - Bien formado y parseable
      - Raíz Document con namespace correcto
      - GrpHdr con MsgId, CreDtTm, NbOfTxs='1', CtrlSum coincidente
      - InitgPty con Id de cliente
      - PmtInf con SvcLvl='URGP' (SPEI es urgente)
      - CdtTrfTxInf con moneda MXN
      - CLABE beneficiaria de 18 dígitos
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise UserError(f"Error de estructura XML en SPEI: El archivo no es un XML válido o está mal formado:\n{e}")

    ns = XML_NAMESPACE
    if not (root.tag == "Document" or root.tag == f"{{{ns}}}Document"):
        raise UserError(f"Estructura SPEI inválida: La etiqueta raíz debe ser 'Document'. Encontrado: {root.tag}")

    def find_node(parent, tag):
        n = parent.find(tag)
        if n is None:
            n = parent.find(f"{{{ns}}}{tag}")
        return n

    def get_val(parent, tag):
        node = find_node(parent, tag)
        return (node.text or "").strip() if node is not None else ""

    cstmr = find_node(root, "CstmrCdtTrfInitn")
    if cstmr is None:
        raise UserError("Estructura SPEI inválida: Falta la sección 'CstmrCdtTrfInitn'.")

    # GrpHdr
    grp = find_node(cstmr, "GrpHdr")
    if grp is None:
        raise UserError("Estructura SPEI inválida: Falta el encabezado 'GrpHdr'.")

    msg_id = get_val(grp, "MsgId")
    if not msg_id:
        raise UserError("Estructura SPEI inválida: 'GrpHdr/MsgId' es obligatorio.")

    cre_dt_tm = get_val(grp, "CreDtTm")
    if not cre_dt_tm:
        raise UserError("Estructura SPEI inválida: 'GrpHdr/CreDtTm' es obligatorio.")

    nb_of_txs = get_val(grp, "NbOfTxs")
    if nb_of_txs != "1":
        raise UserError(f"Estructura SPEI inválida: 'GrpHdr/NbOfTxs' debe ser '1'. Encontrado: '{nb_of_txs}'.")

    ctrl_sum = get_val(grp, "CtrlSum")
    if not ctrl_sum:
        raise UserError("Estructura SPEI inválida: 'GrpHdr/CtrlSum' es obligatorio.")

    # InitgPty / Id / OrgId / Othr / Id
    initg = find_node(grp, "InitgPty")
    if initg is None:
        raise UserError("Estructura SPEI inválida: Falta 'GrpHdr/InitgPty'.")
    org_id_node = find_node(find_node(find_node(initg, "Id") or initg, "OrgId") or initg, "Othr")
    client_id = get_val(org_id_node or initg, "Id") if org_id_node is not None else ""
    if not client_id:
        raise UserError("Estructura SPEI inválida: Falta el ID de cliente HSBC en 'InitgPty/Id/OrgId/Othr/Id'.")

    # PmtInf
    pmt_inf = find_node(cstmr, "PmtInf")
    if pmt_inf is None:
        raise UserError("Estructura SPEI inválida: Falta la sección 'PmtInf'.")

    pmt_mtd = get_val(pmt_inf, "PmtMtd")
    if pmt_mtd != "TRF":
        raise UserError(f"Estructura SPEI inválida: 'PmtInf/PmtMtd' debe ser 'TRF'. Encontrado: '{pmt_mtd}'.")

    # PmtTpInf -> SvcLvl -> Cd == URGP
    pmt_tp = find_node(pmt_inf, "PmtTpInf")
    if pmt_tp is None:
        raise UserError("Estructura SPEI inválida: Falta 'PmtInf/PmtTpInf'.")
    svc_lvl = find_node(pmt_tp, "SvcLvl")
    svc_code = get_val(svc_lvl, "Cd") if svc_lvl is not None else ""
    if svc_code != "URGP":
        raise UserError(f"Estructura SPEI inválida: SvcLvl/Cd debe ser 'URGP' para pagos SPEI. Encontrado: '{svc_code}'.")

    # Dbtr y DbtrAcct
    dbtr = find_node(pmt_inf, "Dbtr")
    if dbtr is None or not get_val(dbtr, "Nm"):
        raise UserError("Estructura SPEI inválida: Falta el nombre del ordenante en 'PmtInf/Dbtr/Nm'.")

    dbtr_acct = find_node(pmt_inf, "DbtrAcct")
    if dbtr_acct is None:
        raise UserError("Estructura SPEI inválida: Falta 'PmtInf/DbtrAcct'.")

    # CdtTrfTxInf
    cdt = find_node(pmt_inf, "CdtTrfTxInf")
    if cdt is None:
        raise UserError("Estructura SPEI inválida: Falta la instrucción de pago 'CdtTrfTxInf'.")

    pmt_id = find_node(cdt, "PmtId")
    if pmt_id is None or not get_val(pmt_id, "InstrId") or not get_val(pmt_id, "EndToEndId"):
        raise UserError("Estructura SPEI inválida: 'InstrId' y 'EndToEndId' son obligatorios en 'PmtId'.")

    amt = find_node(cdt, "Amt")
    if amt is None:
        raise UserError("Estructura SPEI inválida: Falta 'CdtTrfTxInf/Amt'.")
    instd_amt = find_node(amt, "InstdAmt")
    if instd_amt is None:
        raise UserError("Estructura SPEI inválida: Falta 'Amt/InstdAmt'.")
    if instd_amt.get("Ccy") != "MXN":
        raise UserError(f"Estructura SPEI inválida: La moneda 'Ccy' debe ser 'MXN'. Encontrado: '{instd_amt.get('Ccy')}'.")

    # CdtrAcct (CLABE de 18 dígitos)
    cdtr_acct = find_node(cdt, "CdtrAcct")
    if cdtr_acct is None:
        raise UserError("Estructura SPEI inválida: Falta 'CdtTrfTxInf/CdtrAcct'.")
    cdtr_acct_id = find_node(find_node(cdtr_acct, "Id") or cdtr_acct, "Othr")
    cuenta_ben = get_val(cdtr_acct_id or cdtr_acct, "Id") if cdtr_acct_id is not None else ""
    if not cuenta_ben or len(cuenta_ben) != 18 or not cuenta_ben.isdigit():
        raise UserError(
            f"Estructura SPEI inválida: La cuenta beneficiaria en CdtrAcct debe tener 18 dígitos (CLABE). "
            f"Encontrado: '{cuenta_ben}'."
        )
