import json
import unittest

import frappe


class TestSidebarRDCompliance(unittest.TestCase):
	def test_primer_enlace_abre_en_el_escritorio(self):
		"""El ícono del dock abre el primer enlace del sidebar dentro del escritorio (/desk): si fuera
		una URL externa (p. ej. el Panel en /rd-compliance) el escritorio diría "Página no encontrada"."""
		ruta = frappe.get_app_path(
			"erpnext_rd", "rd_compliance", "sidebar", "rd_compliance", "rd_compliance.json"
		)
		with open(ruta, encoding="utf-8") as f:
			items = json.load(f)["items"]
		primero = next(i for i in items if i["type"] == "Link")
		self.assertIn(primero["link_type"], ("DocType", "Workspace"))
		self.assertTrue(any(i.get("url") == "/rd-compliance" for i in items))
