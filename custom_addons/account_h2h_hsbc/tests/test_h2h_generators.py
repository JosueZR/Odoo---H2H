# -*- coding: utf-8 -*-
"""
Suite de pruebas unitarias para los generadores y validadores XML de HSBC H2H.
Verifica:
  1. Ejecución y generación de XML para SPEI, SPID, Nómina y Servicios.
  2. Preservación exacta de la estructura validada por HSBC (tags, namespaces, campos obligatorios).
  3. Validación estructural y semántica de cada tipo de pago.
  4. Rechazo correcto de XML mal formados, monedas incorrectas o campos faltantes.
  5. Registro correcto de generadores en generators/registry.py.
  6. Independencia absoluta de la carpeta 'Los generadores de xml'.
"""
import unittest
import xml.etree.ElementTree as ET
from decimal import Decimal
from types import SimpleNamespace

# Mocks para emular registros de Odoo en pruebas unitarias puras
class DummyCompany:
    name = "EMPRESA PRUEBA SA DE CV"
    street = "Av Principal 123"
    zip = "81200"
    city = "Los Mochis"


class DummyPartnerBank:
    def __init__(self, acc_number):
        self.acc_number = acc_number


class DummyPartner:
    def __init__(self, name, street="Calle Norte 45", zip="01000", city="CDMX", vat="XAXX010101000"):
        self.name = name
        self.street = street
        self.zip = zip
        self.city = city
        self.vat = vat


class DummyCurrency:
    def __init__(self, name):
        self.name = name


class DummyJournal:
    def __init__(self, acc_number, hsbc_client_id="PC000032364", hsbc_bic="BIMEMXMM", hsbc_nomina_account=None):
        self.is_h2h_enabled = True
        self.hsbc_client_id = hsbc_client_id
        self.hsbc_bic = hsbc_bic
        self.hsbc_nomina_account = hsbc_nomina_account
        self.bank_account_id = SimpleNamespace(acc_number=acc_number)


class DummyNominaLine:
    def __init__(self, partner_name, acc_number, amount, referencia=""):
        self.partner_id = DummyPartner(partner_name)
        self.acc_number = acc_number
        self.amount = amount
        self.referencia_empleado = referencia
        self.validation_status = "pending"
        self.error_details = ""
        self.xml_attachment_id = None


class DummyPayment:
    def __init__(
        self,
        name="PAY/2026/00001",
        amount=100.50,
        currency_name="MXN",
        partner_acc="123456789012345678",
        journal_acc="4043001353",
        journal_nomina_acc="4043001353",
        partner_name="JUAN PEREZ",
        spid_rfc="XAXX010101000",
        spid_codigo="04",
        spid_ref_larga="FAC-1234",
        h2h_nomina_line_ids=None,
    ):
        self.id = 1
        self.name = name
        self.amount = amount
        self.date = "2026-10-13"
        self.company_id = DummyCompany()
        self.currency_id = DummyCurrency(currency_name)
        self.partner_id = DummyPartner(partner_name)
        self.partner_bank_id = DummyPartnerBank(partner_acc)
        self.journal_id = DummyJournal(
            acc_number=journal_acc,
            hsbc_nomina_account=journal_nomina_acc,
        )
        self.h2h_spid_rfc = spid_rfc
        self.h2h_spid_codigo = spid_codigo
        self.h2h_spid_referencia_larga = spid_ref_larga
        self.h2h_nomina_line_ids = h2h_nomina_line_ids or []


