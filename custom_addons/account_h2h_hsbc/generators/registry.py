# -*- coding: utf-8 -*-
"""
Registro central de generadores H2H.

Para agregar un nuevo método de pago (ej. SPID):
  1. Crear xml_spid/spid_generator.py con class SpidGenerator(BaseH2HGenerator)
  2. Importar aquí y registrar: REGISTRY["SPID"] = SpidGenerator()
  3. Habilitar el método en h2h.payment.method (is_available = True)

Nada más cambia.
"""
from odoo.exceptions import UserError
from ..xml_spei.spei_generator import SpeiGenerator

# ── Registro de generadores activos ───────────────────────────────────────────
# clave  = h2h.payment.method.code (debe coincidir exactamente)
# valor  = instancia del generador correspondiente
REGISTRY = {
    "SPEI": SpeiGenerator(),
    # "SPID": SpidGenerator(),   ← descomentar cuando SPID esté implementado
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
