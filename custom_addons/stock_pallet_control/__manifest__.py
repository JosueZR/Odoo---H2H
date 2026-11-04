# -*- coding: utf-8 -*-
{
    'name': 'Control de tarimas: etiquetas',
    'version': '18.0.3.1.0',
    'category': 'Inventory/Inventory',
    'summary': 'Tarimas de mercancía de clientes (con propietario, valor $0): etiqueta 4x6 y conciliación.',
    'description': """
Control de tarimas sobre Inventario (Odoo 18)
=============================================

Mercancía de clientes que se guarda o controla (no es compra ni venta). Se registra con
Propietario (consigna nativa de Odoo): se ve en el almacén pero no suma al valor del inventario.

* Recepción: botón "Separar en tarimas" (pide el propietario); un paquete tipo "Tarima" por tarima.
* Botón "Imprimir etiquetas de tarima": etiqueta 4x6 con código de barras del paquete.
* Inventario > Reportes > Conciliación por propietario, para comparar contra el reporte de la bodega.
* Una entrega sin tarima ni propietario (p. ej. de una venta) no aparta mercancía de clientes.
* "Mover paquetes completos" en Entregas e internas de todos los almacenes.
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
        'views/pallet_reconciliation_views.xml',
    ],
    'installable': True,
    'application': False,
}
