"""Cálculos de nómina RD: TSS con topes, ISR de asalariados y regalía pascual."""

import unittest

import frappe
from frappe.tests import IntegrationTestCase

from erpnext_rd.nomina_rd import calculos, hrms_instalado


def conf_2026():
	return frappe._dict(
		salario_minimo_cotizable=23_223,
		tope_afp_salarios=20,
		tope_sfs_salarios=10,
		tope_srl_salarios=4,
		afp_empleado=2.87,
		sfs_empleado=3.04,
		afp_empleador=7.10,
		sfs_empleador=7.09,
		srl_empleador=1.10,
		infotep_empleador=1,
		escala_isr=[
			frappe._dict(desde=d, hasta=h, tasa=t, cuota_fija=c) for d, h, t, c in calculos.ESCALA_ISR_2026
		],
	)


class TestNominaRD(IntegrationTestCase):
	def test_tss_salario_normal(self):
		r = calculos.aportes_tss(50_000, conf_2026())
		self.assertEqual(r.afp, 1435.00)
		self.assertEqual(r.sfs, 1520.00)
		self.assertEqual(r.total_empleado, 2955.00)
		self.assertEqual(r.afp_empleador, 3550.00)
		self.assertEqual(r.sfs_empleador, 3545.00)
		self.assertEqual(r.srl, 550.00)
		self.assertEqual(r.infotep, 500.00)

	def test_tss_aplica_topes(self):
		r = calculos.aportes_tss(500_000, conf_2026())
		self.assertEqual(r.afp, round(464_460 * 0.0287, 2))  # tope 20 salarios
		self.assertEqual(r.sfs, round(232_230 * 0.0304, 2))  # tope 10 salarios
		self.assertEqual(r.srl, round(92_892 * 0.011, 2))  # tope 4 salarios
		self.assertEqual(r.infotep, 5000.00)  # INFOTEP no tiene tope

	def test_isr_exento(self):
		self.assertEqual(calculos.isr_anual(416_220, conf_2026()), 0)
		self.assertEqual(calculos.isr_mensual(34_685, conf_2026()), 0)

	def test_isr_por_tramo(self):
		conf = conf_2026()
		self.assertAlmostEqual(calculos.isr_anual(500_000, conf), (500_000 - 416_220) * 0.15, places=2)
		self.assertAlmostEqual(
			calculos.isr_anual(700_000, conf), 31_216 + (700_000 - 624_329) * 0.20, places=2
		)
		self.assertAlmostEqual(
			calculos.isr_anual(1_000_000, conf), 79_776 + (1_000_000 - 867_123) * 0.25, places=2
		)

	def test_isr_mensual_con_tss(self):
		"""Salario de RD$80,000: gravable 80,000 - 5.91% = 75,272 -> ISR mensual 7,400.94."""
		conf = conf_2026()
		tss = calculos.aportes_tss(80_000, conf)
		self.assertEqual(tss.total_empleado, 4728.00)
		self.assertEqual(calculos.isr_mensual(80_000 - tss.total_empleado, conf), 7400.94)

	def test_regalia_pascual(self):
		self.assertEqual(calculos.regalia_pascual(12 * 30_000), 30_000)
		self.assertEqual(calculos.regalia_pascual(7 * 30_000), 17_500)  # entró a mitad de año

	def test_configuracion_inicial(self):
		conf = frappe.get_single("Configuracion Nomina RD")
		self.assertEqual(len(conf.escala_isr), 4)
		self.assertEqual(conf.escala_isr[-1].tasa, 25)

	def test_escala_con_solapamiento(self):
		conf = frappe.get_doc("Configuracion Nomina RD")
		conf.escala_isr[1].desde = 400_000
		with self.assertRaises(frappe.ValidationError):
			conf.save()


EMPRESA = "_Test Nomina RD"


