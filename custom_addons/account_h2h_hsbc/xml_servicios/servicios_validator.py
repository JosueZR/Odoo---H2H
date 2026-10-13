# -*- coding: utf-8 -*-
"""
Validaciones específicas para pagos de Servicios HSBC y de su estructura XML final generada.
Reglas basadas en el generador original validado por HSBC.

Reglas específicas de Servicios:
- Cuenta beneficiaria: 10 dígitos (B2B HSBC) o 18 dígitos (CLABE SPEI interbancaria).
- El banco se deriva de los primeros 3 dígitos de la cuenta.
- SvcLvl = NURG (no urgente), sin CtgyPurp.
- La moneda debe ser MXN.
"""
import xml.etree.ElementTree as ET
try:
    from odoo.exceptions import UserError
except ImportError:
    class UserError(Exception):
        pass

from .constants import (
    CUENTA_B2B_LENGTH, CUENTA_CLABE_LENGTH, CURRENCY, XML_NAMESPACE,
)


def validar_cuenta_servicios(cuenta: str) -> tuple:
    """
    Valida la cuenta beneficiaria para pago de servicios.
    Acepta cuentas de 10 dígitos (B2B HSBC) o 18 dígitos (CLABE SPEI).

    Returns:
        (es_valida: bool, tipo: str)  — tipo es 'B2B' o 'CLABE' o ''
    """
    if not cuenta or not cuenta.isdigit():
        return False, ''
    if len(cuenta) == CUENTA_B2B_LENGTH:
        return True, 'B2B'
    if len(cuenta) == CUENTA_CLABE_LENGTH:
        return True, 'CLABE'
    return False, ''


def validar_pago_servicios(payment) -> None:
    """
    Valida que el pago tenga todos los datos requeridos para generar XML de Servicios HSBC.
    Lanza UserError describiendo exactamente qué falta.
    """
    errores = []

    # ── Cuenta bancaria del beneficiario ──────────────────────────────────────
    if not payment.partner_bank_id:
        errores.append("El proveedor no tiene cuenta bancaria registrada en este pago.")
    elif not payment.partner_bank_id.acc_number:
        errores.append("La cuenta bancaria del proveedor no tiene número de cuenta.")
    else:
        cuenta = payment.partner_bank_id.acc_number
        es_valida, tipo = validar_cuenta_servicios(cuenta)
        if not es_valida:
            errores.append(
                f"La cuenta beneficiaria '{cuenta}' no es válida para pagos de Servicios. "
                f"Debe tener {CUENTA_B2B_LENGTH} dígitos (cuenta B2B HSBC) "
                f"o {CUENTA_CLABE_LENGTH} dígitos (CLABE SPEI)."
            )

    # ── Cuenta ordenante ─────────────────────────────────────────────────────
    if not payment.journal_id.bank_account_id or \
       not payment.journal_id.bank_account_id.acc_number:
        errores.append(
            "El diario HSBC no tiene configurada la cuenta bancaria de la empresa."
        )

    # ── ID cliente HSBC ────────────────────────────────────────────────────────
    if not payment.journal_id.hsbc_client_id:
        errores.append(
            "El diario HSBC no tiene configurado el ID de cliente HSBC. "
            "(Ve a Contabilidad → Configuración → Diarios → sección HSBC H2H)."
        )

    # ── Proveedor ─────────────────────────────────────────────────────────────
    if not payment.partner_id:
        errores.append("El pago no tiene proveedor asignado.")
    elif not payment.partner_id.name:
        errores.append("El proveedor no tiene nombre registrado.")

    # ── Monto ─────────────────────────────────────────────────────────────────
    if not payment.amount or payment.amount <= 0:
        errores.append("El monto del pago debe ser mayor a cero.")

    # ── Moneda ────────────────────────────────────────────────────────────────
    if payment.currency_id and payment.currency_id.name != CURRENCY:
        errores.append(
            f"Los pagos de Servicios solo operan en {CURRENCY}. "
            f"La moneda del pago es {payment.currency_id.name}."
        )

    # ── Empresa ───────────────────────────────────────────────────────────────
    if not payment.company_id.name:
        errores.append("La empresa no tiene nombre configurado.")

    if errores:
        raise UserError(
            "No se puede generar el XML de Servicios HSBC. "
            "Corrige los siguientes problemas:\n\n"
            + "\n".join(f"• {e}" for e in errores)
        )


