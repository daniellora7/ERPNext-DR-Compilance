"""Portal del empleado: solo sus volantes, su acumulado del año y sus permisos."""

import unittest

import frappe
from frappe.tests import IntegrationTestCase

from erpnext_rd.nomina_rd import hrms_instalado, salario

USUARIO = "empleado.portal@erpnext-rd.test"


@unittest.skipUnless(hrms_instalado(), "requiere Frappe HR")
class TestPortalEmpleado(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from erpnext_rd.tests import test_nomina

		# Empresa, estructura salarial y empleado de las pruebas del recibo de nómina
		test_nomina.TestReciboNominaRD.setUpClass()
		cls.empleado = test_nomina.TestReciboNominaRD.empleado
		if not frappe.db.exists("User", USUARIO):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": USUARIO,
					"first_name": "Empleado Portal",
					"send_welcome_email": 0,
					"roles": [{"role": "Employee"}],
				}
			).insert(ignore_permissions=True)
		frappe.db.set_value("Employee", cls.empleado.name, "user_id", USUARIO)
		recibo = frappe.get_doc(
			{
				"doctype": "Salary Slip",
				"employee": cls.empleado.name,
				"start_date": "2026-09-01",
				"posting_date": "2026-09-30",
				"payroll_frequency": "Monthly",
			}
		).insert()
		recibo.submit()
		cls.recibo = recibo

	def tearDown(self):
		frappe.set_user("Administrator")

	def test_sin_empleado_no_entra(self):
		from erpnext_rd.nomina_rd import portal

		self.assertFalse(portal.tiene_portal())
		self.assertRaises(frappe.PermissionError, portal.resumen)

	def test_resumen_del_empleado(self):
		from erpnext_rd.nomina_rd import portal

		frappe.set_user(USUARIO)
		self.assertTrue(portal.tiene_portal())
		r = portal.resumen()
		self.assertEqual(r["empleado"]["codigo"], self.empleado.name)
		self.assertEqual([v.name for v in r["volantes"]], [self.recibo.name])

		deducciones = {salario._concepto(d.salary_component): d.amount for d in self.recibo.deductions}
		a = portal.acumulado(self.empleado.name, 2026)
		self.assertEqual(a["volantes"], 1)
		self.assertEqual(a["bruto"], self.recibo.gross_pay)
		self.assertEqual(a["neto"], self.recibo.net_pay)
		self.assertEqual(a["afp"], deducciones[salario.AFP])
		self.assertEqual(a["isr"], deducciones[salario.ISR])
		self.assertEqual(portal.acumulado(self.empleado.name, 2025)["volantes"], 0)

	def test_volante_de_otro_no(self):
		from erpnext_rd.nomina_rd import portal

		frappe.set_user(USUARIO)
		self.assertRaises(frappe.PermissionError, portal.volante, "Sal Slip/no-existe/00001")

	def test_permiso_sin_asignacion(self):
		from erpnext_rd.nomina_rd import portal

		frappe.set_user(USUARIO)
		self.assertRaises(
			frappe.ValidationError, portal.solicitar_permiso, "_Tipo inexistente", "2026-12-01", "2026-12-02"
		)

	def test_proximo_aniversario(self):
		from datetime import date

		from erpnext_rd.nomina_rd import portal

		self.assertEqual(portal.proximo_aniversario("2025-01-01", date(2026, 11, 12)), date(2027, 1, 1))
		self.assertEqual(portal.proximo_aniversario("2025-12-01", date(2026, 11, 12)), date(2026, 12, 1))
		self.assertIsNone(portal.proximo_aniversario(None, date(2026, 11, 12)))
