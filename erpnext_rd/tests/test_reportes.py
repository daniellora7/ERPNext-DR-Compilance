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

		# Emisión completa con el emisor configurado y la DGII simulada
		from unittest.mock import patch

		from erpnext_rd.ecf import emision
		from erpnext_rd.tests.test_ecf import SesionDGII

		archivo = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "certificado.p12",
				"content": certificado_de_prueba(),
				"is_private": 1,
			}
		).insert()
		frappe.get_doc(
			{
				"doctype": "Emisor ECF",
				"company": EMPRESA,
				"habilitado": 1,
				"certificado": archivo.file_url,
				"clave_certificado": "prueba",
			}
		).insert()
		self.assertEqual(frappe.db.get_value("Emisor ECF", EMPRESA, "titular"), "EMPRESA DE PRUEBA SRL")
		frappe.cache.delete_value(f"erpnext_rd:ecf_token:TesteCF:{RNC_EMPRESA}")
		with patch("erpnext_rd.ecf.cliente.requests.Session", SesionDGII):
			nombre = emision.emitir("Sales Invoice", si.name)
			envio = frappe.get_doc("Envio ECF", nombre)
			self.assertEqual((envio.estado, envio.track_id, envio.encf), ("En proceso", "T-1", si.rd_ncf))
			self.assertEqual(frappe.db.get_value("File", {"file_url": envio.xml}, "is_private"), 1)
			self.assertEqual(
				frappe.db.get_value("Sales Invoice", si.name, "rd_codigo_seguridad"), envio.codigo_seguridad
			)
			emision.consultar_pendientes()
			self.assertEqual(frappe.db.get_value("Envio ECF", nombre, "estado"), "Aceptado")

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

	# ------------------------------------------------------------------ Proporcionalidad del ITBIS

	def test_proporcionalidad_itbis(self):
		"""Noviembre: 6,000 gravado y 4,000 exento (coeficiente 60%); el ITBIS de un gasto común (180)
		se adelanta solo en un 60%."""
		self.assertEqual(declaraciones.resumen_it1(EMPRESA, 2026, 11).itbis_no_admitido, 0)
		self._venta("_Test Cliente RD", 6000, "2026-11-05")
		exenta = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": EMPRESA,
				"customer": "_Test Cliente RD",
				"set_posting_time": 1,
				"posting_date": "2026-11-06",
				"due_date": "2026-11-06",
				"items": [{"item_code": "_Test Servicio DGII", "qty": 1, "rate": 4000}],
			}
		).insert()
		exenta.submit()

		frappe.db.set_value("Supplier", "_Test Proveedor RD", "rd_itbis_proporcionalidad", 1)
		self.addCleanup(frappe.db.set_value, "Supplier", "_Test Proveedor RD", "rd_itbis_proporcionalidad", 0)
		pi = frappe.get_doc(
			{
				"doctype": "Purchase Invoice",
				"company": EMPRESA,
				"supplier": "_Test Proveedor RD",
				"set_posting_time": 1,
				"posting_date": "2026-11-10",
				"bill_date": "2026-11-10",
				"rd_ncf": "B0100000789",
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
		con_impuestos(pi, "Purchase Taxes and Charges Template", "ITBIS 18% Compras")
		pi.insert()
		self.assertEqual(pi.rd_itbis_proporcionalidad, 1)  # viene del proveedor
		pi.submit()

		fila = next(f for f in formatos.obtener("606", EMPRESA, 2026, 11) if f["_documento"] == pi.name)
		self.assertEqual(fila["itbis_proporcionalidad"], 180)
		self.assertEqual(fila["itbis_adelantar"], 180)  # la DGII lo calcula como facturado - costo

		r = declaraciones.resumen_it1(EMPRESA, 2026, 11)
		self.assertAlmostEqual(r.coeficiente, 0.6)
		self.assertAlmostEqual(r.itbis_proporcionalidad, 180)
		self.assertAlmostEqual(r.itbis_no_admitido, 72)
		self.assertAlmostEqual(r.itbis_deducible, 108)
		self.assertAlmostEqual(r.diferencia, 1080 - 108)
		conceptos = [f["concepto"] for f in declaraciones.filas_it1(r)]
		self.assertIn("ITBIS no admitido por proporcionalidad", conceptos)

	def test_coeficiente_exportaciones_y_exentas_por_destino(self):
		r = frappe._dict(
			total_operaciones=1000, gravadas={18.0: 400}, exportaciones_bienes=200, exentas_destino=100
		)
		self.assertAlmostEqual(declaraciones.coeficiente_proporcionalidad(r), 0.7)
		r.total_operaciones = 0
		self.assertEqual(declaraciones.coeficiente_proporcionalidad(r), 1)

	# ------------------------------------------------------------------ Anticipos del ISR

	def test_anticipos_isr(self):
		from erpnext_rd.dgii_reportes import anticipos
		from erpnext_rd.rd_compliance import recordatorios

		# TET 2%: doceava parte del impuesto; TET 1%: 1.5% de los ingresos en 12 cuotas
		self.assertEqual(anticipos.calcular(1_200_000, 24_000, 1.5).cuota, 2000)
		self.assertEqual(anticipos.calcular(1_200_000, 12_000, 1.5).cuota, 1500)
		self.assertEqual(anticipos.calcular(0, 0, 1.5).cuota, 0)

		base = frappe.get_doc(
			{
				"doctype": "Base Anticipo ISR",
				"company": EMPRESA,
				"ejercicio": 2025,
				"ingresos_brutos": 1_200_000,
				"impuesto_liquidado": 24_000,
			}
		).insert()
		self.assertEqual(str(base.aplica_desde), "2026-05-01")
		self.assertAlmostEqual(base.tasa_efectiva, 2)
		self.assertEqual(base.cuota_mensual, 2000)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc(
				{"doctype": "Base Anticipo ISR", "company": EMPRESA, "ejercicio": 2025, "ingresos_brutos": 1}
			).insert()

		# Marzo vence el 15/4, antes de que rija la base: sin anticipo. Septiembre vence el 15/10.
		self.assertIsNone(anticipos.anticipo(EMPRESA, 2026, 3))
		septiembre = anticipos.anticipo(EMPRESA, 2026, 9)
		self.assertEqual((septiembre.cuota, str(septiembre.vence)), (2000, "2026-10-15"))
		self.assertIn(
			"Anticipo del ISR de septiembre 2026",
			[o["obligacion"] for o in recordatorios.obligaciones(EMPRESA, 2026, 9)],
		)
		filas = anticipos.reporte({"company": EMPRESA, "anio": 2026})[1]
		self.assertEqual(sum(f["cuota"] for f in filas), 2000 * 9)  # abril a diciembre

		base.regimen = anticipos.EXENTO
		base.save()
		self.assertIsNone(anticipos.anticipo(EMPRESA, 2026, 9))

	# ------------------------------------------------------------------ NCF del proveedor en la DGII

	def test_verificacion_ncf_proveedor(self):
		from unittest.mock import patch

		from erpnext_rd.dgii_fiscal import consulta_ncf

		def compra(ncf):
			return frappe.get_doc(
				{
					"doctype": "Purchase Invoice",
					"company": EMPRESA,
					"supplier": "_Test Proveedor RD",
					"set_posting_time": 1,
					"posting_date": "2026-11-12",
					"bill_date": "2026-11-12",
					"rd_ncf": ncf,
					"items": [
						{
							"item_code": "_Test Servicio DGII",
							"qty": 1,
							"rate": 100,
							"expense_account": cuenta("6201"),
						}
					],
				}
			)

		vencido = frappe._dict(estado=consulta_ncf.VENCIDO, vigencia=getdate("2026-12-31"))
		no_corresponde = frappe._dict(estado=consulta_ncf.NO_CORRESPONDE, vigencia=None)
		with (
			patch.object(consulta_ncf, "_consulta_activa", return_value=True),
			patch.object(consulta_ncf, "consultar", return_value=vencido) as consultar,
		):
			pi = compra("B0100000901").insert()
			# Vencido hoy, pero el comprobante es de antes de su vencimiento: válido
			self.assertEqual(pi.rd_ncf_estado_dgii, consulta_ncf.VALIDO)
			self.assertEqual(consultar.call_args.args[:2], ("101003723", "B0100000901"))
			pi.save()  # sin cambios en el NCF no se vuelve a consultar
			self.assertEqual(consultar.call_count, 1)

			consultar.return_value = no_corresponde
			pi.rd_ncf = "B0100000902"
			pi.save()
			self.assertEqual(pi.rd_ncf_estado_dgii, consulta_ncf.NO_CORRESPONDE)
			fila = datos._fila_606(pi, getdate("2026-11-01"), getdate("2026-11-30"))
			self.assertIn("NCF no válido en la DGII", fila["_avisos"])

			frappe.db.set_single_value("Configuracion DGII", "bloquear_ncf_invalido", 1)
			self.addCleanup(frappe.db.set_single_value, "Configuracion DGII", "bloquear_ncf_invalido", 0)
			with self.assertRaisesRegex(frappe.ValidationError, "B0100000902"):
				pi.submit()

	# ------------------------------------------------------------------ Cuadre fiscal del IR-2

	def _activo(self, nombre: str, categoria: str, costo: float, compra: str, depreciacion: float = 0):
		item = f"_Test Activo {nombre}"
		_crear(
			{
				"doctype": "Item",
				"item_code": item,
				"item_name": item,
				"item_group": frappe.db.get_value("Item Group", {"is_group": 0}),
				"stock_uom": frappe.db.get_value("UOM", {"enabled": 1}) or "Nos",
				"is_stock_item": 0,
				"is_fixed_asset": 1,
				"asset_category": categoria,
			}
		)
		activo = frappe.get_doc(
			{
				"doctype": "Asset",
				"company": EMPRESA,
				"item_code": item,
				"asset_name": nombre,
				"asset_type": "Existing Asset",
				"location": self.ubicacion,
				"purchase_date": compra,
				"available_for_use_date": compra,
				"net_purchase_amount": costo,
				"purchase_amount": costo,
				"opening_accumulated_depreciation": depreciacion,
				"calculate_depreciation": 0,
			}
		).insert()
		activo.submit()
		return activo

	def test_cuadre_fiscal_ir2(self):
		from erpnext_rd.dgii_reportes import ir2

		def cuenta_tipo(tipo):
			return frappe.db.get_value("Account", {"company": EMPRESA, "account_type": tipo, "is_group": 0})

		cuentas = [
			{
				"company_name": EMPRESA,
				"fixed_asset_account": cuenta_tipo("Fixed Asset"),
				"accumulated_depreciation_account": cuenta_tipo("Accumulated Depreciation"),
				"depreciation_expense_account": cuenta_tipo("Depreciation"),
			}
		]
		for nombre, categoria, no_depreciable in (
			("_Test Edificios RD", ir2.CATEGORIA_1, 0),
			("_Test Equipos Oficina RD", ir2.CATEGORIA_2, 0),
			("_Test Maquinaria RD", ir2.CATEGORIA_3, 0),
			("_Test Terrenos RD", None, 1),
		):
			_crear(
				{
					"doctype": "Asset Category",
					"name": nombre,
					"asset_category_name": nombre,
					"rd_categoria_fiscal": categoria,
					"non_depreciable_category": no_depreciable,
					"accounts": cuentas,
				}
			)
		self.ubicacion = "_Test Ubicacion RD"
		_crear({"doctype": "Location", "name": self.ubicacion, "location_name": self.ubicacion})

		self._activo("Edificio", "_Test Edificios RD", 3_000_000, "2020-01-01", 600_000)
		self._activo("Maquina", "_Test Maquinaria RD", 500_000, "2024-03-01", 100_000)
		self._activo("Terreno", "_Test Terrenos RD", 1_000_000, "2019-05-01")
		self._activo("Computadora", "_Test Equipos Oficina RD", 100_000, "2026-03-10")

		# 2025, primer año: balances con el valor en libros; multiplicador 1.0495 de la DGII
		c25 = frappe.get_doc({"doctype": ir2.DOCTYPE, "company": EMPRESA, "ejercicio": 2025}).insert()
		self.assertEqual(
			(str(c25.desde), str(c25.hasta), c25.multiplicador), ("2025-01-01", "2025-12-31", 1.0495)
		)
		self.assertIn("valor en libros", c25.avisos)
		self.assertEqual([e.costo_fiscal_inicial for e in c25.edificaciones], [2_400_000])
		saldos = {(c.categoria, c.uso): c.balance_inicial for c in c25.cuentas}
		self.assertEqual(saldos, {(ir2.CATEGORIA_2, ir2.PROPIO): 0, (ir2.CATEGORIA_3, ir2.PROPIO): 400_000})
		self.assertEqual(c25.terrenos_costo_inicial, 1_000_000)

		# Patrimonio fiscal de 10 millones: la base son los 3.8 millones de activos no monetarios
		c25.patrimonio_fiscal = 10_000_000
		c25.beneficio_contable = 1_000_000
		c25.append("ajustes", {"concepto": "1.1 Impuestos no deducibles", "monto": 50_000})
		c25.save()
		self.assertEqual((c25.base_ajuste, c25.ajuste_fiscal), (3_800_000, 188_100))
		edificio = c25.edificaciones[0]
		self.assertEqual((edificio.ajuste_fiscal, edificio.depreciacion_fiscal), (118_800, 125_940))
		self.assertEqual(edificio.costo_fiscal_final, 2_392_860)
		maquinaria = next(c for c in c25.cuentas if c.categoria == ir2.CATEGORIA_3)
		self.assertEqual((maquinaria.ajuste_fiscal, maquinaria.depreciacion_fiscal), (19_800, 62_970))
		self.assertEqual(maquinaria.costo_fiscal_final, 356_830)
		self.assertEqual((c25.terrenos_ajuste, c25.terrenos_costo_final), (49_500, 1_049_500))
		self.assertEqual((c25.depreciacion_fiscal, c25.depreciacion_contable), (188_910, 0))
		deficiencia = [a for a in c25.ajustes if a.concepto == ir2.DEFICIENCIA_DEPRECIACION]
		self.assertEqual(
			[(a.tipo, a.monto, a.origen) for a in deficiencia], [(ir2.NEGATIVO, 188_910, ir2.AUTOMATICO)]
		)
		self.assertEqual((c25.total_positivos, c25.total_negativos), (50_000, 188_910))
		self.assertEqual((c25.renta_neta_imponible, c25.tasa_isr), (861_090, 27))
		self.assertEqual(c25.impuesto_liquidado, 232_494.3)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": ir2.DOCTYPE, "company": EMPRESA, "ejercicio": 2025}).insert()

		# 2026: parte de los saldos finales de 2025; la computadora entra mitad este año
		c26 = frappe.get_doc({"doctype": ir2.DOCTYPE, "company": EMPRESA, "ejercicio": 2026}).insert()
		self.assertEqual(c26.cuadre_anterior, c25.name)
		self.assertIn("multiplicador", c26.avisos)  # la DGII aún no publica el de 2026
		self.assertEqual(c26.ajuste_fiscal, 0)
		self.assertEqual(c26.edificaciones[0].depreciacion_fiscal, 119_643)
		equipos = next(c for c in c26.cuentas if c.categoria == ir2.CATEGORIA_2)
		self.assertEqual(
			(
				equipos.adiciones,
				equipos.base_depreciable,
				equipos.depreciacion_fiscal,
				equipos.costo_fiscal_final,
			),
			(100_000, 50_000, 12_500, 87_500),
		)
		maquinaria = next(c for c in c26.cuentas if c.categoria == ir2.CATEGORIA_3)
		self.assertEqual((maquinaria.balance_inicial, maquinaria.depreciacion_fiscal), (356_830, 53_524.5))
		self.assertEqual(c26.terrenos_costo_inicial, 1_049_500)
		renta = c26.beneficio_contable + c26.total_positivos - c26.total_negativos
		self.assertEqual(c26.renta_antes_perdidas, round(renta, 2))

		# Base de los anticipos del año siguiente con el resultado del cuadre
		base = ir2.crear_base_anticipos(c26.name)
		self.assertEqual(frappe.db.get_value("Base Anticipo ISR", base, "ejercicio"), 2026)
		self.assertEqual(ir2.crear_base_anticipos(c26.name), base)

		# Reparaciones del edificio por encima del 10% del costo fiscal ajustado: el exceso se capitaliza
		c25.edificaciones[0].reparaciones = 300_000
		c25.save()
		self.assertEqual(c25.edificaciones[0].reparaciones_capitalizadas, 300_000 - 251_880)
		self.assertEqual(c25.edificaciones[0].costo_fiscal_final, 2_392_860 + 48_120)
		otros = [a for a in c25.ajustes if a.concepto == ir2.OTROS_POSITIVOS]
		self.assertEqual([(a.monto, a.origen) for a in otros], [(48_120, ir2.AUTOMATICO)])
		self.assertEqual(c25.total_positivos, 50_000 + 48_120)

		# Formato de impresión del cuadre
		ir2.crear_formato()
		html = frappe.get_print(ir2.DOCTYPE, c25.name, ir2.FORMATO["name"])
		self.assertIn("Cuadre fiscal IR-2", html)
		self.assertIn("Edificio", html)
		self.assertIn("1.17 Otros ajustes positivos", html)

	def test_anexos_a1_b1_ir2(self):
		from erpnext_rd.dgii_reportes import estados_ir2

		self.assertEqual(
			frappe.db.get_value("Account", cuenta("4101"), "rd_casilla_ir2"),
			estados_ir2.casilla("B-1", "1.1"),
		)
		r = estados_ir2.calcular(EMPRESA, "2026-01-01", "2026-12-31")
		self.assertEqual(r.avisos, [])
		self.assertEqual(r.totales_a1["6"], r.totales_a1["11"])
		self.assertTrue(r.totales_a1["1"] > 0)

		ingresos, gastos = frappe.db.sql(
			"""SELECT SUM(IF(a.root_type = 'Income', g.credit - g.debit, 0)),
				SUM(IF(a.root_type = 'Expense', g.debit - g.credit, 0))
			FROM `tabGL Entry` g JOIN `tabAccount` a ON a.name = g.account
			WHERE g.company = %s AND g.is_cancelled = 0 AND g.posting_date BETWEEN '2026-01-01' AND '2026-12-31'""",
			EMPRESA,
		)[0]
		self.assertAlmostEqual(r.totales_b1["4"], float(ingresos), places=2)
		self.assertAlmostEqual(r.totales_b1["14"], float(ingresos) - float(gastos), places=2)
		self.assertEqual(r.b1["1.1"], r.totales_b1["1"])  # solo ventas locales
		self.assertAlmostEqual(r.a1["10.5"], r.totales_b1["14"], places=2)  # sin ISR registrado

		columnas, filas, mensaje, _grafico, resumen = estados_ir2.reporte(
			{"company": EMPRESA, "desde": "2026-01-01", "hasta": "2026-12-31"}
		)
		self.assertIn(
			{
				"casilla": "14",
				"descripcion": "Beneficio (pérdida) antes del impuesto sobre la renta",
				"monto": r.totales_b1["14"],
				"negrita": 1,
			},
			filas,
		)
		self.assertEqual(resumen[0]["value"], r.totales_a1["6"])
