{
    "name": "Integración H2H HSBC Contabilidad",
    "version": "18.0.3.0.0",
    "category": "Accounting/Localizations",
    "summary": (
        "Generación y validación de archivos XML ISO 20022 (pain.001) "
        "para pagos Host to Host con HSBC directamente desde Contabilidad. "
        "Soporta SPEI, SPID, Nómina HSBC y Servicios con validación estructural."
    ),
    "depends": ["account"],
    "data": [
        "security/ir.model.access.csv",
        "data/h2h_method_data.xml",
        "views/account_journal_views.xml",
        "views/h2h_payment_views.xml",
    ],
    "installable": True,
    "application": True,
    "license": "LGPL-3",
}
