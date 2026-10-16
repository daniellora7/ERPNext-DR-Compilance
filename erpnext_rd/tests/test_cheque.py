import json

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from erpnext_rd.dgii_fiscal import cheque
from erpnext_rd.dgii_fiscal.cheque import monto_en_letras


class TestMontoEnLetras(UnitTestCase):
	def test_pesos(self):
		self.assertEqual(monto_en_letras(1234.56), "MIL DOSCIENTOS TREINTA Y CUATRO PESOS CON 56/100")
		self.assertEqual(monto_en_letras(1), "UN PESO CON 00/100")
		self.assertEqual(monto_en_letras(21), "VEINTIÚN PESOS CON 00/100")
		self.assertEqual(monto_en_letras(21000.05), "VEINTIÚN MIL PESOS CON 05/100")
		self.assertEqual(monto_en_letras(31001), "TREINTA Y UN MIL UN PESOS CON 00/100")
		self.assertEqual(monto_en_letras(1000000), "UN MILLÓN DE PESOS CON 00/100")
		self.assertEqual(monto_en_letras(0.99), "CERO PESOS CON 99/100")

	def test_otras_monedas(self):
		self.assertEqual(monto_en_letras(150.5, "USD"), "CIENTO CINCUENTA DÓLARES CON 50/100")
		self.assertEqual(monto_en_letras(1, "USD"), "UN DÓLAR CON 00/100")


class TestFormatoCheque(IntegrationTestCase):
	def tearDown(self):
		frappe.db.rollback()

	def test_formato_en_el_constructor(self):
		cheque.crear_formato()
		formato = frappe.get_doc("Print Format", cheque.FORMATO)
		self.assertEqual(formato.doc_type, "Payment Entry")
		self.assertEqual(formato.print_format_builder_beta, 1)
		self.assertEqual(formato.standard, "No")
		self.assertIn("--rd-cheque-fecha-arriba", formato.css)
		bloques = [
			c["fields"][0]["fieldname"]
			for s in json.loads(formato.format_data)["sections"]
			for c in s["columns"]
		]
		self.assertEqual(bloques, ["custom_html_1", "custom_html_2", "custom_html_3"])

	def test_datos_y_bloques(self):
		pago = frappe.new_doc("Payment Entry")
		pago.update(
			{
				"payment_type": "Pay",
				"company": frappe.get_all("Company", pluck="name", limit=1)[0],
				"party_type": "Supplier",
				"party_name": "Ferretería Ejemplo SRL",
				"paid_amount": 25000,
				"base_paid_amount": 25000,
				"paid_from": "Banco",
				"paid_to": "Proveedores",
				"paid_from_account_currency": "DOP",
				"reference_no": "000123",
				"reference_date": "2026-10-16",
				"remarks": "Pago de factura de materiales",
			}
		)
		datos = cheque.rd_datos_cheque(pago)
		self.assertEqual(datos.fecha, "16/10/2026")
		self.assertEqual(datos.simbolo, "RD$")
		self.assertEqual(datos.letras, "VEINTICINCO MIL PESOS CON 00/100")
		self.assertEqual(
			[(d.cuenta, d.debito, d.credito) for d in datos.distribucion],
			[("Proveedores", 25000, 0), ("Banco", 0, 25000)],
		)

		for _etiqueta, archivo in cheque.DEFINICION["bloques"]:
			html = frappe.render_template(
				open(
					frappe.get_app_path("erpnext_rd", "templates", "print", "cheque_rd", f"{archivo}.html")
				).read(),
				{"doc": pago},
			)
			self.assertTrue(html.strip())
			if archivo == "cheque":
				self.assertIn("Ferretería Ejemplo SRL", html)
				self.assertIn("VEINTICINCO MIL PESOS", html)
			if archivo == "talon":
				self.assertIn("BORRADOR", html)
				self.assertIn("Cheque n.º 000123", html)
