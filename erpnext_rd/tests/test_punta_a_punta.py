"""Prueba de punta a punta: un mes completo de una empresa RD (ventas, notas de crédito, anulaciones,
compras con retenciones, pagos al exterior y nómina con su asiento) y la comprobación de que los
formatos y declaraciones cuadran con el libro mayor y entre sí, sin avisos."""

import unittest

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from erpnext_rd.dgii_reportes import declaraciones, formatos
from erpnext_rd.nomina_rd import hrms_instalado
from erpnext_rd.tests.test_empleado import cedula_valida

EMPRESA = "_Test Punta a Punta RD"
ABBR = "TPAP"
RNC_EMPRESA = "101543231"
RNC_TERCERO = "101003723"
MES = (2026, 8)
DESDE, HASTA = "2026-08-01", "2026-08-31"
SERVICIO, BIEN = "_Test Servicio PaP", "_Test Bien PaP"
CLIENTE, CONSUMIDOR = "_Test Cliente PaP", "_Test Consumidor PaP"
PROVEEDOR, INFORMAL, EXTERIOR = "_Test Proveedor PaP", "_Test Informal PaP", "_Test Exterior PaP"


def cuenta(numero: str) -> str:
	return frappe.db.get_value("Account", {"company": EMPRESA, "account_number": numero})


def movimiento(numero: str) -> float:
	"""Haber menos debe de la cuenta en el mes (sin documentos cancelados)."""
	(haber,) = frappe.db.sql(
		"""SELECT COALESCE(SUM(credit - debit), 0) FROM `tabGL Entry`
		WHERE company = %s AND account = %s AND is_cancelled = 0 AND posting_date BETWEEN %s AND %s""",
		(EMPRESA, cuenta(numero), DESDE, HASTA),
	)[0]
	return flt(haber, 2)


def ingresos() -> float:
	(haber,) = frappe.db.sql(
		"""SELECT COALESCE(SUM(gle.credit - gle.debit), 0) FROM `tabGL Entry` gle
		JOIN `tabAccount` a ON a.name = gle.account
		WHERE gle.company = %s AND a.root_type = 'Income' AND gle.is_cancelled = 0
			AND gle.posting_date BETWEEN %s AND %s""",
		(EMPRESA, DESDE, HASTA),
	)[0]
	return flt(haber, 2)


def con_impuestos(doc, doctype_plantilla: str, titulo: str):
	from erpnext.controllers.accounts_controller import get_taxes_and_charges

	doc.taxes_and_charges = frappe.db.get_value(doctype_plantilla, {"company": EMPRESA, "title": titulo})
	doc.set("taxes", get_taxes_and_charges(doctype_plantilla, doc.taxes_and_charges))
	return doc


def _crear(doctype: str, nombre: str, **campos):
	campo = {"Customer": "customer_name", "Supplier": "supplier_name", "Item": "item_code"}[doctype]
	if not frappe.db.exists(doctype, nombre):
		frappe.get_doc({"doctype": doctype, campo: nombre, **campos}).insert(ignore_permissions=True)


def _pagar(doctype: str, nombre: str, fecha: str, modo: str, retencion: float = 0):
	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	pe = get_payment_entry(doctype, nombre)
	pe.posting_date = pe.reference_date = fecha
	pe.mode_of_payment = modo
	pe.reference_no = f"REF-{nombre}"
	if retencion:
		pe.paid_amount = pe.received_amount = pe.paid_amount - retencion
		pe.append(
			"deductions",
			{
				"account": cuenta("110504"),
				"cost_center": frappe.get_cached_value("Company", EMPRESA, "cost_center"),
				"amount": retencion,
			},
		)
	pe.insert()
	pe.submit()
	return pe


