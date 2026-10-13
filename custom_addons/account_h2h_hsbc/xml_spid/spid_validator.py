# -*- coding: utf-8 -*-
"""
Validaciones específicas para pagos SPID (Sistema de Pagos Interbancarios en Dólares)
y de su estructura XML final generada.
Reglas basadas en el generador original validado por HSBC.

Reglas específicas de SPID:
- Banco beneficiario NO puede ser 021 (HSBC, que solo acepta MXN).
- CLABE beneficiaria: 18 dígitos, y sus primeros 3 coinciden con el MmbId (banco).
- RFC del beneficiario: obligatorio.
- Código de operación SPID: obligatorio (01-08).
- Referencia larga (Ustrd): máximo 40 caracteres.
- EndToEndId: solo dígitos, máximo 15.
- Cuenta ordenante: 10 dígitos, inicia con "70".
- Moneda: USD.
"""
import xml.etree.ElementTree as ET
try:
    from odoo.exceptions import UserError
except ImportError:
    class UserError(Exception):
        pass

from .constants import (
    CLABE_LENGTH, CURRENCY, XML_NAMESPACE,
    BANCO_HSBC_EXCLUIDO,
    CUENTA_ORDENANTE_LENGTH, CUENTA_ORDENANTE_PREFIJO,
    END_TO_END_MAX_DIGITS, USTRD_MAX_LENGTH,
    CODIGOS_OPERACION_SPID,
)


def referencia_end_to_end(referencia: str) -> str:
    """
    Extrae los dígitos de la referencia para usarla como EndToEndId en SPID.
    HSBC requiere que EndToEndId sea numérico y no supere 15 dígitos.
    """
    digitos = "".join(c for c in str(referencia) if c.isdigit())
    if not digitos or len(digitos) > END_TO_END_MAX_DIGITS:
        raise UserError(
            f"La referencia EndToEndId de SPID debe contener entre 1 y "
            f"{END_TO_END_MAX_DIGITS} dígitos numéricos. "
            f"Valor actual: '{referencia}'."
        )
    return digitos


def validar_clabe_spid(cuenta: str) -> bool:
    """
    Valida que la CLABE beneficiaria SPID tenga 18 dígitos.
    """
    return bool(cuenta and cuenta.isdigit() and len(cuenta) == CLABE_LENGTH)


