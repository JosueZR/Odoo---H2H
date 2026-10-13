# -*- coding: utf-8 -*-
"""
Validaciones específicas para pagos de Nómina HSBC y de su estructura XML final generada.
Reglas basadas en el generador original validado por HSBC.

Soporta pagos individuales y pagos de nómina con múltiples empleados seleccionados.
"""
from decimal import Decimal
import xml.etree.ElementTree as ET
try:
    from odoo.exceptions import UserError
except ImportError:
    class UserError(Exception):
        pass

from .constants import (
    BANCO_HSBC, CUENTA_NOMINA_LENGTH, NOMINA_KEYWORD,
    CURRENCY, XML_NAMESPACE, SVC_LVL_CODE, CTGY_PURP_CODE,
)


def validar_cuenta_nomina_hsbc(cuenta: str) -> bool:
    """
    Valida que la cuenta HSBC de nómina tenga exactamente 10 dígitos.
    Las cuentas de nómina HSBC son cuentas internas de 10 dígitos.
    """
    if not cuenta or not cuenta.isdigit():
        return False
    return len(cuenta) == CUENTA_NOMINA_LENGTH


def validar_referencia_nomina(referencia: str) -> bool:
    """
    Verifica que la referencia contenga la palabra 'NOMINA'.
    HSBC requiere esta palabra en InstrId y EndToEndId para nómina.
    """
    return NOMINA_KEYWORD in str(referencia).upper()


def validar_pago_nomina(payment) -> None:
    """
    Valida que el pago tenga todos los datos requeridos para generar XML de Nómina HSBC.
    Lanza UserError describiendo exactamente qué falta o qué empleado tiene datos incompletos.
    """
    errores = []

    # ── Cuenta ordenante de nómina (cuenta HSBC de 10 dígitos del diario) ────
    cuenta_nom = getattr(payment.journal_id, 'hsbc_nomina_account', None) or ''
    if not cuenta_nom:
        errores.append(
            "El diario HSBC no tiene configurada la cuenta de dispersion de nomina "
            "(campo 'Cuenta HSBC Nomina'). Configurela en Contabilidad -> Configuracion -> Diarios "
            "-> seccion HSBC H2H."
        )
    elif not validar_cuenta_nomina_hsbc(cuenta_nom):
        errores.append(
            f"La cuenta de nomina HSBC '{cuenta_nom}' no es valida. "
            f"Debe tener {CUENTA_NOMINA_LENGTH} digitos numericos (cuenta HSBC interna)."
        )

    # ── ID cliente HSBC ────────────────────────────────────────────────────────
    if not payment.journal_id.hsbc_client_id:
        errores.append(
            "El diario HSBC no tiene configurado el ID de cliente HSBC. "
            "(Configurelo en Contabilidad -> Configuracion -> Diarios -> seccion HSBC H2H)."
        )

    # ── Moneda ────────────────────────────────────────────────────────────────
    if payment.currency_id and payment.currency_id.name != CURRENCY:
        errores.append(
            f"Los pagos de Nomina HSBC solo operan en {CURRENCY}. "
            f"La moneda actual del pago es {payment.currency_id.name}."
        )

    # ── Empresa ───────────────────────────────────────────────────────────────
    if not payment.company_id.name:
        errores.append("La empresa no tiene nombre configurado.")

    # ── Validación de Beneficiarios / Empleados ────────────────────────────────
    lines = getattr(payment, 'h2h_nomina_line_ids', None)
    if lines and len(lines) > 0:
        # Modo multi-empleado (tabla editable)
        total_nomina = 0.0
        for idx, line in enumerate(lines, start=1):
            emp_nombre = line.partner_id.name if line.partner_id else f"Empleado #{idx}"
            if not line.partner_id:
                errores.append(f"Fila #{idx}: Falta seleccionar al empleado.")
                continue

            cuenta_emp = (line.acc_number or "").strip()
            if not cuenta_emp:
                errores.append(
                    f"Fila #{idx} ({emp_nombre}): No tiene numero de cuenta registrado."
                )
            elif not validar_cuenta_nomina_hsbc(cuenta_emp):
                errores.append(
                    f"Fila #{idx} ({emp_nombre}): La cuenta '{cuenta_emp}' debe tener "
                    f"exactamente {CUENTA_NOMINA_LENGTH} digitos numericos."
                )

            if not line.amount or line.amount <= 0:
                errores.append(
                    f"Fila #{idx} ({emp_nombre}): El importe individual debe ser mayor a cero."
                )
            else:
                total_nomina += float(line.amount)

        if total_nomina <= 0:
            errores.append("El importe total de la dispersion de nomina debe ser mayor a cero.")

    else:
        # Modo individual convencional (un solo beneficiario)
        if not payment.partner_id:
            errores.append("Debe seleccionar al menos un empleado en la tabla de nomina.")
        elif not payment.partner_id.name:
            errores.append("El empleado asignado no tiene nombre registrado.")

        if not payment.partner_bank_id:
            errores.append("El empleado no tiene una cuenta bancaria registrada.")
        elif not payment.partner_bank_id.acc_number:
            errores.append("La cuenta bancaria del empleado no tiene numero de cuenta.")
        else:
            cuenta_ben = payment.partner_bank_id.acc_number
            if not validar_cuenta_nomina_hsbc(cuenta_ben):
                errores.append(
                    f"La cuenta beneficiaria de nomina '{cuenta_ben}' debe tener "
                    f"{CUENTA_NOMINA_LENGTH} digitos numericos (cuenta de nomina HSBC interna)."
                )

        if not payment.amount or payment.amount <= 0:
            errores.append("El monto del pago debe ser mayor a cero.")

    if errores:
        raise UserError(
            "No se puede generar el XML de Nomina HSBC. "
            "Corrija los siguientes problemas antes de continuar:\n\n"
            + "\n".join(f"- {e}" for e in errores)
        )


