# -*- coding: utf-8 -*-
{
    'name': 'Control de tarimas: etiquetas',
    'version': '18.0.3.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Separa la recepción en tarimas (paquetes) e imprime una etiqueta 4x6 por tarima.',
    'description': """
Control de tarimas sobre Inventario (Odoo 18)
=============================================

Se trabaja con los documentos estándar de Inventario; el módulo solo agrega:

* En la Recepción (la que genera la orden de compra): botón "Separar en tarimas".
  Indicas cuánto lleva cada tarima y Odoo crea un paquete por tarima (tipo "Tarima").
* Botón "Imprimir etiquetas de tarima": etiqueta 4x6 con código de barras del paquete.
* "Mover paquetes completos" en Entregas y operaciones internas de todos los almacenes,
  para sacar o mover la tarima entera (también escaneándola en la app Código de barras).
""",
    'author': 'Equipo H2H',
    'license': 'LGPL-3',
    'depends': ['stock'],
    'data': [
        'security/pallet_security.xml',
        'security/ir.model.access.csv',
        'data/pallet_data.xml',
        'report/pallet_label_report.xml',
        'wizard/pallet_split_views.xml',
        'views/stock_quant_package_views.xml',
        'views/stock_picking_pallet_views.xml',
    ],
    'installable': True,
    'application': False,
}
