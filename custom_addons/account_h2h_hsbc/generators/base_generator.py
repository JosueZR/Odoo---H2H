# -*- coding: utf-8 -*-
"""
Clase base abstracta para todos los generadores H2H.
Cada método de pago (SPEI, SPID, …) hereda esta clase e implementa
validate() y generate().
"""
from odoo.exceptions import UserError


class BaseH2HGenerator:
    """
    Interfaz que deben implementar todos los generadores H2H.

    Uso:
        class SpeiGenerator(BaseH2HGenerator):
            METHOD_CODE = "SPEI"

            def validate(self, payment): ...
            def generate(self, payment) -> bytes: ...
    """

    # Código del método: "SPEI", "SPID", etc.
    # Debe coincidir con h2h.payment.method.code en la base de datos.
    METHOD_CODE: str = None

    def validate(self, payment) -> None:
        """
        Valida que el pago tenga todos los datos necesarios para este método.
        Debe lanzar UserError si algo falta o es incorrecto.
        """
        raise NotImplementedError(
            f"El generador {self.__class__.__name__} debe implementar validate()."
        )

    def generate(self, payment) -> bytes:
        """
        Genera el XML del pago y lo devuelve como bytes (UTF-8).
        Llama internamente a validate() antes de generar.
        """
        raise NotImplementedError(
            f"El generador {self.__class__.__name__} debe implementar generate()."
        )

    # ── Utilidades comunes disponibles para todos los generadores ─────────────

    @staticmethod
    def _get_safe_name(payment) -> str:
        """Devuelve un nombre seguro para usar en IDs y nombres de archivo."""
        name = payment.name if payment.name and payment.name != "/" else f"Draft_{payment.id}"
        return name.replace("/", "_")

    @staticmethod
    def _require_field(value, field_label: str) -> None:
        """Lanza UserError si value es falsy."""
        if not value:
            raise UserError(f"Falta el campo requerido: {field_label}.")
