# -*- coding: utf-8 -*-
"""
Validaciones específicas para pagos OPI (Orden de Pago Internacional / Cross Border)
y de su estructura XML final generada.

Reglas de OPI:
- Moneda: cualquiera distinta de MXN (USD, EUR, GBP, ...).
- Banco beneficiario identificado por BIC (8 u 11 caracteres), no por clave local.
- Cuenta beneficiaria: IBAN o número de cuenta normal (Othr/Id).
- Beneficiario ubicado fuera de México, con dirección completa
  (calle, código postal, ciudad y país) — pedido por HSBC 09/2026.
- ChrgBr obligatorio: DEBT / CRED / SHAR.
- Purp/Cd obligatorio (código ISO global).
- RgltryRptg obligatorio: "/BENEFRES/MX//{01..22}".
- RmtInf/Ustrd máximo 140 caracteres.
"""
import re
import unicodedata
import xml.etree.ElementTree as ET
try:
    from odoo.exceptions import UserError
except ImportError:
    class UserError(Exception):
        pass

from .constants import (
    XML_NAMESPACE, SVC_LVL_CODE, CURRENCY_EXCLUIDA,
    NOMBRE_MAX_LENGTH, DIRECCION_MAX_LENGTH, USTRD_MAX_LENGTH,
    END_TO_END_MAX_LENGTH,
    CHRGBR_OPCIONES, PURP_CODES, CODIGOS_REGULATORIOS_OPI, RGLTRY_PREFIJO,
)

_BIC_RE  = re.compile(r"^[A-Z]{4}[A-Z]{2}[A-Z0-9]{2}([A-Z0-9]{3})?$")
_IBAN_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{10,30}$")


# ─────────────────────────────────────────────────────────────────────────────
# Utilidades compartidas con el generador
# ─────────────────────────────────────────────────────────────────────────────
def texto_swift(valor) -> str:
    """
    Normaliza texto para pagos internacionales: quita acentos/ñ y caracteres
    fuera de ASCII (la red SWIFT usa un juego de caracteres restringido).
    """
    if not valor:
        return ""
    normal = unicodedata.normalize("NFKD", str(valor))
    ascii_ = normal.encode("ascii", "ignore").decode("ascii")
    return re.sub(r"\s+", " ", ascii_).strip()


def obtener_bic_beneficiario(payment) -> str:
    """BIC del banco beneficiario: partner_bank_id.bank_id.bic (res.bank)."""
    bank = getattr(payment, "partner_bank_id", None)
    bank_id = getattr(bank, "bank_id", None) if bank else None
    return (getattr(bank_id, "bic", None) or "").strip().upper().replace(" ", "")


def obtener_cuenta_beneficiario(payment):
    """
    Devuelve (tipo, valor) con tipo 'IBAN' o 'OTHR'.
    Usa acc_type de res.partner.bank cuando existe; si no, detecta por formato.
    """
    bank = getattr(payment, "partner_bank_id", None)
    numero = (getattr(bank, "acc_number", None) or "") if bank else ""
    limpio = re.sub(r"[\s-]", "", numero).upper()
    if getattr(bank, "acc_type", None) == "iban" or _IBAN_RE.match(limpio):
        return "IBAN", limpio
    return "OTHR", numero.strip()


def obtener_pais_beneficiario(payment) -> str:
    country = getattr(payment.partner_id, "country_id", None)
    return (getattr(country, "code", None) or "").strip().upper()


def referencia_opi(safe_name: str, fecha_yyyymmdd: str) -> str:
    """Referencia InstrId/EndToEndId (Max35Text, solo caracteres seguros)."""
    base = re.sub(r"[^A-Za-z0-9]", "", f"OPI{fecha_yyyymmdd}{safe_name}")
    return base[:END_TO_END_MAX_LENGTH]


