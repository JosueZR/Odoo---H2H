# -*- coding: utf-8 -*-
"""
Datos de prueba para HSBC H2H (SOLO BASES LOCALES / DE PRUEBAS).

Crea, sin duplicar si se vuelve a ejecutar:
  - Monedas MXN y EUR activas, con tipo de cambio si no tienen.
  - Bancos (res.bank) con su BIC.
  - Dos diarios bancarios con H2H habilitado:
        HSBC MXN (Pruebas H2H)  -> SPEI, Servicios, Nómina
        HSBC USD (Pruebas H2H)  -> SPID, OPI (USD / EUR)
  - Proveedores con cuenta bancaria válida para cada tipo de pago.
  - Empleados (contactos) con cuenta HSBC de nómina.
  - Una factura de proveedor publicada (sin pagar) por cada tipo de pago.
  - Un pago de nómina en borrador con la tabla de empleados lista.

Al final hace una verificación en seco: registra el pago de cada factura,
selecciona el método y genera el XML; después deshace todo (rollback).

Uso, desde la raíz del repo y con la base de pruebas. En Windows hay que indicar
UTF-8; si no, Python lee el script en cp1252 y los acentos se guardan mal:

    PowerShell:  $env:PYTHONIOENCODING = "utf-8"
    Git Bash:    export PYTHONIOENCODING=utf-8

    venv/Scripts/python.exe odoo-bin shell -c odoo.conf -d odoo18 --no-http < scripts/h2h_datos_prueba.py

Los importes son simbólicos (centavos / pocos pesos) para no mover dinero real
si un archivo llega a procesarse en el ambiente de pruebas de HSBC.
"""
import datetime
import unicodedata

PREFIJO = "[PRUEBA H2H]"
FECHA = datetime.date.today()

ID_CLIENTE_HSBC = "PC000032364"   # Mismo valor de ejemplo que usa el módulo
CUENTA_MXN = "4043001353"         # Cuenta ordenante MXN (10 dígitos)
CUENTA_USD = "7000123456"         # SPID exige 10 dígitos que inicien con 70
CUENTA_NOMINA = "4043001353"      # Cuenta HSBC de dispersión de nómina

assert "prod" not in env.cr.dbname.lower(), "No ejecutar en una base productiva."  # noqa: F821
assert len("é") == 1, (
    "El script se leyó con una codificación distinta de UTF-8 y los acentos se guardarían mal. "
    "Define PYTHONIOENCODING=utf-8 antes de ejecutarlo."
)
env = env(context=dict(env.context, tracking_disable=True))  # noqa: F821
company = env.company


def clabe(prefijo17):
    """Agrega el dígito verificador a 17 dígitos (banco 3 + plaza 3 + cuenta 11)."""
    assert len(prefijo17) == 17 and prefijo17.isdigit()
    pesos = [3, 7, 1] * 6
    suma = sum((int(d) * pesos[i]) % 10 for i, d in enumerate(prefijo17))
    return prefijo17 + str((10 - suma % 10) % 10)


def sin_acentos(texto):
    return unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")


def obtener(modelo, dominio, valores):
    rec = env[modelo].with_context(active_test=False).search(dominio, limit=1)
    if rec:
        return rec, False
    return env[modelo].create(valores), True


# ── Monedas ──────────────────────────────────────────────────────────────────
def moneda(codigo, tasa):
    cur = env["res.currency"].with_context(active_test=False).search([("name", "=", codigo)], limit=1)
    if not cur.active:
        cur.active = True
    if cur != company.currency_id and not cur.rate_ids.filtered(lambda r: r.company_id == company):
        env["res.currency.rate"].create({
            "currency_id": cur.id, "company_id": company.id,
            "name": FECHA.replace(month=1, day=1), "rate": tasa,
        })
    return cur


mxn = moneda("MXN", 18.50)
eur = moneda("EUR", 0.92)
usd = env.ref("base.USD")
pais = {c: env["res.country"].search([("code", "=", c)], limit=1) for c in ("MX", "US", "BE")}