def validar_xml_servicios(xml_bytes: bytes) -> None:
    """
    Valida la estructura y contenido del archivo XML generado para Servicios HSBC.
    Verifica que cumpla con el estándar pain.001.001.03 y las especificaciones
    validadas por HSBC México:
      - Bien formado y parseable
      - Raíz Document con namespace ISO 20022 correcto
      - GrpHdr con MsgId, CreDtTm, NbOfTxs, CtrlSum
      - InitgPty con Id de cliente
      - PmtInf con SvcLvl='NURG'
      - Sin CtgyPurp (no es nómina)
      - Moneda MXN
      - Cuenta beneficiaria de 10 dígitos (B2B HSBC) o 18 dígitos (CLABE)
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise UserError(f"Error de estructura XML en Servicios: El archivo no es un XML válido o está mal formado:\n{e}")

    ns = XML_NAMESPACE
    if not (root.tag == "Document" or root.tag == f"{{{ns}}}Document"):
        raise UserError(f"Estructura Servicios inválida: La etiqueta raíz debe ser 'Document'. Encontrado: {root.tag}")

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
        raise UserError("Estructura Servicios inválida: Falta la sección 'CstmrCdtTrfInitn'.")

    # GrpHdr
    grp = find_node(cstmr, "GrpHdr")
    if grp is None:
        raise UserError("Estructura Servicios inválida: Falta el encabezado 'GrpHdr'.")

    if not get_val(grp, "MsgId"):
        raise UserError("Estructura Servicios inválida: 'GrpHdr/MsgId' es obligatorio.")
    if not get_val(grp, "CreDtTm"):
        raise UserError("Estructura Servicios inválida: 'GrpHdr/CreDtTm' es obligatorio.")
    if not get_val(grp, "NbOfTxs"):
        raise UserError("Estructura Servicios inválida: 'GrpHdr/NbOfTxs' es obligatorio.")
    if not get_val(grp, "CtrlSum"):
        raise UserError("Estructura Servicios inválida: 'GrpHdr/CtrlSum' es obligatorio.")

    # PmtInf
    pmt_inf = find_node(cstmr, "PmtInf")
    if pmt_inf is None:
        raise UserError("Estructura Servicios inválida: Falta la sección 'PmtInf'.")

    pmt_tp = find_node(pmt_inf, "PmtTpInf")
    if pmt_tp is None:
        raise UserError("Estructura Servicios inválida: Falta 'PmtInf/PmtTpInf'.")

    svc_lvl = find_node(pmt_tp, "SvcLvl")
    svc_code = get_val(svc_lvl, "Cd") if svc_lvl is not None else ""
    if svc_code != "NURG":
        raise UserError(f"Estructura Servicios inválida: SvcLvl/Cd debe ser 'NURG'. Encontrado: '{svc_code}'.")

    # No debe tener CtgyPurp SALA de nómina
    ctgy = find_node(pmt_tp, "CtgyPurp")
    if ctgy is not None and get_val(ctgy, "Cd") == "SALA":
        raise UserError("Estructura Servicios inválida: Un pago de servicios no debe contener CtgyPurp/Cd='SALA'.")

    # CdtTrfTxInf
    cdt = find_node(pmt_inf, "CdtTrfTxInf")
    if cdt is None:
        raise UserError("Estructura Servicios inválida: Falta la instrucción de pago 'CdtTrfTxInf'.")

    pmt_id = find_node(cdt, "PmtId")
    if pmt_id is None or not get_val(pmt_id, "InstrId") or not get_val(pmt_id, "EndToEndId"):
        raise UserError("Estructura Servicios inválida: 'InstrId' y 'EndToEndId' son obligatorios en 'PmtId'.")

    amt = find_node(cdt, "Amt")
    if amt is None:
        raise UserError("Estructura Servicios inválida: Falta 'CdtTrfTxInf/Amt'.")
    instd_amt = find_node(amt, "InstdAmt")
    if instd_amt is None or instd_amt.get("Ccy") != "MXN":
        raise UserError(
            f"Estructura Servicios inválida: La moneda 'Ccy' debe ser 'MXN'. "
            f"Encontrado: '{instd_amt.get('Ccy') if instd_amt is not None else 'None'}'."
        )

    # CdtrAcct con cuenta B2B (10 dígitos) o CLABE (18 dígitos)
    cdtr_acct = find_node(cdt, "CdtrAcct")
    if cdtr_acct is None:
        raise UserError("Estructura Servicios inválida: Falta 'CdtTrfTxInf/CdtrAcct'.")
    cdtr_acct_id = find_node(find_node(cdtr_acct, "Id") or cdtr_acct, "Othr")
    cuenta_ben = get_val(cdtr_acct_id or cdtr_acct, "Id") if cdtr_acct_id is not None else ""
    if not (cuenta_ben.isdigit() and len(cuenta_ben) in (10, 18)):
        raise UserError(
            f"Estructura Servicios inválida: La cuenta beneficiaria en CdtrAcct debe tener 10 dígitos (B2B HSBC) "
            f"o 18 dígitos (CLABE SPEI). Encontrado: '{cuenta_ben}'."
        )
