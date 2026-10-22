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

	def test_reparto_de_bonificacion(self):
		"""Art. 223: si el 10 % no alcanza para los topes, se reparte en proporción a ellos; si sobra,
		cada uno recibe su tope."""
		from erpnext_rd.nomina_rd import bonificacion

		filas = [{"tope": 60_000}, {"tope": 40_000}]
		self.assertEqual(bonificacion.repartir(filas, 80_000), (100_000, 0.8))
		self.assertEqual([f["monto"] for f in filas], [48_000, 32_000])
		bonificacion.repartir(filas, 500_000)
		self.assertEqual([f["monto"] for f in filas], [60_000, 40_000])
		bonificacion.repartir(filas, -10_000)  # sin utilidad, no hay bonificación
		self.assertEqual([f["monto"] for f in filas], [0, 0])

	def test_recargos_de_horas_extras(self):
		"""Art. 203: 35 % hasta 68 horas semanales (24 extras sobre la jornada de 44) y 100 % después;
		feriados y descanso semanal, 100 %."""
		from erpnext_rd.nomina_rd.horas_extras import monto

		p = frappe._dict(
			horas_normales=44, horas_maximo=68, recargo=35, recargo_exceso=100, recargo_feriado=100
		)
		self.assertAlmostEqual(monto(10, 100, 0, False, p), 1350)
		self.assertAlmostEqual(monto(10, 100, 20, False, p), 4 * 135 + 6 * 200)  # pasa del límite
		self.assertAlmostEqual(monto(3, 100, 30, False, p), 600)  # ya pasó del límite
		self.assertAlmostEqual(monto(5, 100, 0, True, p), 1000)  # feriado

	def test_recargo_nocturno(self):
		"""Art. 204: 15 % más en la parte de las horas extras entre las 9:00 p. m. y las 7:00 a. m."""
		import datetime

		from erpnext_rd.nomina_rd.horas_extras import horas_nocturnas, monto, nocturnas_de_la_salida

		p = frappe._dict(
			horas_normales=44,
			horas_maximo=68,
			recargo=35,
			recargo_exceso=100,
			recargo_feriado=100,
			recargo_nocturno=15,
			inicio_nocturna=datetime.time(21),
			fin_nocturna=datetime.time(7),
		)
		# Salida a las 11:00 p. m. con 4 horas extras (7 a 11 p. m.): 2 nocturnas
		self.assertAlmostEqual(nocturnas_de_la_salida("2026-10-05 23:00:00", 4, p), 2)
		# Cruza la medianoche: 10 p. m. a 2 a. m., todas nocturnas
		self.assertAlmostEqual(horas_nocturnas("2026-10-05 22:00:00", "2026-10-06 02:00:00", p), 4)
		# Madrugada: 5 a 9 a. m., 2 nocturnas
		self.assertAlmostEqual(horas_nocturnas("2026-10-06 05:00:00", "2026-10-06 09:00:00", p), 2)
		self.assertEqual(nocturnas_de_la_salida(None, 4, p), 0)
		self.assertAlmostEqual(monto(4, 100, 0, False, p, nocturnas=2), 4 * 135 + 2 * 15)
		self.assertAlmostEqual(monto(4, 100, 0, True, p, nocturnas=4), 4 * 200 + 4 * 15)

	def test_configuracion_inicial(self):
		conf = frappe.get_single("Configuracion Nomina RD")
		self.assertEqual([len(calculos.escala_isr(conf, a)) for a in (2026, 2027)], [4, 5])
		self.assertEqual(calculos.escala_isr(conf, 2026)[-1].tasa, 25)
		self.assertEqual(calculos.escala_isr(conf, 2027)[-1].tasa, 27)

	def test_escala_isr_2027(self):
		"""Ley 30-26: exento hasta 480,000; 15%, 20%, 25% y 27% desde 4.8 millones."""
		conf = conf_2026()
		conf.escala_isr = [
			frappe._dict(anio=anio, desde=d, hasta=h, tasa=t, cuota_fija=c)
			for anio, escala in calculos.ESCALAS_ISR.items()
			for d, h, t, c in escala
		]
		self.assertEqual(calculos.isr_anual(480_000, conf, 2027), 0)
		self.assertAlmostEqual(calculos.isr_anual(700_000, conf, 2027), 30_750 + 15_000 * 0.20, places=2)
		self.assertAlmostEqual(
			calculos.isr_anual(5_000_000, conf, 2027), 1_048_250 + 200_000 * 0.27, places=2
		)
		# 2026 sigue con su escala; años sin escala propia usan la más reciente anterior (o la primera)
		self.assertAlmostEqual(calculos.isr_anual(500_000, conf, 2026), (500_000 - 416_220) * 0.15, places=2)
		self.assertEqual(calculos.isr_anual(470_000, conf, 2028), 0)
		self.assertGreater(calculos.isr_anual(470_000, conf, 2025), 0)
		# Mismo salario: 80,000 menos AFP y SFS, en enero 2027 retiene menos que en diciembre 2026
		self.assertEqual(calculos.isr_mensual(75_272, conf, 2026), 7400.94)
		self.assertEqual(calculos.isr_mensual(75_272, conf, 2027), 6200.23)

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

		from erpnext_rd.nomina_rd import regalia, salario, vacaciones

		salario.crear_componentes()
		vacaciones.crear_componente_y_tipo()
		regalia.crear_componente()

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

	def test_escala_del_anio_del_recibo(self):
		"""El recibo usa la escala del año de su período: sueldo 80,000 + bono 10,000 - AFP/SFS 4,728."""
		from erpnext_rd.nomina_rd import salario

		recibo = self._recibo()
		self.assertEqual(salario.calcular(recibo)[salario.ISR], 9900.94)
		recibo.end_date = "2027-01-31"
		self.assertEqual(salario.calcular(recibo)[salario.ISR], 8672.17)

	def test_isr_de_frappe_hr_duplicado(self):
		from erpnext_rd.nomina_rd import salario

		if not frappe.db.exists("Salary Component", "_Test ISR Frappe HR"):
			frappe.get_doc(
				{
					"doctype": "Salary Component",
					"salary_component": "_Test ISR Frappe HR",
					"salary_component_abbr": "ISR_HR_T",
					"type": "Deduction",
					"variable_based_on_taxable_salary": 1,
				}
			).insert()
		recibo = self._recibo()
		recibo.append("deductions", {"salary_component": "_Test ISR Frappe HR", "amount": 5000})
		with self.assertRaises(frappe.ValidationError):
			salario.al_validar_recibo(recibo)

	def test_subsidio_con_la_licencia(self):
		if not frappe.db.exists("Leave Type", "_Test Licencia Medica RD"):
			frappe.get_doc(
				{"doctype": "Leave Type", "leave_type_name": "_Test Licencia Medica RD", "is_lwp": 1}
			).insert()
		licencia = frappe.get_doc(
			{
				"doctype": "Leave Application",
				"employee": self.empleado.name,
				"company": EMPRESA,
				"leave_type": "_Test Licencia Medica RD",
				"from_date": "2026-10-05",
				"to_date": "2026-10-09",
			}
		).insert()
		subsidio = frappe.get_doc(
			{
				"doctype": "Subsidio SISALRIL",
				"employee": self.empleado.name,
				"tipo": "Enfermedad común",
				"desde": "2026-10-01",
				"licencia": licencia.name,
				"salario_base": 30_000,
			}
		).insert()
		self.assertEqual(subsidio.tipo_licencia, "Leave Application")
		self.assertEqual((str(subsidio.desde), str(subsidio.hasta)), ("2026-10-05", "2026-10-09"))

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
		self.assertEqual(str(ir3.fecha_limite(2025, 12)), "2026-01-12")  # el 10 cae sábado

		# IR-13: la suma del año (aquí solo octubre)
		from erpnext_rd.nomina_rd import ir13

		datos = ir13.meses(EMPRESA, 2026)
		e = next(f for f in ir13.por_empleado(datos) if f["employee"] == self.empleado.name)
		self.assertEqual((e["meses"], e["renta"], e["isr"], e["isr_retenido"]), (1, 90_000, 9900.94, 9900.94))
		self.assertFalse(e["_avisos"])
		octubre = ir13.por_mes(datos)[9]
		self.assertEqual((octubre["mes"], octubre["isr_retenido"]), ("Oct", 9900.94))
		self.assertEqual(str(ir13.fecha_limite(2026)), "2027-03-15")

	def test_regalia_de_diciembre(self):
		"""Regalía de diciembre de un empleado activo: octubre sale del recibo y los otros 11 meses se
		estiman con la base (12 x 80,000 / 12). Se paga en el recibo de diciembre, sin ISR ni TSS, y va
		en el archivo de la TSS como ingreso exento."""
		from erpnext_rd.nomina_rd import regalia, tss

		self._aislar()
		frappe.db.set_value("Employee", self.empleado.name, "relieving_date", None)

		def recibo(mes):
			return (
				frappe.get_doc(
					{
						"doctype": "Salary Slip",
						"employee": self.empleado.name,
						"start_date": f"2026-{mes}-01",
						"payroll_frequency": "Monthly",
					}
				)
				.insert()
				.submit()
			)

		octubre = recibo(10)
		fila = next(f for f in regalia.obtener(EMPRESA, 2026) if f["employee"] == self.empleado.name)
		self.assertEqual((fila["meses"], fila["meses_estimados"], fila["regalia"]), (12, 11, 80_000))
		self.assertFalse(fila["gratuity"])

		creadas = regalia.crear_regalias(EMPRESA, 2026)["creadas"]
		self.assertEqual(len(creadas), 1)
		self.assertEqual(regalia.crear_regalias(EMPRESA, 2026)["creadas"], [])
		g = frappe.get_doc("Gratuity", creadas[0])
		self.assertEqual(
			(g.amount, str(g.payroll_date), g.salary_component), (80_000, "2026-12-15", regalia.COMPONENTE)
		)
		g.submit()

		diciembre = recibo(12)
		self.assertIn(regalia.COMPONENTE, {f.salary_component for f in diciembre.earnings})
		isr = {f.abbr: f.amount for f in diciembre.deductions}
		self.assertEqual(isr["ISR"], {f.abbr: f.amount for f in octubre.deductions}["ISR"])

		f = next(f for f in tss.obtener(EMPRESA, 2026, 12) if f["employee"] == self.empleado.name)
		self.assertEqual((f["salario_ss"], f["otras_remuneraciones"], f["regalia"]), (80_000, 10_000, 80_000))

	def test_novedades(self):
		"""Cambio de salario (AD) el 5 de octubre y salida (SA) el 20: sin recibo del mes, el salario se
		estima con la nueva base por los días trabajados (90,000 x 20 / 31)."""
		from erpnext_rd.nomina_rd import novedades
		from erpnext_rd.tests.test_empleado import cedula_valida

		self._aislar()
		frappe.db.set_value(
			"Employee",
			self.empleado.name,
			{"rd_cedula": cedula_valida("0010000006"), "relieving_date": "2026-10-20"},
		)
		frappe.get_doc(
			{
				"doctype": "Salary Structure Assignment",
				"employee": self.empleado.name,
				"salary_structure": "_Test Estructura RD",
				"company": EMPRESA,
				"currency": "DOP",
				"from_date": "2026-10-05",
				"base": 90_000,
			}
		).submit()

		filas = novedades.obtener(EMPRESA, 2026, 10, employee=self.empleado.name)
		self.assertEqual(
			[(f["tipo_novedad"], str(f["fecha_inicio"])) for f in filas],
			[("AD", "2026-10-05"), ("SA", "2026-10-20")],
		)
		salida = filas[1]
		self.assertEqual((salida["salario_ss"], salida["_en_txt"]), (58_064.52, 1))
		self.assertIn("estimado", salida["_avisos"])

		frappe.db.set_value("Company", EMPRESA, "tax_id", "101000001")
		nombre, contenido = novedades.generar_txt(
			EMPRESA, 2026, 10, employee=self.empleado.name, tipo=novedades.SALIDA
		)
		lineas = contenido.split("\r\n")[:-1]
		self.assertEqual(nombre, "NV_101000001_102026.txt")
		self.assertEqual(lineas[0], "ENV  101000001102026")
		self.assertEqual((len(lineas), lineas[1][4:14]), (3, "SA20102026"))

	def test_bonificacion(self):
		"""Utilidad 1,000,000 -> 100,000 a repartir. Ingreso 2025-01-01: al cierre de 2026 tiene 2 años
		(tope de 45 días) y trabajó los 12 meses; salario diario 80,000 / 23.83 = 3,357.11 -> tope
		151,069.95. El fondo no alcanza: recibe los 100,000. En el recibo, INFOTEP del empleado 0.5 % y
		en el archivo de la TSS va como otra remuneración (no cotiza)."""
		from erpnext_rd.nomina_rd import salario, tss

		self._aislar()
		frappe.db.set_value("Employee", self.empleado.name, "relieving_date", None)
		ejercicio = (
			frappe.db.get_value(
				"Fiscal Year", {"year_start_date": "2026-01-01", "year_end_date": "2026-12-31"}
			)
			or frappe.get_doc(
				{
					"doctype": "Fiscal Year",
					"year": "2026 RD",
					"year_start_date": "2026-01-01",
					"year_end_date": "2026-12-31",
				}
			)
			.insert()
			.name
		)

		bono = frappe.get_doc(
			{
				"doctype": "Bonificacion RD",
				"company": EMPRESA,
				"ejercicio": ejercicio,
				"utilidad_neta": 1_000_000,
				"fecha_pago": "2026-12-20",
			}
		)
		bono.desde, bono.hasta = "2026-01-01", "2026-12-31"
		bono.calcular()
		fila = next(f for f in bono.empleados if f.employee == self.empleado.name)
		self.assertEqual(
			(fila.meses, fila.dias, fila.salario_diario, fila.tope), (12, 45, 3357.11, 151_069.95)
		)
		self.assertEqual((bono.porcentaje, bono.fondo, str(bono.fecha_limite)), (10, 100_000, "2027-04-30"))
		self.assertAlmostEqual(fila.monto, 100_000, delta=0.01)
		bono.insert()
		bono.submit()
		pago = frappe.db.get_value("Bonificacion RD Empleado", fila.name, "additional_salary")
		self.assertEqual(frappe.db.get_value("Additional Salary", pago, "docstatus"), 1)

		recibo = (
			frappe.get_doc(
				{
					"doctype": "Salary Slip",
					"employee": self.empleado.name,
					"start_date": "2026-12-01",
					"payroll_frequency": "Monthly",
				}
			)
			.insert()
			.submit()
		)
		deducciones = {f.abbr: f.amount for f in recibo.deductions}
		self.assertAlmostEqual(deducciones["INFOTEP_EE"], 500, delta=0.01)
		f = next(f for f in tss.obtener(EMPRESA, 2026, 12) if f["employee"] == self.empleado.name)
		self.assertEqual(f["salario_ss"], 80_000)
		self.assertAlmostEqual(f["otras_remuneraciones"], 110_000, delta=0.01)
		self.assertEqual(salario.calcular(recibo)[salario.AFP], deducciones["AFP"])

		recibo.cancel()  # el recibo que la pagó se cancela primero
		bono.cancel()
		self.assertEqual(frappe.db.get_value("Additional Salary", pago, "docstatus"), 2)

	@unittest.skipUnless(frappe.db.exists("DocType", "Overtime Type"), "Frappe HR sin horas extras")
	def test_horas_extras(self):
		"""Tipo "Horas extras RD": hora = 80,000 / 23.83 / 8; 20 h el lunes (35 %) y 10 h el martes de la
		misma semana (4 h al 35 % y 6 h al 100 %, pasó de 68 horas); 5 h en un feriado, 100 %."""
		from erpnext_rd.nomina_rd import horas_extras
		from erpnext_rd.nomina_rd.horas_extras_rd import OvertimeSlipRD

		self._aislar()
		frappe.db.set_value("Employee", self.empleado.name, "relieving_date", None)
		horas_extras.crear_componente_y_tipo()
		self.assertTrue(frappe.db.get_value("Overtime Type", horas_extras.TIPO, "rd_horas_extras"))
		hoja = frappe.new_doc("Overtime Slip")
		self.assertIsInstance(hoja, OvertimeSlipRD)
		hoja.update(
			{
				"employee": self.empleado.name,
				"company": EMPRESA,
				"start_date": "2026-10-01",
				"end_date": "2026-10-31",
			}
		)
		hoja.overtime_types = hoja._bulk_load_overtime_types({horas_extras.TIPO})
		hora = hoja._calculate_component_based_hourly_rate(horas_extras.TIPO, 9)
		self.assertAlmostEqual(hora, 80_000 / 23.83 / 8, places=6)

		feriados = {"2026-10-12": frappe._dict(weekly_off=0)}
		lunes = hoja.calculate_overtime_amount(horas_extras.TIPO, hora, 20, "2026-10-05", feriados)
		martes = hoja.calculate_overtime_amount(horas_extras.TIPO, hora, 10, "2026-10-06", feriados)
		feriado = hoja.calculate_overtime_amount(horas_extras.TIPO, hora, 5, "2026-10-12", feriados)
		self.assertAlmostEqual(lunes, 20 * hora * 1.35, places=4)
		self.assertAlmostEqual(martes, hora * (4 * 1.35 + 6 * 2), places=4)
		self.assertAlmostEqual(feriado, 5 * hora * 2, places=4)

	def test_volante_de_pago(self):
		"""El formato Volante de pago RD imprime el documento con guiones, AFP / ISR y el neto."""
		from erpnext_rd.nomina_rd import volante
		from erpnext_rd.tests.test_empleado import cedula_valida

		self._aislar()
		cedula = cedula_valida("0010000007")
		frappe.db.set_value(
			"Employee",
			self.empleado.name,
			{"rd_cedula": cedula, "rd_nss": "12345678", "relieving_date": None},
		)
		volante.crear_formato()
		recibo = frappe.get_doc(
			{
				"doctype": "Salary Slip",
				"employee": self.empleado.name,
				"start_date": "2026-07-01",
				"payroll_frequency": "Monthly",
			}
		).insert()
		recibo.submit()
		html = frappe.get_print("Salary Slip", recibo.name, print_format=volante.FORMATO, no_letterhead=1)
		self.assertIn("Volante de pago", html)
		self.assertIn(f"{cedula[:3]}-{cedula[3:10]}-{cedula[10:]}", html)
		self.assertIn("12345678", html)
		self.assertIn("AFP - Fondo de Pensiones", html)
		self.assertIn("ISR - Retención Asalariados", html)
		self.assertIn("Neto a pagar", html)
		self.assertIn("Aportes del empleador", html)

	def test_planillas_sirla(self):
		"""DGT-3: el trabajador activo como ingreso (NI); DGT-4: el cambio de salario del mes (NC)."""
		from erpnext_rd.nomina_rd import sirla
		from erpnext_rd.tests.test_empleado import cedula_valida

		self._aislar()
		frappe.db.set_value(
			"Employee",
			self.empleado.name,
			{"rd_cedula": cedula_valida("0010000008"), "relieving_date": None, "rd_ocupacion_sirla": "2411"},
		)
		frappe.db.set_value("Company", EMPRESA, {"tax_id": "101000001", "rd_localidad_sirla": "0001"})
		f = next(f for f in sirla.obtener(EMPRESA, 2026, 1) if f["employee"] == self.empleado.name)
		self.assertEqual(
			(f["novedad"], f["salario"], f["localidad"], f["_en_txt"]), ("NI", 80_000, "0001", 1)
		)
		self.assertIn("turno", f["_avisos"])

		nombre, contenido = sirla.generar_txt(EMPRESA, 2026, 1)
		lineas = contenido.split("\r\n")[:-1]
		self.assertEqual(nombre, "DGT3_101000001_012026.txt")
		self.assertEqual(lineas[0], "ET300101000001012026")
		self.assertEqual(lineas[-1], "S" + str(len(lineas)).zfill(6))

		frappe.get_doc(
			{
				"doctype": "Salary Structure Assignment",
				"employee": self.empleado.name,
				"salary_structure": "_Test Estructura RD",
				"company": EMPRESA,
				"currency": "DOP",
				"from_date": "2026-10-05",
				"base": 90_000,
			}
		).submit()
		cambio = next(
			f for f in sirla.obtener(EMPRESA, 2026, 10, sirla.DGT4) if f["employee"] == self.empleado.name
		)
		self.assertEqual(
			(cambio["novedad"], str(cambio["fecha_cambio"]), cambio["salario"]), ("NC", "2026-10-05", 90_000)
		)

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

	def test_dependientes_adicionales_del_sfs(self):
		"""Per cápita + Fonamat por cada dependiente afiliado en el mes; no cambia el ISR."""
		self._aislar()
		empleado = frappe.get_doc("Employee", self.empleado.name)
		empleado.append(
			"rd_dependientes_adicionales", {"nombre": "Madre", "parentesco": "Madre", "desde": "2026-01-01"}
		)
		empleado.append(
			"rd_dependientes_adicionales",
			{"nombre": "Suegro", "parentesco": "Suegro", "desde": "2026-01-01", "hasta": "2026-08-31"},
		)
		empleado.save()

		recibo = self._recibo()
		deducciones = {f.abbr: f.amount for f in recibo.deductions}
		self.assertEqual(deducciones["SFS_DA"], 1938.18 + 32.24)
		self.assertEqual(deducciones["ISR"], 9900.94)
		self.assertAlmostEqual(recibo.net_pay, 90_000 - 2296 - 2432 - 9900.94 - 1970.42, places=2)

	def test_subsidios_sisalril_con_la_nomina(self):
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

		# 10 días de licencia: los 3 primeros no se subsidian; 60% del promedio (solo agosto: 80,000)
		enfermedad = frappe.get_doc(
			{
				"doctype": "Subsidio SISALRIL",
				"employee": self.empleado.name,
				"tipo": "Enfermedad común",
				"desde": "2026-09-10",
				"hasta": "2026-09-19",
			}
		).insert()
		self.assertEqual((enfermedad.salario_base, enfermedad.meses_cotizados), (80_000, 1))
		self.assertEqual((enfermedad.dias_subsidio, enfermedad.porcentaje), (7, 60))
		self.assertEqual(enfermedad.monto_estimado, 11_200)

		maternidad = frappe.get_doc(
			{
				"doctype": "Subsidio SISALRIL",
				"employee": self.empleado.name,
				"tipo": "Maternidad",
				"desde": "2026-09-01",
				"hasta": "2026-12-08",
			}
		).insert()
		self.assertEqual(maternidad.monto_estimado, 240_000)


