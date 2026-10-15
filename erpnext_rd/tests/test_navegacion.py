import json
import unittest

import frappe

from erpnext_rd import install
from erpnext_rd.nomina_rd import hrms_instalado


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

		# El Panel abre dentro del escritorio, en la misma ventana: un enlace URL abriría otra pestaña
		panel = next(i for i in items if i.get("label") == "Panel de cumplimiento")
		self.assertEqual((panel["link_type"], panel["link_to"]), ("Page", "panel-cumplimiento"))
		self.assertTrue(frappe.db.exists("Page", "panel-cumplimiento"))

	def test_nomina_fuera_de_rd_compliance(self):
		"""La Nómina RD tiene su propio sidebar, del lado de Frappe HR, y no una sección en RD Compliance."""
		items = frappe.get_all("Sidebar Item", filters={"parent": "RD Compliance"}, pluck="label")
		self.assertNotIn("Nómina RD", items)
		self.assertNotIn("Configuración Nómina RD", items)


@unittest.skipUnless(hrms_instalado(), "requiere Frappe HR")
class TestDockNominaRD(unittest.TestCase):
	def setUp(self):
		self.limpiar_cache()

	def tearDown(self):
		frappe.db.rollback()
		self.limpiar_cache()

	def limpiar_cache(self):
		# El rollback devuelve las capas del dock pero no el caché de Redis que Frappe arma con ellas
		from frappe.desk.doctype.dock.dock import drop_dock_caches

		drop_dock_caches(None)
		for nombre in frappe.get_all("Dock", pluck="name"):
			frappe.clear_document_cache("Dock", nombre)

	def filas_nomina(self):
		return frappe.get_all(
			"Dock Item",
			filters={"parenttype": "Dock", "link_type": "Sidebar", "link_to": install.SIDEBAR_NOMINA},
			fields=["parent", "added", "icon", "title"],
		)

	def test_sidebar_en_el_dock_de_frappe_hr(self):
		# app = hrms: al abrirlo, el dock que se ve es el de Frappe HR y no el de ERPNext
		self.assertEqual(frappe.db.get_value("Sidebar", install.SIDEBAR_NOMINA, "app"), "hrms")

		install.dock_nomina()
		install.dock_nomina()
		sitio = frappe.get_all("Dock", filters={"app": "hrms", "standard": 0, "user": ""}, pluck="name")
		self.assertEqual(len(sitio), 1)
		filas = [f for f in self.filas_nomina() if f.parent == sitio[0]]
		self.assertEqual(len(filas), 1, "dos pasadas no duplican la entrada")
		self.assertEqual((filas[0].added, filas[0].icon), (1, "nomina-rd-duotone"))

		from frappe.desk.doctype.dock.dock import resolve_app_dock

		dock = resolve_app_dock("hrms", upto="site", gated=False)
		self.assertEqual(dock[-1]["link_to"], install.SIDEBAR_NOMINA)
		self.assertIn("Payroll", [e["link_to"] for e in dock], "conserva los módulos de Frappe HR")

	def test_quitar_deja_el_dock_de_frappe_hr(self):
		install.dock_nomina()
		install.quitar_dock_nomina()
		self.assertFalse(self.filas_nomina())
		from frappe.desk.doctype.dock.dock import resolve_app_dock

		dock = resolve_app_dock("hrms", upto="site", gated=False)
		self.assertIn("Payroll", [e["link_to"] for e in dock])
