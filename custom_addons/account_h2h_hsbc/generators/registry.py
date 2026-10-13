# -*- coding: utf-8 -*-
"""
Registro central de generadores H2H.

Para agregar un nuevo método de pago:
  1. Crear xml_{metodo}/{metodo}_generator.py con class XxxGenerator(BaseH2HGenerator)
  2. Importar aquí y registrar: REGISTRY[\"XXX\"] = XxxGenerator()
  3. Habilitar el método en h2h.payment.method (is_available = True)
  4. Actualizar data/h2h_method_data.xml si es necesario

Métodos actualmente implementados:
  - SPEI      — Transferencia nacional en MXN (SvcLvl URGP, CLABE 18 dígitos)
  - SPID      — Transferencia USD (SvcLvl URGP, RFC obligatorio, código operación)
  - NOMINA    — Dispersión de nómina HSBC (SvcLvl NURG, CtgyPurp SALA, 10 dígitos)
  - SERVICIOS — Pago a proveedores MXN (SvcLvl NURG, B2B 10 o CLABE 18 dígitos)
"""
from odoo.exceptions import UserError
from ..xml_spei.spei_generator import SpeiGenerator
from ..xml_spid.spid_generator import SpidGenerator
from ..xml_nomina.nomina_generator import NominaGenerator
from ..xml_servicios.servicios_generator import ServiciosGenerator

# ── Registro de generadores activos ───────────────────────────────────────────
# clave  = h2h.payment.method.code (debe coincidir exactamente)
# valor  = instancia del generador correspondiente
REGISTRY = {
    "SPEI":      SpeiGenerator(),
    "SPID":      SpidGenerator(),
    "NOMINA":    NominaGenerator(),
    "SERVICIOS": ServiciosGenerator(),
}


def get_generator(method_code: str):
    """
    Devuelve el generador registrado para el código dado.
    Lanza UserError si el método no está registrado.
    """
    generator = REGISTRY.get(method_code)
    if not generator:
        raise UserError(
            f"No existe un generador implementado para el método '{method_code}'. "
            f"Métodos disponibles: {', '.join(REGISTRY.keys())}."
        )
    return generator