class TestPuntaAPunta(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.preparar()

	@classmethod
	def preparar(cls):
		"""Registra el mes (también sirve para armar un sitio de demostración)."""
		frappe.db.set_single_value("Configuracion DGII", "aplicar_catalogo_cuentas", 1)
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": EMPRESA,
				"abbr": ABBR,
				"country": "Dominican Republic",
				"default_currency": "DOP",
				"tax_id": RNC_EMPRESA,
				"chart_of_accounts": "Standard",
				"create_chart_of_accounts_based_on": "Standard Template",
			}
		).insert()
		for tipo in ("B01", "B02", "B04", "B11", "B17"):
			frappe.get_doc(
				{
					"doctype": "Secuencia NCF",
					"company": EMPRESA,
					"tipo_comprobante": tipo,
					"desde": 1,
					"hasta": 100,
					"fecha_vencimiento": "2027-12-31",
				}
			).insert()

		uom = frappe.db.get_value("UOM", {"enabled": 1}) or "Nos"
		grupo = frappe.db.sql("SELECT name FROM `tabItem Group` WHERE IFNULL(parent_item_group, '') = ''")[0][
			0
		]
		for codigo, clase in ((SERVICIO, "Servicio"), (BIEN, "Bien")):
			_crear(
				"Item",
				codigo,
				item_name=codigo,
				item_group=grupo,
				stock_uom=uom,
				is_stock_item=0,
				rd_bien_o_servicio=clase,
			)
		_crear("Customer", CLIENTE, tax_id=RNC_TERCERO)
		_crear("Customer", CONSUMIDOR)
		_crear("Supplier", PROVEEDOR, country="Dominican Republic", tax_id=RNC_TERCERO)
		_crear(
			"Supplier",
			INFORMAL,
			country="Dominican Republic",
			supplier_type="Individual",
			tax_id=cedula_valida("0010000012"),
			rd_tipo_comprobante="B11",
		)
		_crear("Supplier", EXTERIOR, country="United States", supplier_type="Company", tax_id="98-7654321")

		# Ventas: crédito fiscal cobrado con retención, consumo de contado, una venta con nota de
		# crédito parcial y una anulada.
		cls.venta = cls._venta(CLIENTE, 20_000, "2026-08-04")
		_pagar("Sales Invoice", cls.venta.name, "2026-08-20", "Wire Transfer", retencion=1080)
		cls.consumo = cls._venta(CONSUMIDOR, 3_000, "2026-08-05")
		_pagar("Sales Invoice", cls.consumo.name, "2026-08-05", "Cash")
		cls.credito = cls._venta(CLIENTE, 5_000, "2026-08-10")
		cls.nota = cls._nota_credito(cls.credito, 1_000, "2026-08-12")
		cls.anulada = cls._venta(CLIENTE, 800, "2026-08-14")
		cls.anulada.rd_tipo_anulacion = "04 - Corrección de la información"
		cls.anulada.cancel()

		# Compras: proveedor formal con retención del 30% del ITBIS, persona física (B11) con
		# retención del ITBIS y del ISR, y un servicio del exterior (B17).
		cls.compra = cls._compra(
			PROVEEDOR,
			"2026-08-06",
			[(SERVICIO, 1_000, "6201"), (BIEN, 500, "6207")],
			"Servicios de Persona Jurídica - Retención 30% del ITBIS",
			rd_ncf="B0100000777",
			bill_date="2026-08-06",
		)
		_pagar("Purchase Invoice", cls.compra.name, "2026-08-18", "Wire Transfer")
		cls.informal = cls._compra(
			INFORMAL,
			"2026-08-08",
			[(SERVICIO, 5_000, "6201")],
			"Servicios de Persona Física - Retención 100% ITBIS y 15% ISR",
			rd_tipo_retencion_isr="02 - Honorarios por servicios",
		)
		_pagar("Purchase Invoice", cls.informal.name, "2026-08-08", "Cash")
		cls.exterior = cls._compra(
			EXTERIOR,
			"2026-08-15",
			[(SERVICIO, 2_000, "6212")],
			None,
			bill_no="INV-PAP-1",
			bill_date="2026-08-15",
			rd_tipo_bienes_servicios="02 - Gastos por trabajos, suministros y servicios",
			rd_tipo_servicio_exterior="02 - Gastos por trabajos, suministros y servicios",
			rd_detalle_servicio_exterior="21 - Honorarios por servicios profesionales (personas morales)",
		)

		cls.nomina = cls._nomina() if hrms_instalado() else None

	# ------------------------------------------------------------------ datos

	@staticmethod
	def _venta(cliente, monto, fecha):
		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": EMPRESA,
				"customer": cliente,
				"set_posting_time": 1,
				"posting_date": fecha,
				"due_date": fecha,
				"items": [{"item_code": SERVICIO, "qty": 1, "rate": monto}],
			}
		)
		con_impuestos(si, "Sales Taxes and Charges Template", "ITBIS 18%")
		si.insert()
		si.submit()
		return si

	@staticmethod
	def _nota_credito(si, monto, fecha):
		from erpnext.accounts.doctype.sales_invoice.sales_invoice import make_sales_return

		nota = make_sales_return(si.name)
		nota.set_posting_time = 1
		nota.posting_date = nota.due_date = fecha
		nota.items[0].rate = monto
		nota.calculate_taxes_and_totals()
		nota.insert()
		nota.submit()
		return nota

	@staticmethod
	def _compra(proveedor, fecha, lineas, plantilla, **campos):
		pi = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": EMPRESA,
				"supplier": proveedor,
				"set_posting_time": 1,
				"posting_date": fecha,
				"items": [
					{"item_code": item, "qty": 1, "rate": monto, "expense_account": cuenta(gasto)}
					for item, monto, gasto in lineas
				],
				**campos,
			}
		)
		if plantilla:
			con_impuestos(pi, "Purchase Taxes and Charges Template", plantilla)
		pi.insert()
		pi.submit()
		return pi

	@staticmethod
	def _nomina():
		"""Dos empleados con cédula, nómina de agosto por *Payroll Entry* (recibos y asiento)."""
		from erpnext_rd.nomina_rd import regalia, salario, vacaciones

		salario.crear_componentes()
		vacaciones.crear_componente_y_tipo()
		regalia.crear_componente()

		lista = frappe.get_doc(
			{
				"doctype": "Holiday List",
				"holiday_list_name": "_Test Feriados PaP",
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

		componente = "_Test Sueldo PaP"
		if not frappe.db.exists("Salary Component", componente):
			frappe.get_doc(
				{
					"doctype": "Salary Component",
					"salary_component": componente,
					"salary_component_abbr": "SUELDO_PAP",
					"type": "Earning",
					"is_tax_applicable": 1,
					"depends_on_payment_days": 0,
					"rd_cotiza_tss": 1,
					"accounts": [{"company": EMPRESA, "account": cuenta("6101")}],
				}
			).insert()
		estructura = frappe.get_doc(
			{
				"doctype": "Salary Structure",
				"name": "_Test Estructura PaP",
				"company": EMPRESA,
				"currency": "DOP",
				"payroll_frequency": "Monthly",
				"earnings": [
					{"salary_component": componente, "amount_based_on_formula": 1, "formula": "base"}
				],
			}
		).insert()
		estructura.submit()

		genero = (
			frappe.db.get_value("Gender", {})
			or frappe.get_doc({"doctype": "Gender", "gender": "Otro"}).insert().name
		)
		for i, (nombre, base) in enumerate((("Ana", 45_000), ("Luis", 150_000)), start=1):
			emp = frappe.get_doc(
				{
					"doctype": "Employee",
					"first_name": f"_Test {nombre}",
					"last_name": "Punta",
					"gender": genero,
					"date_of_birth": "1990-01-01",
					"date_of_joining": "2025-01-01",
					"company": EMPRESA,
					"status": "Active",
					"rd_cedula": cedula_valida(f"00200000{i}0"),
				}
			).insert()
			frappe.get_doc(
				{
					"doctype": "Salary Structure Assignment",
					"employee": emp.name,
					"salary_structure": estructura.name,
					"company": EMPRESA,
					"currency": "DOP",
					"from_date": "2026-01-01",
					"base": base,
				}
			).submit()

		pe = frappe.new_doc("Payroll Entry")
		pe.update(
			{
				"company": EMPRESA,
				"posting_date": HASTA,
				"start_date": DESDE,
				"end_date": HASTA,
				"payroll_frequency": "Monthly",
				"currency": "DOP",
				"exchange_rate": 1,
				"payroll_payable_account": cuenta("210401"),
				"cost_center": frappe.get_cached_value("Company", EMPRESA, "cost_center"),
				"payment_account": frappe.db.get_value(
					"Account", {"company": EMPRESA, "account_type": "Cash", "is_group": 0}
				),
			}
		)
		pe.fill_employee_details()
		pe.insert()
		pe.submit()
		pe.submit_salary_slips()
		return pe

	# ------------------------------------------------------------------ libro mayor

	def test_itbis_de_ventas_cuadra_con_el_mayor(self):
		it1 = declaraciones.resumen_it1(EMPRESA, *MES)
		# 18% de 20,000 + 3,000 + 5,000 - 1,000 de la nota; la anulada no cuenta
		self.assertAlmostEqual(it1.itbis_neto_ventas, 4_860)
		self.assertAlmostEqual(movimiento("210301"), it1.itbis_neto_ventas)
		self.assertAlmostEqual(ingresos(), it1.total_operaciones)
		self.assertAlmostEqual(it1.total_operaciones, 27_000)

	def test_itbis_de_compras_cuadra_con_el_mayor(self):
		it1 = declaraciones.resumen_it1(EMPRESA, *MES)
		self.assertAlmostEqual(it1.itbis_compras, 270 + 900)
		self.assertAlmostEqual(-movimiento("110501"), it1.itbis_compras)

	def test_retenciones_cuadran_con_el_mayor(self):
		it1 = declaraciones.resumen_it1(EMPRESA, *MES)
		ir17 = declaraciones.resumen_ir17(EMPRESA, *MES)
		self.assertAlmostEqual(it1.itbis_retenido_a_terceros, 81 + 900)
		self.assertAlmostEqual(movimiento("210302"), it1.itbis_retenido_a_terceros)
		self.assertAlmostEqual(ir17.total_isr, 750)
		self.assertAlmostEqual(movimiento("210303"), ir17.total_isr)
		self.assertAlmostEqual(it1.itbis_retenido_por_terceros, 1_080)
		self.assertAlmostEqual(-movimiento("110504"), it1.itbis_retenido_por_terceros)
		self.assertAlmostEqual(
			it1.total_a_pagar,
			it1.itbis_neto_ventas - it1.itbis_deducible - 1_080 + it1.itbis_retenido_a_terceros,
		)

	# ------------------------------------------------------------------ formatos

	def test_formatos_sin_avisos(self):
		"""Con datos completos ningún registro del mes lleva observaciones."""
		for formato in ("606", "607", "608", "609"):
			for fila in formatos.obtener(formato, EMPRESA, *MES):
				self.assertFalse(
					fila.get("_avisos"), f"{formato} {fila.get('_documento')}: {fila.get('_avisos')}"
				)

	def test_607_y_608(self):
		filas = {f["_documento"]: f for f in formatos.obtener("607", EMPRESA, *MES)}
		self.assertNotIn(self.anulada.name, filas)
		nota = filas[self.nota.name]
		self.assertTrue(nota["ncf"].startswith("B04"))
		self.assertEqual(nota["ncf_modificado"], self.credito.rd_ncf)
		self.assertFalse(filas[self.consumo.name]["_en_txt"])  # consumo < RD$250,000: resumen

		_nombre, contenido = formatos.generar_txt("607", EMPRESA, *MES)
		lineas = contenido.split("\r\n")[:-1]
		self.assertEqual(lineas[0], f"607|{RNC_EMPRESA}|202608|3")  # venta, crédito y su nota
		self.assertNotIn(self.consumo.rd_ncf, contenido)

		anuladas = formatos.obtener("608", EMPRESA, *frappe.utils.getdate().timetuple()[:2])
		self.assertIn(self.anulada.rd_ncf, [f["ncf"] for f in anuladas])

	def test_606_y_609(self):
		filas = {f["_documento"]: f for f in formatos.obtener("606", EMPRESA, *MES)}
		informal = filas[self.informal.name]
		self.assertTrue(informal["ncf"].startswith("B11"))
		self.assertEqual(informal["tipo_id"], "2")
		self.assertEqual(
			(informal["itbis_retenido"], informal["monto_retencion_renta"], informal["fecha_pago"]),
			(900, 750, "20260808"),
		)
		self.assertEqual(filas[self.compra.name]["itbis_retenido"], 81)

		_nombre, contenido = formatos.generar_txt("606", EMPRESA, *MES)
		self.assertTrue(contenido.startswith(f"606|{RNC_EMPRESA}|202608|3\r\n"))
		(exterior,) = formatos.obtener("609", EMPRESA, *MES)
		self.assertEqual((exterior["numero_documento"], exterior["monto_facturado"]), ("INV-PAP-1", 2_000))

	def test_panel_cuadra_con_las_declaraciones(self):
		from erpnext_rd.rd_compliance import panel

		r = panel.resumen(EMPRESA, *MES)
		it1 = declaraciones.resumen_it1(EMPRESA, *MES)
		self.assertAlmostEqual(r["it1"]["total_a_pagar"], it1.total_a_pagar)
		self.assertEqual(r["avisos"]["total"], 0, r["avisos"]["lista"])

	# ------------------------------------------------------------------ nómina

	def test_ncf_de_venta_solo_de_la_secuencia(self):
		"""Un NCF enviado por la API (en borrador o al aprobar) se cambia por el de la secuencia."""
		inventado = "B0100000099"
		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": EMPRESA,
				"customer": CLIENTE,
				"set_posting_time": 1,
				"posting_date": "2026-09-03",
				"due_date": "2026-09-03",
				"rd_ncf": inventado,
				"items": [{"item_code": SERVICIO, "qty": 1, "rate": 1_000}],
			}
		)
		con_impuestos(si, "Sales Taxes and Charges Template", "ITBIS 18%")
		si.insert()
		self.assertIsNone(si.rd_ncf)

		si.rd_ncf = inventado
		si.submit()
		self.assertNotEqual(si.rd_ncf, inventado)
		self.assertTrue(si.rd_ncf.startswith("B01"))
		self.assertTrue(si.rd_secuencia_ncf)

	def test_utilidad_contable_solo_para_quien_prepara_la_bonificacion(self):
		from erpnext_rd.nomina_rd.bonificacion import utilidad_contable

		# Rol interno que puede leer la empresa pero no prepara bonificaciones
		usuario = "vendedor.punta@example.com"
		if not frappe.db.exists("User", usuario):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": usuario,
					"first_name": "Vendedor",
					"send_welcome_email": 0,
					"roles": [{"role": "Sales User"}],
				}
			).insert(ignore_permissions=True)
		frappe.set_user(usuario)
		self.assertTrue(frappe.has_permission("Company", doc=EMPRESA))
		frappe.set_user("Administrator")

		frappe.set_user(usuario)
		try:
			with self.assertRaises(frappe.PermissionError):
				utilidad_contable(EMPRESA, "2026-01-01", "2026-12-31")
		finally:
			frappe.set_user("Administrator")
		self.assertIsInstance(utilidad_contable(EMPRESA, "2026-01-01", "2026-12-31"), float)

	def test_indice_de_secuencia_ncf(self):
		indices = frappe.db.sql("SHOW INDEX FROM `tabSecuencia NCF`", as_dict=True)
		columnas = {(i.Key_name, i.Column_name) for i in indices}
		self.assertTrue(
			any(c == "company" and (k, "tipo_comprobante") in columnas for k, c in columnas),
			"falta el índice company + tipo_comprobante",
		)

	def _requiere_nomina(self):
		if not self.nomina:
			raise unittest.SkipTest("sin Frappe HR")

	def test_nomina_cuadra_con_el_mayor(self):
		self._requiere_nomina()
		recibos = frappe.get_all(
			"Salary Slip", {"payroll_entry": self.nomina.name, "docstatus": 1}, pluck="name"
		)
		self.assertEqual(len(recibos), 2)

		def total(tabla, abbr=None):
			filtros = {"parent": ["in", recibos], "parentfield": tabla}
			if abbr:
				filtros["abbr"] = ["in", abbr]
			return flt(sum(frappe.get_all("Salary Detail", filtros, pluck="amount")), 2)

		self.assertAlmostEqual(movimiento("210304"), total("deductions", ["ISR"]))
		self.assertAlmostEqual(
			movimiento("210402"),
			total("deductions", ["AFP", "SFS"])
			+ total("employer_contributions", ["AFP_ER", "SFS_ER", "SRL"]),
		)
		self.assertAlmostEqual(movimiento("210403"), total("employer_contributions", ["INFOTEP"]))
		netos = sum(frappe.get_all("Salary Slip", {"name": ["in", recibos]}, pluck="net_pay"))
		self.assertAlmostEqual(movimiento("210401"), flt(netos, 2))

	def test_tss_e_ir3_sin_avisos(self):
		self._requiere_nomina()
		from erpnext_rd.nomina_rd import ir3, tss

		filas = [f for f in tss.obtener(EMPRESA, *MES) if f["con_recibo"]]
		self.assertEqual(len(filas), 2)
		for f in filas:
			self.assertEqual((f["_en_txt"], f["_avisos"]), (1, ""), f["employee_name"])
		# El tope de la AFP es 20 salarios mínimos cotizables; el sueldo de 150,000 no lo pasa
		self.assertEqual(sorted(f["salario_ss"] for f in filas), [45_000, 150_000])

		retenido = 0
		for f in ir3.obtener(EMPRESA, *MES):
			self.assertEqual((f["diferencia"], f["_avisos"]), (0, ""), f["employee_name"])
			retenido += f["isr_retenido"]
		self.assertAlmostEqual(movimiento("210304"), flt(retenido, 2))

		_nombre, contenido = tss.generar_txt(EMPRESA, *MES)
		self.assertEqual(len(contenido.split("\r\n")[:-1]), 4)  # encabezado, 2 detalles, sumario