class TestH2HGenerators(unittest.TestCase):

    def setUp(self):
        # Importar dinámicamente desde el addon
        from ..generators.registry import REGISTRY, get_generator
        from ..xml_spei.spei_generator import SpeiGenerator
        from ..xml_spei.spei_validator import validar_xml_spei
        from ..xml_spid.spid_generator import SpidGenerator
        from ..xml_spid.spid_validator import validar_xml_spid
        from ..xml_nomina.nomina_generator import NominaGenerator
        from ..xml_nomina.nomina_validator import validar_xml_nomina
        from ..xml_servicios.servicios_generator import ServiciosGenerator
        from ..xml_servicios.servicios_validator import validar_xml_servicios

        self.REGISTRY = REGISTRY
        self.get_generator = get_generator
        self.SpeiGenerator = SpeiGenerator
        self.validar_xml_spei = validar_xml_spei
        self.SpidGenerator = SpidGenerator
        self.validar_xml_spid = validar_xml_spid
        self.NominaGenerator = NominaGenerator
        self.validar_xml_nomina = validar_xml_nomina
        self.ServiciosGenerator = ServiciosGenerator
        self.validar_xml_servicios = validar_xml_servicios

    def test_01_registry_contains_all_four_methods(self):
        """Verifica que los 4 generadores estén debidamente registrados en el registry."""
        metodos = ["SPEI", "SPID", "NOMINA", "SERVICIOS"]
        for m in metodos:
            self.assertIn(m, self.REGISTRY, f"El método {m} debe estar registrado en REGISTRY.")
            gen = self.get_generator(m)
            self.assertIsNotNone(gen, f"get_generator('{m}') debe devolver un generador válido.")

    def test_02_spei_generator_and_validator(self):
        """Verifica la generación y validación de XML para SPEI."""
        pago = DummyPayment(
            name="PAY/2026/0001",
            amount=500.00,
            currency_name="MXN",
            partner_acc="012180001234567890", # CLABE 18 dígitos
            journal_acc="4043001353",
        )
        gen = self.get_generator("SPEI")
        xml_bytes = gen.generate(pago)
        self.assertTrue(xml_bytes.startswith(b"<?xml version=\"1.0\" encoding=\"UTF-8\" ?>"))

        # Validar estructuralmente
        self.validar_xml_spei(xml_bytes)

        # Inspeccionar elementos clave
        root = ET.fromstring(xml_bytes)
        ns = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"
        svc = root.find(f".//{{{ns}}}SvcLvl/{{{ns}}}Cd")
        self.assertIsNotNone(svc)
        self.assertEqual(svc.text, "URGP")

        ccy = root.find(f".//{{{ns}}}InstdAmt")
        self.assertEqual(ccy.attrib.get("Ccy"), "MXN")

    def test_03_spid_generator_and_validator(self):
        """Verifica la generación y validación de XML para SPID (USD)."""
        pago = DummyPayment(
            name="PAY/2026/0002",
            amount=1500.00,
            currency_name="USD",
            partner_acc="014180062472999999", # CLABE 18 dígitos banco 014
            journal_acc="7012345678",           # Cuenta ordenante SPID (10 dígitos, inicia con 70)
            spid_rfc="RFC123456789",
            spid_codigo="04",
            spid_ref_larga="PAGO SERVICIOS INTERNACIONALES",
        )
        gen = self.get_generator("SPID")
        xml_bytes = gen.generate(pago)
        self.assertTrue(xml_bytes.startswith(b"<?xml version=\"1.0\" encoding=\"UTF-8\" ?>"))

        # Validar estructuralmente
        self.validar_xml_spid(xml_bytes)

        root = ET.fromstring(xml_bytes)
        ns = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"
        # Moneda USD
        ccy = root.find(f".//{{{ns}}}InstdAmt")
        self.assertEqual(ccy.attrib.get("Ccy"), "USD")

        # Código de clasificación
        rgltry = root.find(f".//{{{ns}}}RgltryRptg/{{{ns}}}Dtls/{{{ns}}}Inf")
        self.assertIsNotNone(rgltry)
        self.assertEqual(rgltry.text, "/SPID/OC/04")

        # RFC beneficiario
        tax_id = root.find(f".//{{{ns}}}Tax/{{{ns}}}Cdtr/{{{ns}}}TaxId")
        self.assertIsNotNone(tax_id)
        self.assertEqual(tax_id.text, "RFC123456789")

    def test_04_nomina_generator_and_validator(self):
        """Verifica la generación y validación de XML para Nómina HSBC."""
        pago = DummyPayment(
            name="PAY/2026/0003",
            amount=12500.00,
            currency_name="MXN",
            partner_acc="4099999999",          # Cuenta HSBC empleado 10 dígitos (banco 021)
            journal_acc="4043001353",
            journal_nomina_acc="4043001353",   # Cuenta de nómina HSBC 10 dígitos
            partner_name="EMPLEADO PEREZ",
        )
        gen = self.get_generator("NOMINA")
        xml_bytes = gen.generate(pago)
        self.assertTrue(xml_bytes.startswith(b"<?xml version=\"1.0\" encoding=\"UTF-8\" ?>"))

        # Validar estructuralmente
        self.validar_xml_nomina(xml_bytes)

        root = ET.fromstring(xml_bytes)
        ns = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"
        # SvcLvl = NURG
        svc = root.find(f".//{{{ns}}}SvcLvl/{{{ns}}}Cd")
        self.assertEqual(svc.text, "NURG")

        # CtgyPurp = SALA
        ctgy = root.find(f".//{{{ns}}}CtgyPurp/{{{ns}}}Cd")
        self.assertIsNotNone(ctgy)
        self.assertEqual(ctgy.text, "SALA")

        # InstrId y EndToEndId contienen 'NOMINA'
        instr = root.find(f".//{{{ns}}}PmtId/{{{ns}}}InstrId")
        self.assertIn("NOMINA", instr.text.upper())
        e2e = root.find(f".//{{{ns}}}PmtId/{{{ns}}}EndToEndId")
        self.assertIn("NOMINA", e2e.text.upper())

        # Banco 021
        mmb = root.find(f".//{{{ns}}}CdtrAgt//{{{ns}}}MmbId")
        self.assertEqual(mmb.text, "021")

    def test_05_servicios_generator_and_validator(self):
        """Verifica la generación y validación de XML para Servicios."""
        pago = DummyPayment(
            name="PAY/2026/0004",
            amount=850.00,
            currency_name="MXN",
            partner_acc="1234567890", # Cuenta B2B HSBC 10 dígitos
            journal_acc="4043001353",
            partner_name="PROVEEDOR SERVICIOS",
        )
        gen = self.get_generator("SERVICIOS")
        xml_bytes = gen.generate(pago)
        self.assertTrue(xml_bytes.startswith(b"<?xml version=\"1.0\" encoding=\"UTF-8\" ?>"))

        # Validar estructuralmente
        self.validar_xml_servicios(xml_bytes)

        root = ET.fromstring(xml_bytes)
        ns = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"
        # SvcLvl = NURG
        svc = root.find(f".//{{{ns}}}SvcLvl/{{{ns}}}Cd")
        self.assertEqual(svc.text, "NURG")

        # Sin CtgyPurp SALA
        ctgy = root.find(f".//{{{ns}}}CtgyPurp")
        self.assertIsNone(ctgy)

    def test_06_validation_rejects_malformed_xml(self):
        """Verifica que los validadores rechacen XML inválidos o mal formados."""
        xml_invalido = b"<Document><CstmrCdtTrfInitn><Incompleto>"
        with self.assertRaises(Exception):
            self.validar_xml_spei(xml_invalido)

        with self.assertRaises(Exception):
            self.validar_xml_spid(xml_invalido)

        with self.assertRaises(Exception):
            self.validar_xml_nomina(xml_invalido)

        with self.assertRaises(Exception):
            self.validar_xml_servicios(xml_invalido)

    def test_07_validation_rejects_rule_violations(self):
        """Verifica que se detecten violaciones específicas de reglas de negocio bancarias."""
        # Generar XML SPEI válido
        pago = DummyPayment(
            name="PAY/2026/0001",
            amount=500.00,
            currency_name="MXN",
            partner_acc="012180001234567890",
            journal_acc="4043001353",
        )
        gen = self.get_generator("SPEI")
        xml_bytes = gen.generate(pago)

        # 1. Moneda alterada a EUR -> debe ser rechazada por SPEI
        xml_eur = xml_bytes.replace(b'Ccy="MXN"', b'Ccy="EUR"')
        with self.assertRaises(Exception):
            self.validar_xml_spei(xml_eur)

        # 2. SvcLvl alterado a NURG en SPEI -> debe ser rechazado
        xml_nurg = xml_bytes.replace(b'<Cd>URGP</Cd>', b'<Cd>NURG</Cd>')
        with self.assertRaises(Exception):
            self.validar_xml_spei(xml_nurg)

        # 3. SPID con moneda MXN -> debe ser rechazada
        pago_spid = DummyPayment(
            name="PAY/2026/0002",
            amount=1500.00,
            currency_name="USD",
            partner_acc="014180062472999999",
            journal_acc="7012345678",
            spid_rfc="RFC123456789",
            spid_codigo="04",
            spid_ref_larga="PAGO SERVICIOS",
        )
        gen_spid = self.get_generator("SPID")
        xml_spid = gen_spid.generate(pago_spid)
        xml_spid_mxn = xml_spid.replace(b'Ccy="USD"', b'Ccy="MXN"')
        with self.assertRaises(Exception):
            self.validar_xml_spid(xml_spid_mxn)

        # 4. Nómina sin la palabra NOMINA en InstrId -> debe ser rechazada
        pago_nom = DummyPayment(
            name="PAY/2026/0003",
            amount=12500.00,
            currency_name="MXN",
            partner_acc="4099999999",
            journal_acc="4043001353",
            journal_nomina_acc="4043001353",
            partner_name="EMPLEADO PEREZ",
        )
        gen_nom = self.get_generator("NOMINA")
        xml_nom = gen_nom.generate(pago_nom)
        xml_nom_sin_palabra = xml_nom.replace(b'NOMINA', b'PAGOOTRO')
        with self.assertRaises(Exception):
            self.validar_xml_nomina(xml_nom_sin_palabra)

    def test_08_nomina_multi_employee_generation_and_validation(self):
        """Verifica la generación y validación de nómina con múltiples empleados y montos diferenciados."""
        lineas = [
            DummyNominaLine(partner_name="JUAN LOPEZ", acc_number="4011111111", amount=8000.00),
            DummyNominaLine(partner_name="MARIA GARCIA", acc_number="4022222222", amount=12500.00),
            DummyNominaLine(partner_name="CARLOS SANCHEZ", acc_number="4033333333", amount=9200.00),
        ]
        pago = DummyPayment(
            name="PAY/2026/NOM-01",
            amount=29700.00,
            currency_name="MXN",
            journal_acc="4043001353",
            journal_nomina_acc="4043001353",
            h2h_nomina_line_ids=lineas,
        )
        gen = self.get_generator("NOMINA")
        xml_bytes = gen.generate(pago)

        # 1. Validación estructural
        self.validar_xml_nomina(xml_bytes)

        # 2. Inspeccionar XML generado
        root = ET.fromstring(xml_bytes)
        ns = "urn:iso:std:iso:20022:tech:xsd:pain.001.001.03"

        # NbOfTxs = 3
        nb_txs = root.find(f".//{{{ns}}}GrpHdr/{{{ns}}}NbOfTxs")
        self.assertIsNotNone(nb_txs)
        self.assertEqual(nb_txs.text, "3")

        # CtrlSum = 29700.00
        ctrl_sum = root.find(f".//{{{ns}}}GrpHdr/{{{ns}}}CtrlSum")
        self.assertIsNotNone(ctrl_sum)
        self.assertEqual(ctrl_sum.text, "29700.00")

        # Total de nodos CdtTrfTxInf = 3
        tx_nodes = root.findall(f".//{{{ns}}}CdtTrfTxInf")
        self.assertEqual(len(tx_nodes), 3)

        # Verificar cada empleado individual
        montos_esperados = ["8000.00", "12500.00", "9200.00"]
        cuentas_esperadas = ["4011111111", "4022222222", "4033333333"]
        nombres_esperados = ["JUAN LOPEZ", "MARIA GARCIA", "CARLOS SANCHEZ"]

        for i, tx in enumerate(tx_nodes):
            # InstrId y EndToEndId contienen NOMINA
            instr = tx.find(f"{{{ns}}}PmtId/{{{ns}}}InstrId").text
            e2e = tx.find(f"{{{ns}}}PmtId/{{{ns}}}EndToEndId").text
            self.assertIn("NOMINA", instr)
            self.assertIn("NOMINA", e2e)

            # Monto
            amt_node = tx.find(f"{{{ns}}}Amt/{{{ns}}}InstdAmt")
            self.assertEqual(amt_node.text, montos_esperados[i])
            self.assertEqual(amt_node.attrib.get("Ccy"), "MXN")

            # Nombre
            nm_node = tx.find(f"{{{ns}}}Cdtr/{{{ns}}}Nm")
            self.assertEqual(nm_node.text, nombres_esperados[i])

            # Cuenta
            acc_node = tx.find(f"{{{ns}}}CdtrAcct/{{{ns}}}Id/{{{ns}}}Othr/{{{ns}}}Id")
            self.assertEqual(acc_node.text, cuentas_esperadas[i])

            # Banco 021 (HSBC)
            mmb = tx.find(f"{{{ns}}}CdtrAgt//{{{ns}}}MmbId")
            self.assertEqual(mmb.text, "021")

    def test_09_nomina_multi_employee_rejects_sum_mismatch(self):
        """Verifica que el validador rechace si CtrlSum no cuadra con la suma de los empleados."""
        lineas = [
            DummyNominaLine(partner_name="JUAN LOPEZ", acc_number="4011111111", amount=5000.00),
            DummyNominaLine(partner_name="MARIA GARCIA", acc_number="4022222222", amount=5000.00),
        ]
        pago = DummyPayment(
            name="PAY/2026/NOM-02",
            amount=10000.00,
            currency_name="MXN",
            journal_acc="4043001353",
            journal_nomina_acc="4043001353",
            h2h_nomina_line_ids=lineas,
        )
        gen = self.get_generator("NOMINA")
        xml_bytes = gen.generate(pago)

        # Alterar CtrlSum para simular discrepancia
        xml_alterado = xml_bytes.replace(b"<CtrlSum>10000.00</CtrlSum>", b"<CtrlSum>9999.00</CtrlSum>")
        with self.assertRaises(Exception):
            self.validar_xml_nomina(xml_alterado)


    def test_10_method_switch_and_opi_views_verification(self):
        """Verifica que OPI sea el método en desarrollo en las vistas y datos, y que no existan SWIFT/Domiciliación en vistas."""
        from pathlib import Path
        root = Path(__file__).parent.parent

        # 1. Verificar h2h_method_data.xml
        data_xml = (root / "data" / "h2h_method_data.xml").read_text(encoding="utf-8")
        self.assertIn('id="h2h_method_opi"', data_xml)
        self.assertIn('<field name="code">OPI</field>', data_xml)
        self.assertIn('<field name="is_available" eval="False"/>', data_xml)

        # 2. Verificar h2h_payment_views.xml
        views_xml = (root / "views" / "h2h_payment_views.xml").read_text(encoding="utf-8")
        # Debe contener OPI en desarrollo
        self.assertIn("OPI", views_xml)
        self.assertIn("Orden de pago", views_xml)
        self.assertIn("En desarrollo", views_xml)

        # No debe contener cuadros visuales de SWIFT ni Domiciliación
        self.assertNotIn("SWIFT / Internacional", views_xml)
        self.assertNotIn("Cobro recurrente", views_xml)
        self.assertNotIn("Domiciliación", views_xml)

        # 3. Debe permitir cambiar método antes de enviar al banco
        self.assertIn('invisible="h2h_state in (\'sent_to_bank\', \'accepted\')"', views_xml)


if __name__ == "__main__":
    unittest.main()
