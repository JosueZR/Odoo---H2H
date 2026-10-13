# -*- coding: utf-8 -*-
"""
Constantes específicas para pagos de Nómina HSBC (ACH interno HSBC).
Los pagos de nómina HSBC se dispersan a cuentas internas de 10 dígitos
y utilizan el código de propósito SALA (salarios).
"""

# Namespace XML ISO 20022 — igual para todos los tipos
XML_NAMESPACE     = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"
XML_NAMESPACE_XSI = "http://www.w3.org/2001/XMLSchema-instance"

# Método de pago
PMT_MTD = "TRF"

# Nivel de servicio: NURG = no urgente (Nómina ACH)
SVC_LVL_CODE = "NURG"

# Propósito de categoría: SALA = pago de salarios
CTGY_PURP_CODE = "SALA"

# Moneda de operación (Nómina en pesos MXN)
CURRENCY = "MXN"

# País de operación
COUNTRY = "MX"

# BIC por defecto HSBC México
BIC_DEFAULT = "BIMEMXMM"

# Código de banco HSBC México (solo se permiten cuentas HSBC para nómina)
BANCO_HSBC = "021"

# Longitud de la cuenta HSBC de nómina (10 dígitos internos)
CUENTA_NOMINA_LENGTH = 10

# El InstrId y EndToEndId de nómina DEBEN contener esta palabra (requerido por HSBC)
NOMINA_KEYWORD = "NOMINA"