# ── Bancos ───────────────────────────────────────────────────────────────────
BANCOS = {
    "HSBC":     ("HSBC México", "BIMEMXMM", "MX"),
    "BBVA":     ("BBVA México", "BCMRMXMM", "MX"),
    "BANORTE":  ("Banorte", "MENOMXMT", "MX"),
    "SANTANDER": ("Santander México", "BMSXMXMM", "MX"),
    "BOFA":     ("Bank of America", "BOFAUS3N", "US"),
    "BNP":      ("BNP Paribas Fortis", "GEBABEBB", "BE"),
}
banco = {}
for clave, (nombre, bic, pais_banco) in BANCOS.items():
    banco[clave], _ = obtener("res.bank", [("bic", "=", bic)],
                             {"name": nombre, "bic": bic, "country": pais[pais_banco].id})


# ── Diarios HSBC H2H ─────────────────────────────────────────────────────────
def diario(nombre, codigo, cuenta, moneda_diario):
    jrnl = env["account.journal"].search([("code", "=", codigo), ("company_id", "=", company.id)], limit=1)
    if not jrnl:
        jrnl = env["account.journal"].create({
            "name": nombre, "type": "bank", "code": codigo,
            "currency_id": moneda_diario.id if moneda_diario else False,
            "bank_acc_number": cuenta, "bank_id": banco["HSBC"].id,
        })
    jrnl.write({
        "is_h2h_enabled": True, "hsbc_client_id": ID_CLIENTE_HSBC,
        "hsbc_bic": "BIMEMXMM", "hsbc_nomina_account": CUENTA_NOMINA,
    })
    return jrnl


diario_mxn = diario("HSBC MXN (Pruebas H2H)", "HMXN", CUENTA_MXN, mxn if company.currency_id != mxn else None)
diario_usd = diario("HSBC USD (Pruebas H2H)", "HUSD", CUENTA_USD, usd if company.currency_id != usd else None)


# ── Proveedores y empleados ──────────────────────────────────────────────────
def contacto(nombre, cuenta, banco_rec, pais_code, es_empleado=False, **extra):
    nombre_completo = nombre if es_empleado else f"{nombre}"
    partner, _ = obtener("res.partner", [("name", "=", nombre_completo), ("comment", "ilike", PREFIJO)], {
        "name": nombre_completo, "is_company": not es_empleado,
        "country_id": pais[pais_code].id, "comment": f"{PREFIJO} contacto de prueba",
        "supplier_rank": 0 if es_empleado else 1, **extra,
    })
    numero = cuenta.replace(" ", "")
    cuenta_rec = partner.bank_ids.filtered(lambda b: b.acc_number.replace(" ", "") == numero)
    if not cuenta_rec:
        cuenta_rec = env["res.partner.bank"].create({
            "partner_id": partner.id, "acc_number": cuenta, "bank_id": banco_rec.id,
        })
    try:
        cuenta_rec.allow_out_payment = True
    except Exception:
        pass
    return partner, cuenta_rec


direccion_mx = {"street": "Blvd. Antonio Rosales 123", "zip": "81200", "city": "Los Mochis"}

PROVEEDORES = [
    # (código método, nombre, cuenta, banco, país, moneda, importe, extra)
    ("SPEI", "Papelería del Pacífico SA de CV", clabe("01218000123456789"), "BBVA", "MX", mxn, 1.00,
     dict(direccion_mx)),
    ("SPID", "Importadora del Norte SA de CV", clabe("07218000987654321"), "BANORTE", "MX", usd, 0.50,
     dict(direccion_mx, vat="INO010101AB1")),
    ("SERVICIOS", "Mantenimiento Industrial del Valle SA de CV", "4051234567", "HSBC", "MX", mxn, 1.50,
     dict(direccion_mx)),
    ("SERVICIOS", "Servicios de Energía del Golfo SA de CV", clabe("01418000555444333"), "SANTANDER", "MX",
     mxn, 2.00, dict(direccion_mx)),
    ("OPI", "ABC Supplies Inc", "0011223344", "BOFA", "US", usd, 0.50,
     {"street": "100 Montgomery St", "zip": "94108", "city": "San Francisco"}),
    ("OPI", "GHI Semiconductors SA", "BE30 0012 1637 1411", "BNP", "BE", eur, 1.00,
     {"street": "Avenue Brugmann 415", "zip": "1050", "city": "Brussels"}),
]

EMPLEADOS = [
    ("Juan Pérez López", "4060000011", 1.00),
    ("María García Hernández", "4060000022", 1.50),
    ("Luis Ramírez Soto", "4060000033", 2.00),
]


