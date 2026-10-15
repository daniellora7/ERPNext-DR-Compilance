"""Reportes DGII 606 / 607 / 608 / 609 con facturas reales en una empresa de prueba (rollback)."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import getdate, nowdate

from erpnext_rd.dgii_reportes import datos, declaraciones, formatos

EMPRESA = "_Test Reportes RD"
ABBR = "TRRD"
RNC_EMPRESA = "101543231"
RNC_TERCERO = "101003723"
SEPTIEMBRE = (2026, 9)
OCTUBRE = (2026, 10)


def cuenta(numero: str) -> str:
	return frappe.db.get_value("Account", {"company": EMPRESA, "account_number": numero})


def plantilla(doctype: str, titulo: str) -> str:
	return frappe.db.get_value(doctype, {"company": EMPRESA, "title": titulo})


def con_impuestos(doc, doctype_plantilla: str, titulo: str):
	from erpnext.controllers.accounts_controller import get_taxes_and_charges

	doc.taxes_and_charges = plantilla(doctype_plantilla, titulo)
	doc.set("taxes", get_taxes_and_charges(doctype_plantilla, doc.taxes_and_charges))
	return doc


def _crear(doc: dict):
	if not frappe.db.exists(doc["doctype"], doc.get("name") or doc.get(_campo_nombre(doc["doctype"]))):
		return frappe.get_doc(doc).insert(ignore_permissions=True)


def _campo_nombre(doctype: str) -> str:
	return {"Customer": "customer_name", "Supplier": "supplier_name", "Item": "item_code"}.get(
		doctype, "name"
	)


class TestReportesDGII(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
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

		for tipo in ("B01", "B02", "B04", "B17", "E31", "E41"):
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
		for codigo, clase in (("_Test Servicio DGII", "Servicio"), ("_Test Bien DGII", "Bien")):
			_crear(
				{
					"doctype": "Item",
					"item_code": codigo,
					"item_name": codigo,
					"item_group": grupo,
					"stock_uom": uom,
					"is_stock_item": 0,
					"rd_bien_o_servicio": clase,
				}
			)

		_crear(
			{
				"doctype": "Supplier",
				"supplier_name": "_Test Proveedor RD",
				"country": "Dominican Republic",
				"tax_id": RNC_TERCERO,
			}
		)
		_crear(
			{
				"doctype": "Supplier",
				"supplier_name": "_Test Proveedor Exterior",
				"country": "United States",
				"supplier_type": "Company",
				"tax_id": "98-7654321",
			}
		)
		_crear({"doctype": "Customer", "customer_name": "_Test Cliente RD", "tax_id": RNC_TERCERO})
		_crear({"doctype": "Customer", "customer_name": "_Test Consumidor RD"})

		cls.compra = cls._compra()
		cls.pago_compra = cls._pagar_compra(cls.compra)
		cls.venta = cls._venta("_Test Cliente RD", 10000, "2026-09-12")
		cls.cobro = cls._cobrar_con_retencion(cls.venta)
		cls.consumo = cls._venta("_Test Consumidor RD", 1000, "2026-09-15")
		cls.anulada = cls._venta("_Test Cliente RD", 500, "2026-09-16")
		cls.anulada.rd_tipo_anulacion = "04 - Corrección de la información"
		cls.anulada.cancel()
		cls.exterior = cls._compra_exterior()

	# ------------------------------------------------------------------ e-CF

	def test_ecf_de_facturas_reales(self):
		"""El e-CF de una venta E31 y de una compra E41 reales se arma, se firma y cumple el XSD oficial."""
		from erpnext_rd.ecf import datos as d
		from erpnext_rd.ecf import esquemas, firma
		from erpnext_rd.tests.test_ecf import certificado_de_prueba

		frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": EMPRESA,
				"address_line1": "Av. Winston Churchill 1",
				"city": "Santo Domingo",
				"country": "Dominican Republic",
				"is_your_company_address": 1,
				"links": [{"link_doctype": "Company", "link_name": EMPRESA}],
			}
		).insert()
		llave, cert = firma.cargar_certificado(certificado_de_prueba(), "prueba")

		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": EMPRESA,
				"customer": "_Test Cliente RD",
				"set_posting_time": 1,
				"posting_date": "2026-10-05",
				"due_date": "2026-11-04",
				"rd_tipo_comprobante": "E31",
				"items": [{"item_code": "_Test Servicio DGII", "qty": 2, "rate": 1250}],
			}
		)
		con_impuestos(si, "Sales Taxes and Charges Template", "ITBIS 18%")
		si.insert()
		si.submit()
		datos_venta = d.datos_ecf(si)
		firmado = firma.firmar(esquemas.construir(31, datos_venta), llave, cert)
		self.assertEqual(esquemas.errores(31, firmado), [])
		totales = datos_venta["Encabezado"]["Totales"]
		self.assertEqual(
			(totales["MontoGravadoI1"], totales["TotalITBIS1"], totales["MontoTotal"]),
			("2500.00", "450.00", "2950.00"),
		)
		self.assertEqual(datos_venta["Encabezado"]["IdDoc"]["TipoPago"], d.CREDITO)
		linea = datos_venta["DetallesItems"]["Item"][0]
		self.assertEqual((linea["IndicadorFacturacion"], linea["IndicadorBienoServicio"]), (1, 2))
		self.assertEqual(datos_venta["Encabezado"]["Emisor"]["DireccionEmisor"], "Av. Winston Churchill 1")

		pi = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": EMPRESA,
				"supplier": "_Test Proveedor RD",
				"set_posting_time": 1,
				"posting_date": "2026-10-06",
				"rd_tipo_comprobante": "E41",
				"items": [
					{
						"item_code": "_Test Servicio DGII",
						"qty": 1,
						"rate": 1000,
						"expense_account": cuenta("6201"),
					}
				],
			}
		)
		con_impuestos(
			pi,
			"Purchase Taxes and Charges Template",
			"Servicios de Persona Jurídica - Retención 30% del ITBIS",
		)
		pi.insert()
		pi.submit()
		datos_compra = d.datos_ecf(pi)
		firmado = firma.firmar(esquemas.construir(41, datos_compra), llave, cert)
		self.assertEqual(esquemas.errores(41, firmado), [])
		self.assertEqual(datos_compra["Encabezado"]["Totales"]["TotalITBISRetenido"], "54.00")

	# ------------------------------------------------------------------ datos

	@staticmethod
	def _compra():
		pi = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": EMPRESA,
				"supplier": "_Test Proveedor RD",
				"set_posting_time": 1,
				"posting_date": "2026-09-10",
				"bill_date": "2026-09-09",
				"rd_ncf": "B0100000123",
				"items": [
					{
						"item_code": "_Test Servicio DGII",
						"qty": 1,
						"rate": 1000,
						"expense_account": cuenta("6201"),
					},
					{
						"item_code": "_Test Bien DGII",
						"qty": 1,
						"rate": 500,
						"expense_account": cuenta("6207"),
					},
				],
			}
		)
		con_impuestos(
			pi,
			"Purchase Taxes and Charges Template",
			"Servicios de Persona Jurídica - Retención 30% del ITBIS",
		)
		pi.insert()
		pi.submit()
		return pi

	@staticmethod
	def _pagar_compra(pi):
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		pe = get_payment_entry("Purchase Invoice", pi.name)
		pe.posting_date = "2026-09-20"
		pe.mode_of_payment = "Wire Transfer"
		pe.reference_no = "TRF-1"
		pe.reference_date = "2026-09-20"
		pe.insert()
		pe.submit()
		return pe

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
				"items": [{"item_code": "_Test Servicio DGII", "qty": 1, "rate": monto}],
			}
		)
		con_impuestos(si, "Sales Taxes and Charges Template", "ITBIS 18%")
		si.insert()
		si.submit()
		return si

	@staticmethod
	def _cobrar_con_retencion(si):
		"""El cliente retiene el 30% del ITBIS y paga el resto por transferencia."""
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		retencion = si.base_total_taxes_and_charges * 0.30
		pe = get_payment_entry("Sales Invoice", si.name)
		pe.posting_date = "2026-09-25"
		pe.mode_of_payment = "Wire Transfer"
		pe.reference_no = "TRF-2"
		pe.reference_date = "2026-09-25"
		pe.paid_amount = pe.received_amount = si.base_grand_total - retencion
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

	@staticmethod
	def _compra_exterior():
		pi = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": EMPRESA,
				"supplier": "_Test Proveedor Exterior",
				"set_posting_time": 1,
				"posting_date": "2026-09-18",
				"bill_no": "INV-US-77",
				"bill_date": "2026-09-17",
				"rd_tipo_bienes_servicios": "02 - Gastos por trabajos, suministros y servicios",
				"rd_tipo_servicio_exterior": "02 - Gastos por trabajos, suministros y servicios",
				"rd_detalle_servicio_exterior": "21 - Honorarios por servicios profesionales (personas morales)",
				"items": [
					{
						"item_code": "_Test Servicio DGII",
						"qty": 1,
						"rate": 2000,
						"expense_account": cuenta("6212"),
					}
				],
			}
		)
		pi.insert()
		pi.submit()
		return pi

	# ------------------------------------------------------------------ 606

	def test_606_compra_con_retencion_pagada(self):
		filas = {f["_documento"]: f for f in datos.datos_606(EMPRESA, *SEPTIEMBRE)}
		fila = filas[self.compra.name]

		self.assertEqual(fila["rnc_cedula"], RNC_TERCERO)
		self.assertEqual(fila["tipo_id"], "1")
		self.assertEqual(fila["tipo_bienes_servicios"], "02")  # sugerido por la cuenta 6201
		self.assertEqual(fila["ncf"], "B0100000123")
		self.assertEqual(fila["fecha_comprobante"], "20260909")
		self.assertEqual(fila["fecha_pago"], "20260920")
		self.assertEqual(fila["monto_servicios"], 1000)
		self.assertEqual(fila["monto_bienes"], 500)
		self.assertEqual(fila["total_monto_facturado"], 1500)
		self.assertEqual(fila["itbis_facturado"], 270)
		self.assertEqual(fila["itbis_retenido"], 81)
		self.assertEqual(fila["itbis_adelantar"], 270)
		self.assertEqual(fila["forma_pago"], "02")
		self.assertEqual(fila["_avisos"], "")

	def test_606_pago_exterior_usa_rnc_de_la_empresa(self):
		filas = {f["_documento"]: f for f in datos.datos_606(EMPRESA, *SEPTIEMBRE)}
		fila = filas[self.exterior.name]
		self.assertTrue(fila["ncf"].startswith("B17"))
		self.assertEqual(fila["rnc_cedula"], RNC_EMPRESA)
		self.assertEqual(fila["forma_pago"], "04")  # sin pagar: compra a crédito

	# ------------------------------------------------------------------ 607

	def test_607_venta_con_retencion_del_cliente(self):
		filas = {f["_documento"]: f for f in datos.datos_607(EMPRESA, *SEPTIEMBRE)}
		fila = filas[self.venta.name]

		self.assertEqual(fila["ncf"], self.venta.rd_ncf)
		self.assertTrue(fila["ncf"].startswith("B01"))
		self.assertEqual(fila["tipo_id"], "1")
		self.assertEqual(fila["tipo_ingreso"], "01")  # sugerido por la cuenta 4101
		self.assertEqual(fila["monto_facturado"], 10000)
		self.assertEqual(fila["itbis_facturado"], 1800)
		self.assertAlmostEqual(fila["itbis_retenido_terceros"], 540)
		self.assertEqual(fila["fecha_retencion"], "20260925")
		self.assertAlmostEqual(fila["cheque_transferencia"], 11800)
		self.assertAlmostEqual(fila["venta_credito"], 0)
		self.assertTrue(fila["_en_txt"])

	def test_607_consumo_menor_al_umbral_va_al_resumen(self):
		filas = datos.datos_607(EMPRESA, *SEPTIEMBRE)
		fila = next(f for f in filas if f["_documento"] == self.consumo.name)
		self.assertTrue(fila["ncf"].startswith("B02"))
		self.assertFalse(fila["_en_txt"])
		self.assertEqual(fila["venta_credito"], 1180)

		resumen = datos.resumen_consumo(filas)
		self.assertEqual(resumen["cantidad"], 1)
		self.assertEqual(resumen["monto_facturado"], 1000)
		self.assertEqual(resumen["itbis_facturado"], 180)

	def test_607_excluye_anuladas(self):
		documentos = {f["_documento"] for f in datos.datos_607(EMPRESA, *SEPTIEMBRE)}
		self.assertNotIn(self.anulada.name, documentos)

	# ------------------------------------------------------------------ 608

	def test_608_factura_anulada(self):
		hoy = getdate(nowdate())
		filas = datos.datos_608(EMPRESA, hoy.year, hoy.month)
		fila = next(f for f in filas if f["_documento"] == self.anulada.name)
		self.assertEqual(fila["ncf"], self.anulada.rd_ncf)
		self.assertEqual(fila["fecha_comprobante"], "20260916")
		self.assertEqual(fila["tipo_anulacion"], "04")

	# ------------------------------------------------------------------ 609

	def test_609_pago_al_exterior(self):
		filas = datos.datos_609(EMPRESA, *SEPTIEMBRE)
		self.assertEqual(len(filas), 1)
		fila = filas[0]
		self.assertEqual(fila["razon_social"], "_Test Proveedor Exterior")
		self.assertEqual(fila["tipo_id_tributaria"], "2")
		self.assertEqual(fila["id_tributaria"], "98-7654321")
		self.assertEqual(fila["pais_destino"], "840")
		self.assertEqual(fila["tipo_servicio"], "02")
		self.assertEqual(fila["detalle_servicio"], "21")
		self.assertEqual(fila["parte_relacionada"], "0")
		self.assertEqual(fila["numero_documento"], "INV-US-77")
		self.assertEqual(fila["fecha_documento"], "20260917")
		self.assertEqual(fila["monto_facturado"], 2000)

	# ------------------------------------------------------------------ TXT

	def test_txt_606(self):
		nombre, contenido = formatos.generar_txt("606", EMPRESA, *SEPTIEMBRE)
		self.assertEqual(nombre, f"DGII_F_606_{RNC_EMPRESA}_202609.TXT")
		lineas = contenido.split("\r\n")[:-1]
		self.assertEqual(lineas[0], f"606|{RNC_EMPRESA}|202609|2")
		self.assertEqual(len(lineas), 3)
		for linea in lineas[1:]:
			self.assertEqual(len(linea.split("|")), 23)
		compra = next(l for l in lineas[1:] if "B0100000123" in l)
		self.assertEqual(
			compra,
			f"{RNC_TERCERO}|1|02|B0100000123||20260909|20260920|1000.00|500.00|1500.00|270.00|81.00|0.00|0.00|270.00|"
			"||0.00||0.00|0.00|0.00|02",
		)

	def test_txt_607_sin_consumo_menor(self):
		_nombre, contenido = formatos.generar_txt("607", EMPRESA, *SEPTIEMBRE)
		lineas = contenido.split("\r\n")[:-1]
		self.assertEqual(lineas[0], f"607|{RNC_EMPRESA}|202609|1")
		self.assertEqual(len(lineas[1].split("|")), 23)
		self.assertNotIn(self.consumo.rd_ncf, contenido)

	def test_txt_sin_registros(self):
		with self.assertRaises(frappe.ValidationError):
			formatos.generar_txt("608", EMPRESA, 2026, 1)

	def test_empresa_de_otro_pais(self):
		with self.assertRaises(frappe.ValidationError):
			formatos.obtener("606", "Dynamics Plastics MX inexistente", 2026, 9)

	# ------------------------------------------------------------------ IT-1 / IR-17

	def test_it1_liquidacion(self):
		r = declaraciones.resumen_it1(EMPRESA, *SEPTIEMBRE)
		self.assertEqual(r.ventas_brutas, 11000)  # crédito fiscal + consumo, sin la anulada
		self.assertEqual(r.notas_credito, 0)
		self.assertAlmostEqual(r.gravadas[18.0], 11000)
		self.assertAlmostEqual(r.exentas, 0)
		self.assertEqual(r.itbis_facturado, 1980)
		self.assertAlmostEqual(r.formas["cheque_transferencia"], 11800)
		self.assertAlmostEqual(r.formas["venta_credito"], 1180)
		self.assertEqual(r.itbis_compras, 270)  # el pago al exterior (B17) no lleva ITBIS
		self.assertEqual(r.itbis_deducible, 270)
		self.assertAlmostEqual(r.itbis_retenido_por_terceros, 540)
		self.assertAlmostEqual(r.itbis_a_pagar, 1980 - 270 - 540)
		self.assertAlmostEqual(r.itbis_retenido_a_terceros, 81)
		self.assertAlmostEqual(r.total_a_pagar, 1170 + 81)
		self.assertEqual(str(r.vence), "2026-10-20")

	def test_it1_saldo_a_favor(self):
		r = declaraciones.resumen_it1(EMPRESA, *SEPTIEMBRE, saldo_favor_anterior=2000)
		self.assertEqual(r.itbis_a_pagar, 0)
		self.assertAlmostEqual(r.nuevo_saldo_favor, 2000 - 1170)
		self.assertAlmostEqual(r.total_a_pagar, 81)  # la retención a terceros se paga igual

	def test_ir17_retencion_isr_pagada(self):
		from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

		self.assertEqual(declaraciones.resumen_ir17(EMPRESA, *OCTUBRE).total_isr, 0)

		pi = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": EMPRESA,
				"supplier": "_Test Proveedor RD",
				"set_posting_time": 1,
				"posting_date": "2026-10-05",
				"bill_date": "2026-10-05",
				"rd_ncf": "B0100000456",
				"rd_tipo_retencion_isr": "02 - Honorarios por servicios",
				"items": [
					{
						"item_code": "_Test Servicio DGII",
						"qty": 1,
						"rate": 5000,
						"expense_account": cuenta("6201"),
					}
				],
			}
		)
		con_impuestos(
			pi,
			"Purchase Taxes and Charges Template",
			"Servicios de Persona Física - Retención 100% ITBIS y 15% ISR",
		)
		pi.insert()
		pi.submit()

		# Sin pagar todavía: la retención no se declara
		self.assertEqual(declaraciones.resumen_ir17(EMPRESA, *OCTUBRE).total_isr, 0)

		pe = get_payment_entry("Purchase Invoice", pi.name)
		pe.posting_date = "2026-10-08"
		pe.mode_of_payment = "Wire Transfer"
		pe.reference_no = "TRF-3"
		pe.reference_date = "2026-10-08"
		pe.insert()
		pe.submit()

		r = declaraciones.resumen_ir17(EMPRESA, *OCTUBRE)
		self.assertAlmostEqual(r.total_isr, 750)
		self.assertEqual(len(r.grupos), 1)
		self.assertEqual(r.grupos[0].concepto, "02 - Honorarios por servicios")
		self.assertEqual(r.grupos[0].base, 5000)
		self.assertEqual(str(r.vence), "2026-11-10")

		filas = declaraciones.filas_ir17(r)
		self.assertEqual(filas[1]["documento"], pi.name)
		self.assertEqual(filas[1]["tasa"], 15)

		it1 = declaraciones.resumen_it1(EMPRESA, *OCTUBRE)
		self.assertAlmostEqual(it1.itbis_retenido_a_terceros, 900)  # 100% del ITBIS de 5,000

	def test_ncf_duplicado_se_marca(self):
		filas = [
			{"rnc_cedula": RNC_TERCERO, "ncf": "B0100000001", "_documento": "A", "_avisos": ""},
			{"rnc_cedula": RNC_TERCERO, "ncf": "B0100000001", "_documento": "B", "_avisos": "otro"},
			{"rnc_cedula": RNC_EMPRESA, "ncf": "B0100000001", "_documento": "C", "_avisos": ""},
		]
		formatos.marcar_duplicados("606", filas)
		self.assertIn("NCF duplicado", filas[0]["_avisos"])
		self.assertTrue(filas[1]["_avisos"].startswith("otro; NCF duplicado"))
		self.assertEqual(filas[2]["_avisos"], "")  # mismo NCF de otro proveedor: válido

	# ------------------------------------------------------------------ Panel RD Compliance

	def test_panel_cuadra_con_los_reportes(self):
		from erpnext_rd.rd_compliance import panel

		r = panel.resumen(EMPRESA, *SEPTIEMBRE)
		por_formato = {f["formato"]: f for f in r["formatos"]}
		it1 = declaraciones.resumen_it1(EMPRESA, *SEPTIEMBRE)

		for formato, f in por_formato.items():
			filas = formatos.obtener(formato, EMPRESA, *SEPTIEMBRE)
			self.assertEqual(f["registros"], sum(1 for x in filas if x.get("_en_txt", True)))
			self.assertEqual(str(f["vence"]), "2026-10-15")
		self.assertIsNone(por_formato["608"]["monto"])
		self.assertAlmostEqual(r["it1"]["total_a_pagar"], it1.total_a_pagar)
		self.assertAlmostEqual(r["it1"]["itbis_deducible"], it1.itbis_deducible)
		self.assertEqual(r["avisos"]["total"], len(r["avisos"]["lista"]))

	def test_panel_solo_empresas_rd(self):
		from erpnext_rd.rd_compliance import panel

		self.assertIn(EMPRESA, [e.name for e in panel.contexto()["empresas"]])
		with self.assertRaises(frappe.ValidationError):
			panel.resumen("Empresa inexistente", *SEPTIEMBRE)
