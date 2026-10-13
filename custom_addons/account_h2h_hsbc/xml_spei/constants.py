# -*- coding: utf-8 -*-
"""
Constantes específicas del estándar SPEI / pain.001.001.03 para HSBC México.
"""

# Namespace XML ISO 20022
XML_NAMESPACE = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"
XML_NAMESPACE_XSI = "http://www.w3.org/2001/XMLSchema-instance"

# Nivel de servicio SPEI (urgente)
SVC_LVL_CODE = "URGP"

# Método de pago (transferencia de crédito)
PMT_MTD = "TRF"

# Moneda SPEI
CURRENCY = "MXN"

# País de operación
COUNTRY = "MX"

# BIC por defecto HSBC México (se sobreescribe con el valor del diario)
BIC_DEFAULT = "BIMEMXMM"

# Longitud de una CLABE interbancaria
CLABE_LENGTH = 18
