# -*- coding: utf-8 -*-
"""
Validaciones específicas para pagos SPEI.
Separadas del generador para facilitar pruebas unitarias y reutilización.
"""
from odoo.exceptions import UserError
from .constants import CLABE_LENGTH, CURRENCY


def validar_clabe(clabe: str) -> bool:
    """
    Valida que una CLABE interbancaria tenga 18 dígitos.

    MODO PRUEBAS: solo verifica longitud y que sean dígitos.
    Para activar validación completa del dígito verificador (producción),
    descomentar el bloque de abajo y eliminar el return de abajo.
    """
    if not clabe or not clabe.isdigit():
        return False
    if len(clabe) != CLABE_LENGTH:
        return False
    return True

    # ── Validación completa BANXICO (activar en producción) ──────────────────
    # pesos = [3, 7, 1] * 6
    # suma = sum(int(d) * p for d, p in zip(clabe[:17], pesos))
    # digito = (10 - (suma % 10)) % 10
    # return digito == int(clabe[17])


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
            f"(debe tener {CLABE_LENGTH} dígitos con dígito verificador correcto)."
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
