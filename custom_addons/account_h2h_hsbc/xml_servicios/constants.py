# -*- coding: utf-8 -*-
"""
Constantes específicas para pagos de Servicios HSBC (ACH/SPEI a proveedores).
Pago de servicios o a proveedores en pesos MXN.
Utiliza SvcLvl NURG (no urgente) sin propósito de categoría (a diferencia de Nómina).
La cuenta beneficiaria puede ser de 10 dígitos (B2B HSBC) o 18 dígitos (CLABE SPEI).
"""

# Namespace XML ISO 20022 — igual para todos los tipos
XML_NAMESPACE     = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"
XML_NAMESPACE_XSI = "http://www.w3.org/2001/XMLSchema-instance"

# Método de pago
PMT_MTD = "TRF"

# Nivel de servicio: NURG = no urgente (Servicios / proveedores)
SVC_LVL_CODE = "NURG"

# Moneda de operación (Servicios en pesos MXN)
CURRENCY = "MXN"

# País de operación
COUNTRY = "MX"

# BIC por defecto HSBC México
BIC_DEFAULT = "BIMEMXMM"

# Longitudes válidas de cuenta beneficiaria
CUENTA_B2B_LENGTH  = 10   # Cuenta HSBC interna (B2B)
CUENTA_CLABE_LENGTH = 18  # CLABE interbancaria (SPEI)
