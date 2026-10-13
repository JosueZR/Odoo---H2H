# -*- coding: utf-8 -*-
"""
Constantes específicas para pagos SPID (Sistema de Pagos Interbancarios en Dólares).
SPID opera en USD y usa el mismo estándar pain.001.001.03.

Reglas especiales de SPID validadas por HSBC:
- Moneda: USD (dólares americanos).
- Banco beneficiario NO puede ser 021 (ese banco solo acepta MXN/ACH).
- Los 3 primeros dígitos de la CLABE beneficiaria deben coincidir con el MmbId.
- EndToEndId debe ser numérico (solo dígitos, max 15).
- RFC del beneficiario es OBLIGATORIO (campo Tax/Cdtr/TaxId).
- Código de operación SPID es OBLIGATORIO (RgltryRptg/Dtls/Inf = "/SPID/OC/{Codigo}").
- RmtInf/Ustrd (referencia larga) máximo 40 caracteres.
- Cuenta ordenante SPID: 10 dígitos y debe comenzar con "70".
"""

# Namespace XML ISO 20022 — igual para todos los tipos
XML_NAMESPACE     = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"
XML_NAMESPACE_XSI = "http://www.w3.org/2001/XMLSchema-instance"

# Método de pago
PMT_MTD = "TRF"

# Nivel de servicio: URGP (urgente, igual que SPEI pero en USD)
SVC_LVL_CODE = "URGP"

# Moneda de operación (SPID en dólares americanos)
CURRENCY = "USD"

# País de operación
COUNTRY = "MX"

# BIC por defecto HSBC México
BIC_DEFAULT = "BIMEMXMM"

# Banco HSBC (NO permitido como destino SPID)
BANCO_HSBC_EXCLUIDO = "021"

# Longitud de la CLABE beneficiaria SPID (interbancaria 18 dígitos)
CLABE_LENGTH = 18

# Longitud de la cuenta ordenante SPID (10 dígitos, debe iniciar con "70")
CUENTA_ORDENANTE_LENGTH = 10
CUENTA_ORDENANTE_PREFIJO = "70"

# Longitud máxima de EndToEndId numérico SPID
END_TO_END_MAX_DIGITS = 15

# Longitud máxima de referencia larga (Ustrd) — HSBC rechaza si excede
USTRD_MAX_LENGTH = 40

# Codigos de clasificación de operación SPID (RgltryRptg/Dtls/Inf)
# Formato en XML: "/SPID/OC/{codigo}"
CODIGOS_OPERACION_SPID = {
    "01": "Liquidación de operación con valores",
    "02": "Liquidación de operación derivada",
    "03": "Liquidación de operación cambiaria",
    "04": "Pago de servicios",
    "05": "Pago de bienes",
    "06": "Otorgamiento de préstamo",
    "07": "Pago de préstamo",
    "08": "Otros",
}
