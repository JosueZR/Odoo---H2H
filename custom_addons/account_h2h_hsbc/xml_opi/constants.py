# -*- coding: utf-8 -*-
"""
Constantes específicas para pagos OPI (Orden de Pago Internacional / Cross Border).
Usa el mismo estándar pain.001.001.03 que el resto de métodos.

Diferencias clave contra los pagos nacionales (SPEI/SPID/Servicios/Nómina):
- El banco beneficiario se identifica con BIC (SWIFT), no con ClrSysMmbId de 3 dígitos.
- La cuenta beneficiaria es IBAN (países que lo usan) o número de cuenta normal (Othr/Id).
- Existe ChrgBr (quién paga las comisiones): DEBT, CRED o SHAR.
- El propósito de pago usa códigos ISO globales (Purp/Cd), no los locales mexicanos.
- La moneda puede variar (USD, EUR, GBP, ...) pero NO puede ser MXN.
- Se exige el reporte regulatorio RgltryRptg con formato /BENEFRES/MX//XX (XX = 01..22).
- Se solicita el código postal del beneficiario (HSBC, 09/2026).
"""

# Namespace XML ISO 20022 — igual para todos los tipos
XML_NAMESPACE     = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"
XML_NAMESPACE_XSI = "http://www.w3.org/2001/XMLSchema-instance"

# Método de pago
PMT_MTD = "TRF"

# Nivel de servicio: URGP (prioritario, igual que el ejemplo oficial HSBC Cross Border)
SVC_LVL_CODE = "URGP"

# País del ordenante (la empresa está domiciliada en México)
COUNTRY = "MX"

# BIC por defecto HSBC México
BIC_DEFAULT = "BIMEMXMM"

# OPI no opera en MXN
CURRENCY_EXCLUIDA = "MXN"

# Longitudes máximas (ISO 20022: Max70Text / Max140Text)
NOMBRE_MAX_LENGTH       = 70
DIRECCION_MAX_LENGTH    = 70
USTRD_MAX_LENGTH        = 140
END_TO_END_MAX_LENGTH   = 35   # Max35Text

# Quién paga las comisiones (ChrgBr)
CHRGBR_OPCIONES = {
    "DEBT": "Las paga el ordenante",
    "CRED": "Las paga el beneficiario",
    "SHAR": "Compartidas (comisión al ordenante y al beneficiario)",
}

# Códigos de propósito global ISO 20022 (Purp/Cd) más comunes
PURP_CODES = {
    "CINV": "Pago de factura comercial",
    "GDDS": "Pago de bienes",
    "INTC": "Transferencia entre cuentas propias (intra-company)",
    "SUPP": "Pago a proveedor",
    "SALA": "Pago de nómina",
    "TAXS": "Pago de impuestos",
}

# Catálogo "Propósito del Pago" para RgltryRptg (formato /BENEFRES/MX//XX)
CODIGOS_REGULATORIOS_OPI = {
    "01": "Pago a proveedores",
    "02": "Pago de impuestos",
    "03": "Envío de pago a casa matriz",
    "04": "Pago a filiales o subsidiarias",
    "05": "Pago de créditos",
    "06": "Pago de seguros",
    "07": "Pago Fideicomisos",
    "08": "Pago de servicios",
    "09": "Pago a tarjeta de crédito",
    "10": "Pago a tarjeta de débito",
    "11": "Pago de nómina",
    "12": "Pago de inversiones",
    "13": "Pago otras operaciones",
    "14": "Pago a proveedores locales",
    "15": "Pago a clientes locales",
    "16": "Pago de proveedores fronterizos",
    "17": "Pago a clientes fronterizos",
    "18": "Inversión",
    "19": "Pago de bienes",
    "20": "Otorgamiento de préstamo",
    "21": "Pago de préstamo",
    "22": "Otros",
}

# Prefijo del reporte regulatorio. Formato final: "/BENEFRES/MX//{codigo}"
RGLTRY_PREFIJO = "/BENEFRES/MX//"

# Orden de RgltryRptg respecto a Purp dentro de CdtTrfTxInf.
# El generador original validado con HSBC (09/2026) coloca RgltryRptg ANTES de Purp.
# (El XSD estándar de pain.001.001.03 los define en el orden inverso: Purp -> RgltryRptg.)
# Si HSBC rechaza el archivo por orden de elementos, cambiar a False.
RGLTRY_ANTES_DE_PURP = True
