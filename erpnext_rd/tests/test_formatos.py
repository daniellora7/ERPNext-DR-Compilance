"""Formatos de impresión en el constructor de formatos de Frappe (editables por el usuario)."""

import json

import frappe
from frappe.tests import IntegrationTestCase

from erpnext_rd import formatos

PRUEBA = "_Test Formato RD"


class TestFormatosImpresion(IntegrationTestCase):
	def test_fiscales_en_el_constructor(self):
		for definicion in formatos.FISCALES:
			pf = frappe.get_doc("Print Format", definicion["name"])
			self.assertEqual((pf.standard, pf.custom_format, pf.print_format_builder_beta), ("No", 0, 1))
			secciones = json.loads(pf.format_data)["sections"]
			self.assertEqual(len(secciones), len(definicion["bloques"]))
			bloque = secciones[0]["columns"][0]["fields"][0]
			self.assertEqual((bloque["fieldtype"], bloque["custom"]), ("HTML", 1))
			self.assertIn("rd_datos_fiscales(doc)", bloque["html"])
			self.assertTrue(pf.css)

	def test_convierte_version_anterior_y_respeta_lo_editado(self):
		definicion = {**formatos.FISCALES[0], "name": PRUEBA}
		frappe.get_doc(
			{
				"doctype": "Print Format",
				"name": PRUEBA,
				"doc_type": "Sales Invoice",
				"module": formatos.MODULO_FISCAL,
				"custom_format": 1,
				"print_format_type": "Jinja",
				"html": '{% include "erpnext_rd/templates/print/factura_rd.html" %}',
			}
		).insert()
		formatos.asegurar(definicion, formatos.MODULO_FISCAL)
		self.assertEqual(frappe.db.get_value("Print Format", PRUEBA, "print_format_builder_beta"), 1)

		frappe.db.set_value("Print Format", PRUEBA, "css", ".editado {}")
		formatos.asegurar(definicion, formatos.MODULO_FISCAL)
		self.assertEqual(frappe.db.get_value("Print Format", PRUEBA, "css"), ".editado {}")

	def test_datos_una_vez_por_documento(self):
		llamadas = []

		@formatos.por_documento
		def datos(doc):
			llamadas.append(doc.name)
			return frappe._dict(ok=1)

		doc = frappe._dict(doctype="Sales Invoice", name="X-1", modified="2026-10-16", docstatus=1)
		doc.get = doc.__getitem__
		datos(doc)
		datos(doc)
		self.assertEqual(llamadas, ["X-1"])
