# -*- coding: utf-8 -*-
from odoo import _, api, models
from odoo.exceptions import UserError


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    @api.model
    def _pallet_setup_operation_types(self):
        """Activa "Mover paquetes completos" en Entregas y operaciones internas (Recolectar,
        Traslados internos...) de todos los almacenes, activos o no.

        Así se saca o mueve la tarima entera (sección Paquete o escaneo) en vez de capturar
        producto por producto. No activa ni desactiva tipos de operación.
        """
        self.with_context(active_test=False).search([
            ('code', 'in', ('outgoing', 'internal')),
            ('show_entire_packs', '=', False),
        ]).write({'show_entire_packs': True})


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    def action_open_pallet_split(self):
        """Recepción: abrir el asistente para repartir lo recibido en tarimas."""
        self.ensure_one()
        if self.picking_type_code != 'incoming':
            raise UserError(_('Separar en tarimas solo aplica a recepciones.'))
        if self.state != 'assigned':
            raise UserError(_('La recepción debe estar en estado "Listo" para separarla en tarimas.'))
        return {
            'type': 'ir.actions.act_window',
            'name': _('Separar en tarimas'),
            'res_model': 'stock.pallet.split',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_picking_id': self.id},
        }

    def action_print_pallet_labels(self):
        """Imprime la etiqueta 4x6 de cada tarima (paquete) de esta recepción."""
        self.ensure_one()
        packages = self.move_line_ids.result_package_id or self.package_level_ids.package_id
        if not packages:
            raise UserError(_(
                'Esta recepción no tiene tarimas (paquetes).\n\n'
                'Antes de validar usa "Separar en tarimas", o "Poner en paquete" en cada tarima.'))
        # config=False: la etiqueta no usa el encabezado de la compañía; no pedir "diseño de documento".
        return self.env.ref('stock_pallet_control.action_report_pallet_label').report_action(
            packages, config=False)