def factura(partner, cuenta_rec, moneda_fact, importe, metodo):
    ref = f"{PREFIJO} {metodo} {partner.name}"
    bill = env["account.move"].search([("ref", "=", ref), ("move_type", "=", "in_invoice")], limit=1)
    if bill:
        return bill, False
    bill = env["account.move"].create({
        "move_type": "in_invoice", "partner_id": partner.id, "ref": ref,
        "invoice_date": FECHA, "currency_id": moneda_fact.id, "partner_bank_id": cuenta_rec.id,
        "invoice_line_ids": [(0, 0, {
            "name": f"Prueba de pago H2H {metodo}", "quantity": 1,
            "price_unit": importe, "tax_ids": [(6, 0, [])],
        })],
    })
    bill.action_post()
    return bill, True


facturas = []
for metodo, nombre, cuenta, banco_clave, pais_code, moneda_fact, importe, extra in PROVEEDORES:
    partner, cuenta_rec = contacto(nombre, cuenta, banco[banco_clave], pais_code, **extra)
    bill, nueva = factura(partner, cuenta_rec, moneda_fact, importe, metodo)
    jrnl = diario_mxn if moneda_fact == mxn else diario_usd
    facturas.append((metodo, bill, jrnl))
    print(f"{'Creada ' if nueva else 'Existe '} {bill.name:<20} {metodo:<10} {moneda_fact.name} "
          f"{importe:>6.2f}  {partner.name}  -> pagar con {jrnl.name}")

# ── Pago de nómina en borrador ───────────────────────────────────────────────
empleados = [contacto(n, c, banco["HSBC"], "MX", es_empleado=True, **direccion_mx) + (imp,)
             for n, c, imp in EMPLEADOS]
ref_nomina = f"{PREFIJO} Nómina quincena"
pago_nomina = env["account.payment"].search([("memo", "=", ref_nomina)], limit=1)
if not pago_nomina:
    pago_nomina = env["account.payment"].create({
        "payment_type": "outbound", "partner_type": "supplier",
        "partner_id": empleados[0][0].id, "journal_id": diario_mxn.id,
        "currency_id": mxn.id, "amount": sum(e[2] for e in empleados),
        "date": FECHA, "memo": ref_nomina,
    })
    pago_nomina._select_h2h_method_by_code("NOMINA")
    pago_nomina.write({"h2h_nomina_line_ids": [
        (0, 0, {"partner_id": p.id, "partner_bank_id": b.id, "amount": imp,
                "referencia_empleado": f"NOMINA {sin_acentos(p.name.split()[0]).upper()}"})
        for p, b, imp in empleados
    ]})
    print(f"Creado  {pago_nomina.name or 'pago borrador':<20} NOMINA     MXN  {pago_nomina.amount:>6.2f}  "
          f"{len(empleados)} empleados -> {diario_mxn.name}")
else:
    print(f"Existe  pago de nómina (id {pago_nomina.id})")

env.cr.commit()
print("\nDatos de prueba guardados.\n")

# ── Verificación en seco: generar el XML de cada tipo y deshacer ─────────────
print("Verificación (se deshace al terminar):")


class _Rollback(Exception):
    pass


resultados = []
try:
    with env.cr.savepoint():
        for metodo, bill, jrnl in facturas:
            try:
                with env.cr.savepoint():
                    ctx = {"active_model": "account.move", "active_ids": bill.ids}
                    wiz = env["account.payment.register"].with_context(**ctx).create({"journal_id": jrnl.id})
                    pago = wiz._create_payments()
                    pago._select_h2h_method_by_code(metodo)
                    pago.action_h2h_generate_xml()
                    ok = bool(pago.h2h_xml_attachment_id)
                    resultados.append((metodo, bill.partner_id.name, "OK" if ok else "sin XML",
                                       f"factura: {bill.payment_state}"))
            except Exception as e:  # noqa: BLE001
                resultados.append((metodo, bill.partner_id.name, "ERROR", str(e).replace("\n", " ")[:300]))
        try:
            with env.cr.savepoint():
                pago_nomina.action_h2h_generate_xml()
                resultados.append(("NOMINA", f"{len(empleados)} empleados",
                                   "OK" if pago_nomina.h2h_xml_attachment_id else "sin XML", ""))
        except Exception as e:  # noqa: BLE001
            resultados.append(("NOMINA", "pago borrador", "ERROR", str(e).replace("\n", " ")[:300]))
        raise _Rollback()
except _Rollback:
    pass
env.invalidate_all()

for metodo, quien, estado, detalle in resultados:
    print(f"  {estado:<6} {metodo:<10} {quien:<45} {detalle}")
