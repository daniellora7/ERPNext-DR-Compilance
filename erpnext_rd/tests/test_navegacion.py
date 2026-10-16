import json
import unittest

import frappe

from erpnext_rd import install
from erpnext_rd.nomina_rd import hrms_instalado


class TestSidebarRDCompliance(unittest.TestCase):
	def test_primer_enlace_abre_en_el_escritorio(self):
		"""El ícono del dock abre el primer enlace del sidebar dentro del escritorio (/desk): si fuera
		una URL externa (p. ej. el Panel en /rd-compliance) el escritorio diría "Página no encontrada".
		Frappe busca la página de inicio con `module_landing_route`: el primer enlace navegable."""
		ruta = frappe.get_app_path(
			"erpnext_rd", "rd_compliance", "sidebar", "rd_compliance", "rd_compliance.json"
		)
		with open(ruta, encoding="utf-8") as f:
			items = json.load(f)["items"]
		primero = next(i for i in items if i["type"] == "Link")

		# El módulo abre en el Panel, dentro del escritorio y en la misma ventana (no un enlace URL)
		self.assertEqual((primero["link_type"], primero["link_to"]), ("Page", "panel-cumplimiento"))
		self.assertTrue(frappe.db.exists("Page", "panel-cumplimiento"))

	def test_nomina_abre_en_las_planillas(self):
		"""La Nómina RD abre en las planillas de nómina, donde se corre cada quincena o mes."""
		ruta = frappe.get_app_path("erpnext_rd", "nomina_rd", "sidebar", "nomina_rd", "nomina_rd.json")
		with open(ruta, encoding="utf-8") as f:
			items = json.load(f)["items"]
		primero = next(i for i in items if i["type"] == "Link")
		self.assertEqual((primero["link_type"], primero["link_to"]), ("DocType", "Payroll Entry"))

	def test_nomina_fuera_de_rd_compliance(self):
		"""La Nómina RD tiene su propio sidebar, del lado de Frappe HR, y no una sección en RD Compliance."""
		items = frappe.get_all("Sidebar Item", filters={"parent": "RD Compliance"}, pluck="label")
		self.assertNotIn("Nómina RD", items)
		self.assertNotIn("Configuración Nómina RD", items)


class TestDockTraducido(unittest.TestCase):
	def test_titulos_en_el_idioma_del_usuario(self):
		"""Frappe v16 no traduce los nombres del dock: la app los traduce al armar la sesión."""
		from erpnext_rd.boot import traducir_dock

		def bootinfo():
			return frappe._dict(
				dock={"erpnext": [{"link_type": "Sidebar", "link_to": "Accounts", "title": "Accounts"}]},
				app_data=[{"app_name": "erpnext", "dock": [{"link_to": "Selling", "title": "Selling"}]}],
			)

		idioma = frappe.local.lang
		try:
			frappe.local.lang = "es"
			es = bootinfo()
			traducir_dock(es)
			self.assertEqual(es.dock["erpnext"][0]["title"], "Cuentas")
			self.assertEqual(es.app_data[0]["dock"][0]["title"], "Ventas")
			# El destino no cambia: es lo que identifica la entrada al guardar "Organizar dock"
			self.assertEqual(es.dock["erpnext"][0]["link_to"], "Accounts")

			frappe.local.lang = "en"
			en = bootinfo()
			traducir_dock(en)
			self.assertEqual(en.dock["erpnext"][0]["title"], "Accounts")
		finally:
			frappe.local.lang = idioma

	@unittest.skipUnless(hrms_instalado(), "requiere Frappe HR")
	def test_frappe_hr_completo_en_espanol(self):
		"""Los textos que faltan en el catálogo de Frappe HR vienen en el es.po de la app."""
		idioma = frappe.local.lang
		try:
			frappe.local.lang = "es"
			for texto, esperado in (
				("HR Setup", "Configuración de RR. HH."),
				("Tenure", "Trayectoria"),
				("Recruitment", "Reclutamiento"),
				("Salary Slip", "Recibo de nómina"),
			):
				self.assertEqual(frappe._(texto), esperado)
		finally:
			frappe.local.lang = idioma


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
			fields=["name", "parent", "added", "icon", "title"],
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
		self.assertEqual((filas[0].added, filas[0].icon), (1, install.ICONO_DOCK_NOMINA))

		# Un sitio con la entrada del ícono anterior pasa al nuevo
		frappe.db.set_value("Dock Item", filas[0].name, "icon", "nomina-rd-duotone")
		install.dock_nomina()
		self.assertEqual(frappe.db.get_value("Dock Item", filas[0].name, "icon"), install.ICONO_DOCK_NOMINA)

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