def validar_xml_nomina(xml_bytes: bytes) -> None:
    """
    Valida la estructura y contenido del archivo XML generado para Nómina HSBC.
    Verifica que cumpla con el estándar pain.001.001.03 y las especificaciones
    validadas por HSBC México:
      - Bien formado y parseable
      - Raíz Document con namespace ISO 20022 correcto
      - GrpHdr con MsgId, CreDtTm, NbOfTxs, CtrlSum
      - InitgPty con Id de cliente
      - PmtInf con SvcLvl='NURG'
      - PmtInf con CtgyPurp/Cd='SALA' (identificador de nómina obligatorio)
      - Cuenta ordenante de nómina (10 dígitos)
      - Cada CdtTrfTxInf con InstrId y EndToEndId conteniendo 'NOMINA'
      - Moneda MXN en cada importe
      - Banco beneficiario MmbId = '021'
      - Cuenta beneficiaria de 10 dígitos (HSBC interna)
      - Suma de importes coincidente con CtrlSum
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise UserError(f"Error de estructura XML en Nomina: El archivo no es un XML valido o esta mal formado:\n{e}")

    ns = XML_NAMESPACE
    if not (root.tag == "Document" or root.tag == f"{{{ns}}}Document"):
        raise UserError(f"Estructura Nomina invalida: La etiqueta raiz debe ser 'Document'. Encontrado: {root.tag}")

    def find_node(parent, tag):
        n = parent.find(tag)
        if n is None:
            n = parent.find(f"{{{ns}}}{tag}")
        return n

    def find_all_nodes(parent, tag):
        nodes = parent.findall(tag)
        if not nodes:
            nodes = parent.findall(f"{{{ns}}}{tag}")
        return nodes

    def get_val(parent, tag):
        node = find_node(parent, tag)
        return (node.text or "").strip() if node is not None else ""

    cstmr = find_node(root, "CstmrCdtTrfInitn")
    if cstmr is None:
        raise UserError("Estructura Nomina invalida: Falta la seccion 'CstmrCdtTrfInitn'.")

    # GrpHdr
    grp = find_node(cstmr, "GrpHdr")
    if grp is None:
        raise UserError("Estructura Nomina invalida: Falta el encabezado 'GrpHdr'.")

    if not get_val(grp, "MsgId"):
        raise UserError("Estructura Nomina invalida: 'GrpHdr/MsgId' es obligatorio.")
    if not get_val(grp, "CreDtTm"):
        raise UserError("Estructura Nomina invalida: 'GrpHdr/CreDtTm' es obligatorio.")

    nb_of_txs_str = get_val(grp, "NbOfTxs")
    if not nb_of_txs_str or not nb_of_txs_str.isdigit() or int(nb_of_txs_str) < 1:
        raise UserError("Estructura Nomina invalida: 'GrpHdr/NbOfTxs' debe ser un numero entero mayor a cero.")

    ctrl_sum_str = get_val(grp, "CtrlSum")
    if not ctrl_sum_str:
        raise UserError("Estructura Nomina invalida: 'GrpHdr/CtrlSum' es obligatorio.")

    # PmtInf
    pmt_inf = find_node(cstmr, "PmtInf")
    if pmt_inf is None:
        raise UserError("Estructura Nomina invalida: Falta la seccion 'PmtInf'.")

    # SvcLvl = NURG y CtgyPurp = SALA
    pmt_tp = find_node(pmt_inf, "PmtTpInf")
    if pmt_tp is None:
        raise UserError("Estructura Nomina invalida: Falta 'PmtInf/PmtTpInf'.")

    svc_lvl = find_node(pmt_tp, "SvcLvl")
    svc_code = get_val(svc_lvl, "Cd") if svc_lvl is not None else ""
    if svc_code != "NURG":
        raise UserError(f"Estructura Nomina invalida: SvcLvl/Cd debe ser 'NURG'. Encontrado: '{svc_code}'.")

    ctgy = find_node(pmt_tp, "CtgyPurp")
    if ctgy is None:
        raise UserError("Estructura Nomina invalida: Falta 'PmtTpInf/CtgyPurp' con el codigo de salario SALA.")
    ctgy_code = get_val(ctgy, "Cd")
    if ctgy_code != "SALA":
        raise UserError(f"Estructura Nomina invalida: CtgyPurp/Cd debe ser 'SALA'. Encontrado: '{ctgy_code}'.")

    # DbtrAcct con cuenta de 10 dígitos
    dbtr_acct = find_node(pmt_inf, "DbtrAcct")
    if dbtr_acct is None:
        raise UserError("Estructura Nomina invalida: Falta 'PmtInf/DbtrAcct'.")
    dbtr_acct_id = find_node(find_node(dbtr_acct, "Id") or dbtr_acct, "Othr")
    cuenta_ord = get_val(dbtr_acct_id or dbtr_acct, "Id") if dbtr_acct_id is not None else ""
    if len(cuenta_ord) != 10 or not cuenta_ord.isdigit():
        raise UserError(
            f"Estructura Nomina invalida: La cuenta ordenante en DbtrAcct debe tener 10 digitos. "
            f"Encontrado: '{cuenta_ord}'."
        )

    # CdtTrfTxInf: validar todas las transacciones incluidas
    transacciones = find_all_nodes(pmt_inf, "CdtTrfTxInf")
    if not transacciones:
        raise UserError("Estructura Nomina invalida: Falta la instruccion de pago 'CdtTrfTxInf'.")

    if len(transacciones) != int(nb_of_txs_str):
        raise UserError(
            f"Estructura Nomina invalida: La cantidad de transacciones ({len(transacciones)}) "
            f"no coincide con NbOfTxs ({nb_of_txs_str})."
        )

    suma_montos = Decimal("0.00")
    for idx, cdt in enumerate(transacciones, start=1):
        pmt_id = find_node(cdt, "PmtId")
        if pmt_id is None:
            raise UserError(f"Estructura Nomina invalida: Falta 'PmtId' en transaccion #{idx}.")

        instr_id = get_val(pmt_id, "InstrId")
        end_to_end = get_val(pmt_id, "EndToEndId")
        if "NOMINA" not in instr_id.upper() or "NOMINA" not in end_to_end.upper():
            raise UserError(
                f"Estructura Nomina invalida en transaccion #{idx}: InstrId y EndToEndId DEBEN contener la palabra 'NOMINA'. "
                f"InstrId='{instr_id}', EndToEndId='{end_to_end}'."
            )

        amt = find_node(cdt, "Amt")
        if amt is None:
            raise UserError(f"Estructura Nomina invalida: Falta 'Amt' en transaccion #{idx}.")
        instd_amt = find_node(amt, "InstdAmt")
        if instd_amt is None or instd_amt.get("Ccy") != "MXN":
            raise UserError(
                f"Estructura Nomina invalida en transaccion #{idx}: La moneda 'Ccy' debe ser 'MXN'."
            )
        try:
            monto_val = Decimal(instd_amt.text or "0")
            suma_montos += monto_val
        except Exception:
            raise UserError(f"Estructura Nomina invalida: Monto numerico invalido en transaccion #{idx}.")

        # CdtrAgt / ClrSysMmbId / MmbId = "021"
        cdtr_agt = find_node(cdt, "CdtrAgt")
        clr_sys = find_node(find_node(cdtr_agt or cdt, "FinInstnId") or cdt, "ClrSysMmbId")
        banco_ben = get_val(clr_sys or cdt, "MmbId") if clr_sys is not None else ""
        if banco_ben != "021":
            raise UserError(
                f"Estructura Nomina invalida en transaccion #{idx}: El banco beneficiario en ClrSysMmbId debe ser '021' (HSBC). "
                f"Encontrado: '{banco_ben}'."
            )

        # CdtrAcct con cuenta interna HSBC de 10 dígitos
        cdtr_acct = find_node(cdt, "CdtrAcct")
        if cdtr_acct is None:
            raise UserError(f"Estructura Nomina invalida: Falta 'CdtrAcct' en transaccion #{idx}.")
        cdtr_acct_id = find_node(find_node(cdtr_acct, "Id") or cdtr_acct, "Othr")
        cuenta_ben = get_val(cdtr_acct_id or cdtr_acct, "Id") if cdtr_acct_id is not None else ""
        if len(cuenta_ben) != 10 or not cuenta_ben.isdigit():
            raise UserError(
                f"Estructura Nomina invalida en transaccion #{idx}: La cuenta beneficiaria en CdtrAcct debe tener 10 digitos (cuenta HSBC). "
                f"Encontrado: '{cuenta_ben}'."
            )

    # Validar que suma_montos coincida con CtrlSum
    ctrl_sum_dec = Decimal(ctrl_sum_str)
    if abs(suma_montos - ctrl_sum_dec) > Decimal("0.01"):
        raise UserError(
            f"Estructura Nomina invalida: La suma total de las transferencias ({suma_montos:.2f}) "
            f"no coincide con CtrlSum ({ctrl_sum_str})."
        )