class TestSubsidiosSISALRIL(IntegrationTestCase):
	def conf(self):
		return frappe._dict(
			salario_minimo_cotizable=23_223,
			subsidio_enfermedad_ambulatorio=60,
			subsidio_enfermedad_hospitalario=40,
			subsidio_dias_espera=3,
			subsidio_dias_maximo=182,
			subsidio_maternidad_meses=3,
			lactancia_un_salario=33,
			lactancia_dos_salarios=12,
			lactancia_tres_salarios=6,
		)

	def test_enfermedad_hospitalaria_con_tope(self):
		from erpnext_rd.nomina_rd import subsidios

		r = subsidios.calcular(
			subsidios.ENFERMEDAD, "2026-01-01", "2026-12-31", 30_000, subsidios.HOSPITALARIA, self.conf()
		)
		self.assertEqual((r.dias, r.porcentaje), (179, 40))
		self.assertEqual(r.monto, round(30_000 / 30 * 179 * 0.40, 2))
		corta = subsidios.calcular(
			subsidios.ENFERMEDAD, "2026-01-01", "2026-01-03", 30_000, None, self.conf()
		)
		self.assertEqual(corta.monto, 0)

	def test_lactancia_por_tramos(self):
		from erpnext_rd.nomina_rd import subsidios

		tramos = {
			20_000: 33,
			40_000: 12,
			60_000: 6,
			80_000: 0,
		}
		for salario, porcentaje in tramos.items():
			r = subsidios.calcular(subsidios.LACTANCIA, "2026-03-15", None, salario, conf=self.conf())
			self.assertEqual(r.porcentaje, porcentaje)
			self.assertEqual(r.monto, round(salario * porcentaje / 100, 2) * 12)
		self.assertEqual(str(r.hasta), "2027-03-14")