# ─────────────────────────────────────────────────────────────────────────────
# Validación previa del pago (datos de Odoo)
# ─────────────────────────────────────────────────────────────────────────────
def validar_pago_opi(payment) -> None:
    """
    Valida que el pago tenga todos los datos requeridos para generar XML OPI.
    Lanza UserError describiendo exactamente qué falta.
    """
    errores = []
    partner = payment.partner_id

    # ── Cuenta ordenante ──────────────────────────────────────────────────────
    cuenta_ord = (
        payment.journal_id.bank_account_id.acc_number
        if payment.journal_id.bank_account_id else ""
    ) or ""
    if not cuenta_ord:
        errores.append("El diario HSBC no tiene configurada la cuenta bancaria de la empresa.")
    elif not cuenta_ord.isdigit():
        errores.append(f"La cuenta ordenante '{cuenta_ord}' debe contener solo dígitos.")

    if not payment.journal_id.hsbc_client_id:
        errores.append(
            "El diario HSBC no tiene configurado el ID de cliente HSBC. "
            "(Ve a Contabilidad → Configuración → Diarios → sección HSBC H2H)."
        )

    # ── Beneficiario ──────────────────────────────────────────────────────────
    if not partner:
        errores.append("El pago no tiene beneficiario asignado.")
    else:
        if not partner.name:
            errores.append("El beneficiario no tiene nombre registrado.")
        elif len(texto_swift(partner.name)) > NOMBRE_MAX_LENGTH:
            errores.append(f"El nombre del beneficiario supera {NOMBRE_MAX_LENGTH} caracteres.")

        faltantes = [
            etiqueta for etiqueta, valor in (
                ("calle", partner.street),
                ("código postal", partner.zip),
                ("ciudad", partner.city),
                ("país", getattr(partner, "country_id", None)),
            ) if not valor
        ]
        if faltantes:
            errores.append(
                "El beneficiario necesita dirección completa para OPI. "
                f"Falta: {', '.join(faltantes)}."
            )
        else:
            if len(texto_swift(partner.street)) > DIRECCION_MAX_LENGTH:
                errores.append(f"La calle del beneficiario supera {DIRECCION_MAX_LENGTH} caracteres.")
            if len(texto_swift(partner.city)) > DIRECCION_MAX_LENGTH:
                errores.append(f"La ciudad del beneficiario supera {DIRECCION_MAX_LENGTH} caracteres.")
            if obtener_pais_beneficiario(payment) == "MX":
                errores.append(
                    "El beneficiario está en México. OPI es para beneficiarios en el "
                    "extranjero; para pagos nacionales usa SPEI, SPID o Servicios."
                )

    # ── Banco y cuenta del beneficiario ──────────────────────────────────────
    if not payment.partner_bank_id:
        errores.append("El beneficiario no tiene cuenta bancaria registrada en este pago.")
    else:
        bic = obtener_bic_beneficiario(payment)
        if not bic:
            errores.append(
                "El banco del beneficiario no tiene BIC/SWIFT. Edita la cuenta bancaria del "
                "proveedor y asígnale un Banco con su BIC."
            )
        elif not _BIC_RE.match(bic):
            errores.append(f"El BIC '{bic}' no es válido (debe tener 8 u 11 caracteres alfanuméricos).")

        _tipo, cuenta_ben = obtener_cuenta_beneficiario(payment)
        if not cuenta_ben:
            errores.append("La cuenta bancaria del beneficiario no tiene número de cuenta/IBAN.")

    # ── Moneda y monto ────────────────────────────────────────────────────────
    if not payment.currency_id:
        errores.append("El pago no tiene moneda.")
    elif payment.currency_id.name == CURRENCY_EXCLUIDA:
        errores.append(
            "OPI requiere moneda extranjera (USD, EUR, GBP, ...). "
            f"La moneda del pago es {payment.currency_id.name}."
        )
    if not payment.amount or payment.amount <= 0:
        errores.append("El monto del pago debe ser mayor a cero.")

    # ── Campos propios de OPI ─────────────────────────────────────────────────
    chrgbr = getattr(payment, "h2h_opi_chrgbr", None) or ""
    if chrgbr not in CHRGBR_OPCIONES:
        errores.append(f"Selecciona quién paga las comisiones: {', '.join(CHRGBR_OPCIONES)}.")

    purp = getattr(payment, "h2h_opi_purp_code", None) or ""
    if purp not in PURP_CODES:
        errores.append(f"El propósito ISO (Purp) es obligatorio. Opciones: {', '.join(PURP_CODES)}.")

    reg = getattr(payment, "h2h_opi_reg_code", None) or ""
    if reg not in CODIGOS_REGULATORIOS_OPI:
        errores.append("El propósito regulatorio (01 a 22) es obligatorio para OPI.")

    ref_larga = getattr(payment, "h2h_opi_referencia_larga", None) or ""
    if len(texto_swift(ref_larga)) > USTRD_MAX_LENGTH:
        errores.append(f"La referencia (Ustrd) no puede superar {USTRD_MAX_LENGTH} caracteres.")

    if not payment.company_id.name:
        errores.append("La empresa no tiene nombre configurado.")

    if errores:
        raise UserError(
            "No se puede generar el XML OPI. Corrige los siguientes problemas:\n\n"
            + "\n".join(f"• {e}" for e in errores)
        )