def validar_pago_spid(payment) -> None:
    """
    Valida que el pago tenga todos los datos requeridos para generar XML SPID.
    Lanza UserError describiendo exactamente qué falta.
    """
    errores = []

    # ── Cuenta ordenante SPID (10 dígitos, inicia con "70") ──────────────────
    cuenta_ord = (
        payment.journal_id.bank_account_id.acc_number
        if payment.journal_id.bank_account_id
        else ''
    ) or ''
    if not cuenta_ord:
        errores.append("El diario HSBC no tiene configurada la cuenta bancaria de la empresa.")
    elif len(cuenta_ord) != CUENTA_ORDENANTE_LENGTH or \
         not cuenta_ord.startswith(CUENTA_ORDENANTE_PREFIJO):
        errores.append(
            f"La cuenta ordenante SPID '{cuenta_ord}' debe tener "
            f"{CUENTA_ORDENANTE_LENGTH} dígitos y comenzar con '{CUENTA_ORDENANTE_PREFIJO}'."
        )

    # ── Cuenta bancaria del beneficiario (CLABE 18 dígitos) ───────────────────
    if not payment.partner_bank_id:
        errores.append("El beneficiario no tiene cuenta bancaria registrada en este pago.")
    elif not payment.partner_bank_id.acc_number:
        errores.append("La cuenta bancaria del beneficiario no tiene número de cuenta.")
    else:
        cuenta_ben = payment.partner_bank_id.acc_number
        banco_ben  = cuenta_ben[:3] if len(cuenta_ben) >= 3 else ''

        if not validar_clabe_spid(cuenta_ben):
            errores.append(
                f"La CLABE beneficiaria SPID '{cuenta_ben}' no es válida "
                f"(debe tener {CLABE_LENGTH} dígitos numéricos)."
            )
        elif banco_ben == BANCO_HSBC_EXCLUIDO:
            errores.append(
                f"El banco beneficiario '{banco_ben}' (HSBC/021) no está permitido para SPID. "
                f"SPID solo aplica para transferencias a bancos distintos de HSBC."
            )

    # ── ID cliente HSBC ────────────────────────────────────────────────────────
    if not payment.journal_id.hsbc_client_id:
        errores.append(
            "El diario HSBC no tiene configurado el ID de cliente HSBC. "
            "(Ve a Contabilidad → Configuración → Diarios → sección HSBC H2H)."
        )

    # ── Proveedor ─────────────────────────────────────────────────────────────
    if not payment.partner_id:
        errores.append("El pago no tiene beneficiario asignado.")
    elif not payment.partner_id.name:
        errores.append("El beneficiario no tiene nombre registrado.")

    # ── RFC del beneficiario (obligatorio para SPID) ──────────────────────────
    rfc = getattr(payment, 'h2h_spid_rfc', None) or \
          getattr(payment.partner_id, 'vat', None) or ''
    if not rfc or not rfc.strip():
        errores.append(
            "El RFC del beneficiario es obligatorio para SPID. "
            "Configúralo en el campo 'RFC Beneficiario SPID' o en el RFC del proveedor."
        )

    # ── Código de operación SPID (obligatorio) ────────────────────────────────
    codigo = getattr(payment, 'h2h_spid_codigo', None) or ''
    if not codigo or codigo not in CODIGOS_OPERACION_SPID:
        errores.append(
            f"El código de operación SPID es obligatorio. "
            f"Selecciona uno de: {', '.join(f'{k} ({v})' for k, v in CODIGOS_OPERACION_SPID.items())}."
        )

    # ── Referencia larga (Ustrd, max 40 chars) ────────────────────────────────
    ref_larga = getattr(payment, 'h2h_spid_referencia_larga', None) or ''
    if ref_larga and len(ref_larga) > USTRD_MAX_LENGTH:
        errores.append(
            f"La referencia larga SPID (Ustrd) no puede superar {USTRD_MAX_LENGTH} caracteres. "
            f"Valor actual: {len(ref_larga)} caracteres."
        )

    # ── Monto ─────────────────────────────────────────────────────────────────
    if not payment.amount or payment.amount <= 0:
        errores.append("El monto del pago debe ser mayor a cero.")

    # ── Moneda ────────────────────────────────────────────────────────────────
    if payment.currency_id and payment.currency_id.name != CURRENCY:
        errores.append(
            f"SPID opera en {CURRENCY} (dólares americanos). "
            f"La moneda del pago es {payment.currency_id.name}."
        )

    # ── Empresa ───────────────────────────────────────────────────────────────
    if not payment.company_id.name:
        errores.append("La empresa no tiene nombre configurado.")

    if errores:
        raise UserError(
            "No se puede generar el XML SPID. "
            "Corrige los siguientes problemas:\n\n"
            + "\n".join(f"• {e}" for e in errores)
        )