@unittest.skipUnless(hrms_instalado(), "Requiere Frappe HR (hrms)")
class TestReciboNominaRD(IntegrationTestCase):
	"""Recibo de nómina de Frappe HR en una empresa RD: TSS e ISR calculados por la app."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.db.set_single_value("Configuracion DGII", "aplicar_catalogo_cuentas", 1)
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": EMPRESA,
				"abbr": "TNRD",
				"country": "Dominican Republic",
				"default_currency": "DOP",
				"chart_of_accounts": "Standard",
				"create_chart_of_accounts_based_on": "Standard Template",
			}
		).insert()
		lista = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "_Test Feriados Nomina RD",
				"from_date": "2026-01-01",
				"to_date": "2026-12-31",
			}
		).insert()
		frappe.db.set_value("Company", EMPRESA, "default_holiday_list", lista.name)
		frappe.get_doc(
			{
				"doctype": "Holiday List Assignment",
				"applicable_for": "Company",
				"assigned_to": EMPRESA,
				"holiday_list": lista.name,
				"from_date": "2026-01-01",
			}
		).submit()

		from erpnext_rd.nomina_rd import salario

		salario.crear_componentes()

		for nombre, abbr, cotiza in (
			("_Test Sueldo RD", "SUELDO_T", 1),
			("_Test Bono No Cotizable", "BONO_T", 0),
		):
			if not frappe.db.exists("Salary Component", nombre):
				frappe.get_doc(
					{
						"doctype": "Salary Component",
						"salary_component": nombre,
						"salary_component_abbr": abbr,
						"type": "Earning",
						"is_tax_applicable": 1,
						"depends_on_payment_days": 0,
						"rd_cotiza_tss": cotiza,
					}
				).insert()

		estructura = frappe.get_doc(
			{
				"doctype": "Salary Structure",
				"name": "_Test Estructura RD",
				"company": EMPRESA,
				"currency": "DOP",
				"payroll_frequency": "Monthly",
				"earnings": [
					{"salary_component": "_Test Sueldo RD", "amount_based_on_formula": 1, "formula": "base"},
					{"salary_component": "_Test Bono No Cotizable", "amount": 10_000},
				],
			}
		).insert()
		estructura.submit()

		genero = (
			frappe.db.get_value("Gender", {})
			or frappe.get_doc({"doctype": "Gender", "gender": "Otro"}).insert().name
		)
		cls.empleado = frappe.get_doc(
			{
				"doctype": "Employee",
				"first_name": "_Test Empleado RD",
				"gender": genero,
				"date_of_birth": "1990-01-01",
				"date_of_joining": "2025-01-01",
				"company": EMPRESA,
				"status": "Active",
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "Salary Structure Assignment",
				"employee": cls.empleado.name,
				"salary_structure": estructura.name,
				"company": EMPRESA,
				"currency": "DOP",
				"from_date": "2026-01-01",
				"base": 80_000,
			}
		).submit()

	def _recibo(self):
		return frappe.get_doc(
			{
				"doctype": "Salary Slip",
				"employee": self.empleado.name,
				"start_date": "2026-09-01",
				"posting_date": "2026-09-30",
				"payroll_frequency": "Monthly",
			}
		).insert()

	def test_deducciones_de_ley(self):
		recibo = self._recibo()
		deducciones = {f.abbr: f.amount for f in recibo.deductions}
		aportes = {f.abbr: f.amount for f in recibo.employer_contributions}

		self.assertEqual(recibo.gross_pay, 90_000)
		# TSS sobre 80,000 (el bono no cotiza)
		self.assertEqual(deducciones["AFP"], 2296.00)
		self.assertEqual(deducciones["SFS"], 2432.00)
		# ISR sobre 90,000 - 4,728 = 85,272 mensual -> 1,023,264 anual
		self.assertEqual(deducciones["ISR"], 9900.94)
		self.assertAlmostEqual(recibo.net_pay, 90_000 - 2296 - 2432 - 9900.94, places=2)

		self.assertEqual(aportes["AFP_ER"], 5680.00)
		self.assertEqual(aportes["SFS_ER"], 5672.00)
		self.assertEqual(aportes["SRL"], 880.00)
		self.assertEqual(aportes["INFOTEP"], 800.00)

	def test_componentes_con_cuentas_del_catalogo(self):
		afp = frappe.get_doc("Salary Component", "AFP - Fondo de Pensiones")
		cuenta = next(a.account for a in afp.accounts if a.company == EMPRESA)
		self.assertTrue(cuenta.startswith("210402"))
		infotep = frappe.get_doc("Salary Component", "INFOTEP - Aporte Empleador")
		fila = next(a for a in infotep.accounts if a.company == EMPRESA)
		self.assertTrue(fila.account.startswith("6109"))
		self.assertTrue(fila.liability_account.startswith("210403"))

	def test_desactivado(self):
		frappe.db.set_single_value("Configuracion Nomina RD", "calcular_deducciones", 0)
		try:
			recibo = self._recibo()
			self.assertNotIn("AFP", {f.abbr for f in recibo.deductions})
		finally:
			frappe.db.set_single_value("Configuracion Nomina RD", "calcular_deducciones", 1)