# ─────────────────────────────────────────────────────────────────────────────
# Validación estructural del XML generado
# ─────────────────────────────────────────────────────────────────────────────
def validar_xml_opi(xml_bytes: bytes) -> None:
    """
    Valida estructura y contenido del XML OPI generado:
      - Bien formado, raíz Document con namespace correcto
      - GrpHdr (MsgId, CreDtTm, NbOfTxs='1', CtrlSum) e InitgPty con ID de cliente
      - SvcLvl='URGP'
      - InstdAmt con moneda distinta de MXN
      - ChrgBr en DEBT/CRED/SHAR
      - CdtrAgt con BIC válido (sin ClrSysMmbId)
      - Cdtr con dirección completa (StrtNm, PstCd, TwnNm, Ctry) y Ctry != MX
      - CdtrAcct con IBAN o Othr/Id
      - RgltryRptg '/BENEFRES/MX//XX'
      - Purp/Cd presente
      - RmtInf/Ustrd <= 140
    """
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as e:
        raise UserError(f"Error de estructura XML en OPI: el archivo está mal formado:\n{e}")

    ns = XML_NAMESPACE
    if root.tag not in ("Document", f"{{{ns}}}Document"):
        raise UserError(f"Estructura OPI inválida: la raíz debe ser 'Document'. Encontrado: {root.tag}")

    def find(parent, tag):
        if parent is None:
            return None
        n = parent.find(tag)
        return n if n is not None else parent.find(f"{{{ns}}}{tag}")

    def val(parent, tag):
        n = find(parent, tag)
        return (n.text or "").strip() if n is not None else ""

    def need(parent, tag, ruta):
        n = find(parent, tag)
        if n is None:
            raise UserError(f"Estructura OPI inválida: falta '{ruta}'.")
        return n

    cstmr = need(root, "CstmrCdtTrfInitn", "CstmrCdtTrfInitn")
    grp = need(cstmr, "GrpHdr", "GrpHdr")
    for campo in ("MsgId", "CreDtTm", "CtrlSum"):
        if not val(grp, campo):
            raise UserError(f"Estructura OPI inválida: 'GrpHdr/{campo}' es obligatorio.")
    if val(grp, "NbOfTxs") != "1":
        raise UserError("Estructura OPI inválida: 'GrpHdr/NbOfTxs' debe ser '1'.")
    initg_id = val(find(find(find(find(grp, "InitgPty"), "Id"), "OrgId"), "Othr"), "Id")
    if not initg_id:
        raise UserError("Estructura OPI inválida: falta 'InitgPty/Id/OrgId/Othr/Id' (ID de cliente HSBC).")

    pmt = need(cstmr, "PmtInf", "PmtInf")
    svc = val(find(find(pmt, "PmtTpInf"), "SvcLvl"), "Cd")
    if svc != SVC_LVL_CODE:
        raise UserError(f"Estructura OPI inválida: SvcLvl/Cd debe ser '{SVC_LVL_CODE}'. Encontrado: '{svc}'.")

    cdt = need(pmt, "CdtTrfTxInf", "CdtTrfTxInf")

    # Moneda
    instd = find(find(cdt, "Amt"), "InstdAmt")
    if instd is None:
        raise UserError("Estructura OPI inválida: falta 'Amt/InstdAmt'.")
    ccy = instd.get("Ccy") or ""
    if not ccy or ccy == CURRENCY_EXCLUIDA:
        raise UserError(f"Estructura OPI inválida: la moneda debe ser extranjera. Encontrado: '{ccy}'.")

    # ChrgBr
    chrgbr = val(cdt, "ChrgBr")
    if chrgbr not in CHRGBR_OPCIONES:
        raise UserError(f"Estructura OPI inválida: ChrgBr debe ser DEBT, CRED o SHAR. Encontrado: '{chrgbr}'.")

    # Banco beneficiario: BIC (no ClrSysMmbId)
    fin = find(find(cdt, "CdtrAgt"), "FinInstnId")
    if fin is None:
        raise UserError("Estructura OPI inválida: falta 'CdtrAgt/FinInstnId'.")
    if find(fin, "ClrSysMmbId") is not None:
        raise UserError("Estructura OPI inválida: el banco beneficiario debe ir por BIC, no por ClrSysMmbId.")
    bic = val(fin, "BIC")
    if not _BIC_RE.match(bic):
        raise UserError(f"Estructura OPI inválida: BIC del banco beneficiario no válido: '{bic}'.")

    # Beneficiario y dirección completa
    cdtr = need(cdt, "Cdtr", "Cdtr")
    if not val(cdtr, "Nm"):
        raise UserError("Estructura OPI inválida: falta 'Cdtr/Nm'.")
    adr = need(cdtr, "PstlAdr", "Cdtr/PstlAdr")
    for campo in ("StrtNm", "PstCd", "TwnNm", "Ctry"):
        if not val(adr, campo):
            raise UserError(f"Estructura OPI inválida: falta 'Cdtr/PstlAdr/{campo}'.")
    if val(adr, "Ctry") == "MX":
        raise UserError("Estructura OPI inválida: el país del beneficiario no puede ser MX.")

    # Cuenta beneficiaria
    acct_id = find(find(cdt, "CdtrAcct"), "Id")
    if acct_id is None:
        raise UserError("Estructura OPI inválida: falta 'CdtrAcct/Id'.")
    if not (val(acct_id, "IBAN") or val(find(acct_id, "Othr"), "Id")):
        raise UserError("Estructura OPI inválida: 'CdtrAcct' requiere IBAN u Othr/Id con valor.")

    # Reporte regulatorio
    rgl = need(cdt, "RgltryRptg", "RgltryRptg")
    inf = val(find(rgl, "Dtls"), "Inf")
    if not re.fullmatch(re.escape(RGLTRY_PREFIJO) + r"\d{2}", inf) or inf[-2:] not in CODIGOS_REGULATORIOS_OPI:
        raise UserError(
            f"Estructura OPI inválida: RgltryRptg/Dtls/Inf debe ser '{RGLTRY_PREFIJO}XX' "
            f"con XX entre 01 y 22. Encontrado: '{inf}'."
        )

    # Propósito ISO
    if not val(find(cdt, "Purp"), "Cd"):
        raise UserError("Estructura OPI inválida: falta 'Purp/Cd'.")

    # Referencia
    rmt = find(cdt, "RmtInf")
    if rmt is not None and len(val(rmt, "Ustrd")) > USTRD_MAX_LENGTH:
        raise UserError(f"Estructura OPI inválida: 'RmtInf/Ustrd' supera {USTRD_MAX_LENGTH} caracteres.")
