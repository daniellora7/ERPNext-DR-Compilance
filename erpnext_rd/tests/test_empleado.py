"""Datos RD del empleado: cédula, NSS, segundo apellido, AFP y ARS (Employee de ERPNext, sin HRMS)."""

import unittest

import frappe
from frappe.tests import IntegrationTestCase

from erpnext_rd.dgii_fiscal.ncf import PAIS
from erpnext_rd.dgii_fiscal.validaciones import es_cedula_valida


def cedula_valida(base: str) -> str:
	"""Completa 10 dígitos con el dígito verificador."""
	return next(base + str(d) for d in range(10) if es_cedula_valida(base + str(d)))


class TestEmpleadoRD(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.empresa = frappe.db.get_value("Company", {"country": PAIS}, "name")
		if not cls.empresa:
			raise unittest.SkipTest("sin empresa RD")
		cls.genero = (
			frappe.db.get_value("Gender", {})
			or frappe.get_doc({"doctype": "Gender", "gender": "Otro"}).insert().name
		)

	def _empleado(self, **datos):
		return frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "_Test",
				"last_name": "Pérez",
				"gender": self.genero,
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2026-01-01",
				"company": self.empresa,
				"status": "Active",
				**datos,
			}
		)

	def test_cedula_sin_guiones_y_segundo_apellido(self):
		cedula = cedula_valida("0010000001")
		empleado = self._empleado(
			rd_segundo_apellido="García",
			rd_cedula=f"{cedula[:3]}-{cedula[3:10]}-{cedula[10]}",
			rd_nss="123-456 789",
		).insert()
		self.assertEqual(empleado.rd_cedula, cedula)
		self.assertEqual(empleado.rd_nss, "123456789")
		self.assertEqual(empleado.employee_name, "_Test Pérez García")

	def test_cedula_invalida(self):
		cedula = cedula_valida("0010000002")
		mala = cedula[:10] + str((int(cedula[10]) + 1) % 10)
		with self.assertRaises(frappe.ValidationError):
			self._empleado(rd_cedula=mala).insert()

	def test_cedula_repetida_en_la_empresa(self):
		cedula = cedula_valida("0010000003")
		self._empleado(rd_cedula=cedula).insert()
		with self.assertRaises(frappe.ValidationError):
			self._empleado(first_name="_Test Otro", rd_cedula=cedula).insert()

	def test_catalogo_afp_ars(self):
		self.assertTrue(frappe.db.exists("Entidad Seguridad Social RD", {"tipo": "AFP"}))
		self.assertTrue(frappe.db.exists("Entidad Seguridad Social RD", {"tipo": "ARS"}))
		afp = frappe.db.get_value("Entidad Seguridad Social RD", {"tipo": "AFP"})
		ars = frappe.db.get_value("Entidad Seguridad Social RD", {"tipo": "ARS"})
		empleado = self._empleado(rd_afp=afp, rd_ars=ars).insert()
		self.assertEqual((empleado.rd_afp, empleado.rd_ars), (afp, ars))

	def test_buscar_por_cedula(self):
		self.assertIn("rd_cedula", frappe.get_meta("Employee").search_fields)
