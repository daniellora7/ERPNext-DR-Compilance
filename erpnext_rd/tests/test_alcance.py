"""Alcance por empresa: módulos, campos e idioma solo para quienes trabajan con empresas de RD."""

import frappe
from frappe.tests import IntegrationTestCase

from erpnext_rd.rd_compliance import alcance

EMPRESA_US = "_Test Alcance US"
USUARIO = "alcance.rd@erpnext-rd.test"


class TestAlcancePorEmpresa(IntegrationTestCase):
	def setUp(self):
		frappe.db.savepoint("alcance_rd")
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": EMPRESA_US,
				"abbr": "TAUS",
				"country": "United States",
				"default_currency": "USD",
				"create_chart_of_accounts_based_on": "Standard Template",
				"chart_of_accounts": "Standard",
			}
		).insert()
		frappe.get_doc(
			{"doctype": "User", "email": USUARIO, "first_name": "Alcance", "send_welcome_email": 0}
		).insert()

	def tearDown(self):
		frappe.db.rollback(save_point="alcance_rd")
		frappe.clear_cache(user=USUARIO)

	def bloqueados(self):
		return set(
			frappe.get_all("Block Module", filters={"parenttype": "User", "parent": USUARIO}, pluck="module")
		)

	def test_modulos_segun_las_empresas_del_usuario(self):
		# Sin permisos de usuario trabaja con todas, incluida la de RD
		self.assertTrue(alcance.empresas_rd(USUARIO))
		self.assertFalse(self.bloqueados() & set(alcance.MODULOS))

		# Solo con la empresa de EE. UU.: no ve los módulos de la app
		permiso = frappe.get_doc(
			{"doctype": "User Permission", "user": USUARIO, "allow": "Company", "for_value": EMPRESA_US}
		).insert()
		self.assertEqual(alcance.empresas_rd(USUARIO), [])
		self.assertIn("RD Compliance", self.bloqueados())
		# Así lo lee Frappe para el menú, el dock y los íconos
		from frappe.utils.modules import is_module_visible

		self.assertFalse(is_module_visible("RD Compliance", USUARIO))

		# Sin ese permiso vuelve a verlos
		permiso.delete()
		self.assertFalse(self.bloqueados() & set(alcance.MODULOS))
		self.assertTrue(is_module_visible("RD Compliance", USUARIO))

	def test_campos_solo_en_empresas_rd(self):
		self.assertEqual(alcance.condicion_campo("Sales Invoice", None), f"eval:{alcance.EN_EMPRESA_RD}")
		self.assertEqual(
			alcance.condicion_campo("Purchase Invoice", "rd_ncf_estado_dgii"),
			f"eval:({alcance.EN_EMPRESA_RD}) && (doc.rd_ncf_estado_dgii)",
		)
		self.assertEqual(
			alcance.condicion_campo("Customer", "eval:doc.x"), f"eval:({alcance.CON_EMPRESAS_RD}) && (doc.x)"
		)
		campo = frappe.get_meta("Sales Invoice").get_field("rd_ncf")
		self.assertIn("frappe.boot.empresas_rd", campo.depends_on)
		# Definición compartida entre Customer y Supplier: la condición va una sola vez
		for doctype in ("Customer", "Supplier"):
			depends_on = frappe.get_meta(doctype).get_field("rd_tipo_identificacion").depends_on
			self.assertEqual(depends_on.count("frappe.boot"), 1, doctype)

	def test_idioma_una_sola_vez(self):
		frappe.db.set_default(alcance.CLAVE_IDIOMA, "")
		frappe.db.set_value("User", USUARIO, "language", "en")
		frappe.db.set_single_value("System Settings", "language", "en")
		alcance.idioma_inicial()
		# Hay una empresa de EE. UU.: el sitio no cambia, el usuario (todas sus empresas) tampoco
		self.assertEqual(frappe.db.get_single_value("System Settings", "language"), "en")
		self.assertEqual(frappe.db.get_value("User", USUARIO, "language"), "en")
		self.assertTrue(frappe.db.get_default(alcance.CLAVE_IDIOMA))

		# Una vez hecho no se vuelve a aplicar
		frappe.db.set_value("User", USUARIO, "language", "fr")
		alcance.idioma_inicial()
		self.assertEqual(frappe.db.get_value("User", USUARIO, "language"), "fr")

	def test_sin_empresas_rd_no_toca_erpnext(self):
		"""Sin empresas de RD la instalación no crea registros de ERPNext ni de Frappe HR; la primera
		empresa de RD los prepara."""
		from unittest.mock import patch

		from erpnext_rd import install

		with (
			patch.object(alcance, "hay_empresas_rd", return_value=False),
			patch.object(install, "registros_rd") as registros,
		):
			install.setup()
		registros.assert_not_called()

		with patch.object(alcance, "_primera_empresa_rd") as primera:
			empresa = frappe.get_doc("Company", EMPRESA_US)
			empresa.country = "Dominican Republic"
			with patch.object(frappe.db, "count", return_value=1):
				alcance.al_cambiar_empresa(empresa)
		primera.assert_called_once()