def validar_xml_spid(xml_bytes: bytes) -> None:
    """
    Valida la estructura y contenido del archivo XML generado para SPID.
    Verifica que cumpla con el estándar pain.001.001.03 y las especificaciones
    validadas por HSBC México:
      - Bien formado y parseable
      - Raíz Document con namespace correcto
      - GrpHdr con MsgId, CreDtTm, NbOfTxs='1', CtrlSum coincidente
      - InitgPty con Id de cliente
      - PmtInf con SvcLvl='URGP'
      - Cuenta ordenante de 10 dígitos iniciando con '70'
      - CdtTrfTxInf con moneda USD
      - EndToEndId numérico de hasta 15 dígitos
      - Banco beneficiario ≠ 021 y coincidente con los 3 primeros dígitos de la CLABE
      - CLABE beneficiaria de 18 dígitos
      - RgltryRptg con '/SPID/OC/{codigo}'
      - Tax con RFC del beneficiario
      - RmtInf/Ustrd <= 40 caracteres
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise UserError(f"Error de estructura XML en SPID: El archivo no es un XML válido o está mal formado:\n{e}")

    ns = XML_NAMESPACE
    if not (root.tag == "Document" or root.tag == f"{{{ns}}}Document"):
        raise UserError(f"Estructura SPID inválida: La etiqueta raíz debe ser 'Document'. Encontrado: {root.tag}")

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
        raise UserError("Estructura SPID inválida: Falta la sección 'CstmrCdtTrfInitn'.")

    # GrpHdr
    grp = find_node(cstmr, "GrpHdr")
    if grp is None:
        raise UserError("Estructura SPID inválida: Falta el encabezado 'GrpHdr'.")

    if not get_val(grp, "MsgId"):
        raise UserError("Estructura SPID inválida: 'GrpHdr/MsgId' es obligatorio.")
    if not get_val(grp, "CreDtTm"):
        raise UserError("Estructura SPID inválida: 'GrpHdr/CreDtTm' es obligatorio.")
    if get_val(grp, "NbOfTxs") != "1":
        raise UserError("Estructura SPID inválida: 'GrpHdr/NbOfTxs' debe ser '1'.")
    if not get_val(grp, "CtrlSum"):
        raise UserError("Estructura SPID inválida: 'GrpHdr/CtrlSum' es obligatorio.")

    # PmtInf
    pmt_inf = find_node(cstmr, "PmtInf")
    if pmt_inf is None:
        raise UserError("Estructura SPID inválida: Falta la sección 'PmtInf'.")

    pmt_tp = find_node(pmt_inf, "PmtTpInf")
    if pmt_tp is None:
        raise UserError("Estructura SPID inválida: Falta 'PmtInf/PmtTpInf'.")
    svc_lvl = find_node(pmt_tp, "SvcLvl")
    svc_code = get_val(svc_lvl, "Cd") if svc_lvl is not None else ""
    if svc_code != "URGP":
        raise UserError(f"Estructura SPID inválida: SvcLvl/Cd debe ser 'URGP'. Encontrado: '{svc_code}'.")

    # Cuenta ordenante SPID: 10 dígitos e inicia con "70"
    dbtr_acct = find_node(pmt_inf, "DbtrAcct")
    if dbtr_acct is None:
        raise UserError("Estructura SPID inválida: Falta 'PmtInf/DbtrAcct'.")
    dbtr_acct_id = find_node(find_node(dbtr_acct, "Id") or dbtr_acct, "Othr")
    cuenta_ord = get_val(dbtr_acct_id or dbtr_acct, "Id") if dbtr_acct_id is not None else ""
    if len(cuenta_ord) != 10 or not cuenta_ord.startswith("70"):
        raise UserError(
            f"Estructura SPID inválida: La cuenta ordenante en DbtrAcct debe tener 10 dígitos y comenzar con '70'. "
            f"Encontrado: '{cuenta_ord}'."
        )

    # CdtTrfTxInf
    cdt = find_node(pmt_inf, "CdtTrfTxInf")
    if cdt is None:
        raise UserError("Estructura SPID inválida: Falta la instrucción de pago 'CdtTrfTxInf'.")

    # PmtId / EndToEndId: sólo dígitos y hasta 15 dígitos
    pmt_id = find_node(cdt, "PmtId")
    if pmt_id is None:
        raise UserError("Estructura SPID inválida: Falta 'CdtTrfTxInf/PmtId'.")
    end_to_end = get_val(pmt_id, "EndToEndId")
    if not end_to_end or not end_to_end.isdigit() or len(end_to_end) > 15:
        raise UserError(
            f"Estructura SPID inválida: EndToEndId debe ser numérico y contener entre 1 y 15 dígitos. "
            f"Encontrado: '{end_to_end}'."
        )

    # Moneda USD obligatoria
    amt = find_node(cdt, "Amt")
    if amt is None:
        raise UserError("Estructura SPID inválida: Falta 'CdtTrfTxInf/Amt'.")
    instd_amt = find_node(amt, "InstdAmt")
    if instd_amt is None or instd_amt.get("Ccy") != "USD":
        raise UserError(
            f"Estructura SPID inválida: La moneda 'Ccy' debe ser 'USD'. "
            f"Encontrado: '{instd_amt.get('Ccy') if instd_amt is not None else 'None'}'."
        )

    # CdtrAcct (CLABE de 18 dígitos)
    cdtr_acct = find_node(cdt, "CdtrAcct")
    if cdtr_acct is None:
        raise UserError("Estructura SPID inválida: Falta 'CdtTrfTxInf/CdtrAcct'.")
    cdtr_acct_id = find_node(find_node(cdtr_acct, "Id") or cdtr_acct, "Othr")
    cuenta_ben = get_val(cdtr_acct_id or cdtr_acct, "Id") if cdtr_acct_id is not None else ""
    if len(cuenta_ben) != 18 or not cuenta_ben.isdigit():
        raise UserError(
            f"Estructura SPID inválida: La cuenta beneficiaria en CdtrAcct debe tener 18 dígitos (CLABE). "
            f"Encontrado: '{cuenta_ben}'."
        )

    # CdtrAgt / ClrSysMmbId / MmbId no puede ser 021 y debe coincidir con cuenta_ben[:3]
    cdtr_agt = find_node(cdt, "CdtrAgt")
    clr_sys = find_node(find_node(cdtr_agt or cdt, "FinInstnId") or cdt, "ClrSysMmbId")
    banco_ben = get_val(clr_sys or cdt, "MmbId") if clr_sys is not None else ""
    if banco_ben == "021":
        raise UserError(
            "Estructura SPID inválida: El banco beneficiario 021 (HSBC) no corresponde a una transferencia SPID."
        )
    if banco_ben != cuenta_ben[:3]:
        raise UserError(
            f"Estructura SPID inválida: El banco beneficiario MmbId '{banco_ben}' debe coincidir con los 3 primeros dígitos de la CLABE '{cuenta_ben[:3]}'."
        )

    # RgltryRptg / Dtls / Inf debe tener /SPID/OC/{codigo}
    rgltry = find_node(cdt, "RgltryRptg")
    if rgltry is None:
        raise UserError("Estructura SPID inválida: Falta el elemento 'RgltryRptg' con el código de operación SPID.")
    inf_val = get_val(find_node(rgltry, "Dtls") or rgltry, "Inf")
    if not inf_val.startswith("/SPID/OC/"):
        raise UserError(
            f"Estructura SPID inválida: RgltryRptg/Dtls/Inf debe iniciar con '/SPID/OC/'. Encontrado: '{inf_val}'."
        )

    # Tax / Cdtr / TaxId (RFC obligatorio)
    tax = find_node(cdt, "Tax")
    if tax is None:
        raise UserError("Estructura SPID inválida: Falta el elemento 'Tax' con el RFC del beneficiario.")
    tax_id = get_val(find_node(tax, "Cdtr") or tax, "TaxId")
    if not tax_id:
        raise UserError("Estructura SPID inválida: El RFC en 'Tax/Cdtr/TaxId' es obligatorio para pagos SPID.")

    # RmtInf / Ustrd <= 40
    rmt_inf = find_node(cdt, "RmtInf")
    if rmt_inf is not None:
        ustrd = get_val(rmt_inf, "Ustrd")
        if len(ustrd) > 40:
            raise UserError(
                f"Estructura SPID inválida: La referencia en 'RmtInf/Ustrd' supera el límite de 40 caracteres ({len(ustrd)} caracteres)."
            )
