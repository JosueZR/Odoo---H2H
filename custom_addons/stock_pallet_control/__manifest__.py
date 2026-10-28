# -*- coding: utf-8 -*-
{
    'name': 'Control de tarimas: etiquetas, escaneo y ubicaciones',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Registra cada tarima como paquete con etiqueta de código de barras, '
               'entrada y salida por escaneo, propietario y mapa de ubicaciones libres/ocupadas.',
    'description': """
Control de tarimas sobre Inventario (Odoo 18 Community)
=======================================================

* Cada tarima es un paquete de Odoo; la etiqueta solo lleva el código del paquete.
* Recepción de tarimas: crea el paquete, la recepción validada, asigna ubicación libre
  automáticamente (reglas de ubicación + categoría de almacenamiento) e imprime la etiqueta 4x6.
* Escáner de tarimas: salida y cambio de ubicación escaneando la misma etiqueta.
* Propietario del inventario (mercancía de otras compañías).
* Mapa de ubicaciones: libres / ocupadas, con la tarima y su propietario.
* Generador de ubicaciones con código de barras para imprimir las etiquetas de rack.
""",
    'author': 'Equipo H2H',
    'license': 'LGPL-3',
    'depends': ['stock', 'barcodes'],
    'data': [
        'security/pallet_security.xml',
        'security/ir.model.access.csv',
        'data/pallet_data.xml',
        'report/pallet_label_report.xml',
        'wizard/pallet_receive_views.xml',
        'wizard/pallet_scan_views.xml',
        'wizard/location_generator_views.xml',
        'views/stock_location_views.xml',
        'views/stock_quant_package_views.xml',
        'views/pallet_menus.xml',
    ],
    'installable': True,
    'application': False,
}
