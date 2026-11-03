# -*- coding: utf-8 -*-
from odoo import _, fields, models
from odoo.exceptions import UserError


class StockPickingPallet(models.Model):
    _inherit = 'stock.picking'

    use_pallet = fields.Boolean(
        string='Manejar por tarima',
        default=False,
        help='Activa esta opción cuando la recepción se gestiona por tarimas.',
    )
    pallet_qty = fields.Integer(
        string='Cantidad de tarimas',
        default=0,
        help='Número de tarimas asociadas a esta recepción.',
    )

    def action_print_pallet_labels(self):
        """Imprime las etiquetas de tarima de todos los paquetes de esta recepción."""
        self.ensure_one()
        # Buscar paquetes en las líneas de movimiento (resultado)
        packages = self.move_line_ids.result_package_id
        # También revisar package_level_ids (paquetes a nivel de operación)
        if not packages:
            packages = self.package_level_ids.package_id
        # Como último recurso, buscar paquetes via quants de los moves
        if not packages:
            packages = self.move_line_ids.package_id
        if not packages:
            raise UserError(_(
                'Esta recepcion no tiene tarimas (paquetes) registrados.\n\n'
                'Para crear etiquetas de tarima tienes dos opciones:\n'
                '1. Usa el wizard "Recibir tarimas" desde el Centro de Operaciones '
                '(este crea los paquetes automaticamente).\n'
                '2. En esta recepcion, ve a "Operaciones detalladas" y asigna '
                'un paquete de destino a cada linea antes de validar.'
            ))
        return self.env.ref(
            'stock_pallet_control.action_report_pallet_label'
        ).report_action(packages)
