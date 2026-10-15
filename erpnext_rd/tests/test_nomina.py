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

		from erpnext_rd.nomina_rd import salario, vacaciones

		salario.crear_componentes()
		vacaciones.crear_componente_y_tipo()

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

	def _prestacion(self, regla: str):
		# Ingreso 2025-01-01, salida 2026-09-30: 21 meses completos
		frappe.db.set_value("Employee", self.empleado.name, "relieving_date", "2026-09-30")
		return frappe.get_doc(
			{
				"doctype": "Gratuity",
				"employee": self.empleado.name,
				"company": EMPRESA,
				"posting_date": "2026-09-30",
				"gratuity_rule": regla,
			}
		).insert()

	def test_cesantia_sobre_gratuity(self):
		"""Gratuity de Frappe HR con la regla "Cesantía RD": 1 año x 21 días + 9 meses (13 días) = 34 días
		del salario diario. Sin recibos aprobados se usa la base de la asignación (80,000 / 23.83)."""
		cesantia = self._prestacion("Cesantía RD")
		self.assertEqual(cesantia.rd_meses_servicio, 21)
		self.assertEqual(cesantia.rd_dias, 34)
		self.assertEqual(cesantia.rd_salario_diario, 3357.11)
		self.assertEqual(cesantia.amount, 114_141.74)

	def test_preaviso_sobre_gratuity(self):
		preaviso = self._prestacion("Preaviso RD")
		self.assertEqual(preaviso.rd_dias, 28)
		self.assertEqual(preaviso.amount, 93_999.08)

	def test_promedio_con_recibos_aprobados(self):
		"""El promedio sale de los ingresos que cotizan (el bono de 10,000 no cuenta)."""
		from erpnext_rd.nomina_rd import prestaciones

		self._aislar()
		frappe.get_doc(
			{
				"doctype": "Salary Slip",
				"employee": self.empleado.name,
				"start_date": "2026-08-01",
				"posting_date": "2026-08-31",
				"payroll_frequency": "Monthly",
			}
		).insert().submit()
		promedio = prestaciones.salario_promedio_mensual(
			self.empleado.name, "2026-09-30", prestaciones.componentes_ordinarios()
		)
		self.assertEqual(promedio, 80_000)

	def test_regalia_proporcional_sobre_gratuity(self):
		"""Regla "Regalía RD": salida 2026-09-30, 9 meses del año sin recibos -> 9 x 80,000 / 12."""
		regalia = self._prestacion("Regalía RD")
		self.assertEqual(regalia.rd_meses_servicio, 9)
		self.assertEqual(regalia.rd_salarios_del_anio, 720_000)
		self.assertEqual(regalia.amount, 60_000)

	def test_regalia_con_recibo_aprobado(self):
		"""El mes con recibo aprobado sale del recibo (el bono no cuenta) y no se vuelve a estimar."""
		from erpnext_rd.nomina_rd import prestaciones

		self._aislar()
		frappe.get_doc(
			{
				"doctype": "Salary Slip",
				"employee": self.empleado.name,
				"start_date": "2026-08-01",
				"posting_date": "2026-08-31",
				"payroll_frequency": "Monthly",
			}
		).insert().submit()
		r = prestaciones.regalia_proporcional(self.empleado.name, "2026-09-30")
		self.assertEqual(r.salarios_del_anio, 720_000)

	def test_archivo_tss(self):
		"""Archivo AM de la TSS desde un recibo aprobado: el sueldo cotiza, el bono va como otras
		remuneraciones del ISR."""
		from erpnext_rd.nomina_rd import tss
		from erpnext_rd.tests.test_empleado import cedula_valida

		self._aislar()
		cedula = cedula_valida("0010000005")
		frappe.db.set_value(
			"Employee",
			self.empleado.name,
			{
				"rd_cedula": cedula,
				"last_name": "Peña",
				"rd_segundo_apellido": "Gómez",
				"relieving_date": None,
			},
		)
		frappe.db.set_value("Company", EMPRESA, "tax_id", "101000001")
		frappe.get_doc(
			{
				"doctype": "Salary Slip",
				"employee": self.empleado.name,
				"start_date": "2026-10-01",
				"posting_date": "2026-10-31",
				"payroll_frequency": "Monthly",
			}
		).insert().submit()

		fila = next(f for f in tss.obtener(EMPRESA, 2026, 10) if f["employee"] == self.empleado.name)
		self.assertEqual(
			(fila["salario_ss"], fila["salario_isr"], fila["otras_remuneraciones"]), (80_000, 80_000, 10_000)
		)
		self.assertEqual((fila["tipo_ingreso"], fila["_en_txt"]), ("0001", 1))

		nombre, contenido = tss.generar_txt(EMPRESA, 2026, 10)
		self.assertEqual(nombre, "AM_101000001_102026.txt")
		lineas = contenido.split("\r\n")[:-1]
		self.assertEqual(lineas[0], "EAM  101000001102026")
		self.assertEqual(lineas[-1], "S" + str(len(lineas)).zfill(6))
		detalle = next(linea for linea in lineas if cedula in linea)
		self.assertEqual(detalle[80:120].rstrip(), "PENA")
		self.assertEqual(detalle[169:185], "0000000080000.00")
		self.assertEqual(detalle[217:233], "0000000010000.00")

		# IR-3: renta 90,000 - AFP/SFS 4,728 = 85,272 -> 9,900.94, igual a lo retenido en el recibo
		from erpnext_rd.nomina_rd import ir3

		r = next(f for f in ir3.obtener(EMPRESA, 2026, 10) if f["employee"] == self.empleado.name)
		self.assertEqual((r["renta"], r["aportes_tss"], r["isr"]), (90_000, 4728, 9900.94))
		self.assertEqual(r["diferencia"], 0)
		self.assertEqual(str(ir3.fecha_limite(2026, 10)), "2026-11-10")

	def _aislar(self):
		# Las pruebas de la clase comparten datos: las que crean documentos deshacen lo suyo
		frappe.db.savepoint("vacaciones_rd")
		self.addCleanup(frappe.db.rollback, save_point="vacaciones_rd")

	def _pago_vacaciones(self):
		from erpnext_rd.nomina_rd import vacaciones

		frappe.db.set_value("Employee", self.empleado.name, "relieving_date", "2026-09-30")
		return frappe.get_doc(
			{
				"doctype": "Leave Encashment",
				"employee": self.empleado.name,
				"company": EMPRESA,
				"leave_type": vacaciones.tipo_vacaciones(),
				"encashment_date": "2026-09-30",
			}
		).insert()

	def test_vacaciones_al_salir(self):
		"""Ingreso 2025-01-01, salida 2026-09-30: los 14 días del año cumplido (asignados en el
		aniversario) más 10 días por los 9 meses del año incompleto (art. 180) = 24 x 3,357.11."""
		from erpnext_rd.nomina_rd import vacaciones

		self._aislar()
		frappe.db.set_single_value("Configuracion Nomina RD", "asignar_vacaciones", 1)
		creadas = vacaciones.asignar_vacaciones("2026-03-01", [EMPRESA])
		self.assertEqual(len(creadas), 1)
		self.assertEqual(vacaciones.asignar_vacaciones("2026-03-01", [EMPRESA]), [])
		asignacion = frappe.get_doc("Leave Allocation", creadas[0])
		self.assertEqual(str(asignacion.from_date), "2026-01-01")
		self.assertEqual(str(asignacion.to_date), "2026-12-31")
		self.assertEqual(asignacion.new_leaves_allocated, 14)

		pago = self._pago_vacaciones()
		self.assertEqual(pago.leave_allocation, asignacion.name)
		self.assertEqual(pago.rd_dias_proporcionales, 10)
		self.assertEqual(pago.encashment_days, 24)
		self.assertEqual(pago.rd_salario_diario, 3357.11)
		self.assertEqual(pago.encashment_amount, 80_570.64)

		# Solo los 14 días de la asignación se descuentan de ella
		pago.submit()
		self.assertEqual(
			frappe.db.get_value("Leave Allocation", asignacion.name, "total_leaves_encashed"), 14
		)

	def test_vacaciones_sin_asignacion(self):
		"""Sin asignación vigente solo se paga la proporción del año incompleto."""
		self._aislar()
		pago = self._pago_vacaciones()
		self.assertFalse(pago.leave_allocation)
		self.assertEqual(pago.encashment_days, 10)
		pago.submit()

	def test_vacaciones_solo_al_salir(self):
		"""Art. 182: sin fecha de salida no se pagan vacaciones en dinero."""
		from erpnext_rd.nomina_rd import vacaciones

		self._aislar()
		frappe.db.set_value("Employee", self.empleado.name, "relieving_date", None)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{
					"doctype": "Leave Encashment",
					"employee": self.empleado.name,
					"company": EMPRESA,
					"leave_type": vacaciones.tipo_vacaciones(),
					"encashment_date": "2026-09-30",
				}
			).insert()
