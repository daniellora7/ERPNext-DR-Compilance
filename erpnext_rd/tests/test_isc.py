"""Impuesto selectivo al consumo (ISC): tasas, cálculo en las ventas, 607, resumen y requisitos."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from erpnext_rd.dgii_fiscal import isc
from erpnext_rd.ecf import datos as datos_ecf
from erpnext_rd.ecf import esquemas, firma
from erpnext_rd.rd_compliance import perfil, recordatorios
from erpnext_rd.tests.test_ecf import certificado_de_prueba

EMPRESA = "_Test ISC RD"
RNC_EMPRESA = "101543231"
RNC_CLIENTE = "101003723"
FECHA = "2026-11-02"
CERVEZA = "_Test Cerveza ISC"
CERVEZA_IMPORTADA = "_Test Cerveza Importada ISC"
INTERNET = "_Test Internet ISC"
CIGARRILLOS = "_Test Cigarrillos ISC"


def _articulo(codigo: str, **campos):
	if frappe.db.exists("Item", codigo):
		frappe.db.set_value("Item", codigo, campos)
		return
	frappe.get_doc(
		{
			"doctype": "Item",
			"item_code": codigo,
			"item_name": codigo,
			"item_group": frappe.db.get_value("Item Group", {"parent_item_group": ("is", "not set")}),
			"stock_uom": frappe.db.get_value("UOM", {"enabled": 1}) or "Nos",
			"is_stock_item": 0,
			**campos,
		}
	).insert(ignore_permissions=True)


def _venta(item_code: str, qty: float, rate: float, fecha: str = FECHA):
	from erpnext.controllers.accounts_controller import get_taxes_and_charges

	si = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": EMPRESA,
			"customer": "_Test Cliente ISC",
			"set_posting_time": 1,
			"posting_date": fecha,
			"due_date": fecha,
			"items": [{"item_code": item_code, "qty": qty, "rate": rate}],
		}
	)
	si.taxes_and_charges = frappe.db.get_value(
		"Sales Taxes and Charges Template", {"company": EMPRESA, "title": "ITBIS 18%"}
	)
	si.set("taxes", get_taxes_and_charges("Sales Taxes and Charges Template", si.taxes_and_charges))
	return si.insert()


class TestISC(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.db.set_single_value("Configuracion DGII", "aplicar_catalogo_cuentas", 1)
		if not frappe.db.exists("Company", EMPRESA):
			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": EMPRESA,
					"abbr": "TISC",
					"country": "Dominican Republic",
					"default_currency": "DOP",
					"tax_id": RNC_EMPRESA,
					"chart_of_accounts": "Standard",
					"create_chart_of_accounts_based_on": "Standard Template",
				}
			).insert()
			frappe.get_doc(
				{
					"doctype": "Secuencia NCF",
					"company": EMPRESA,
					"tipo_comprobante": "B01",
					"desde": 1,
					"hasta": 100,
					"fecha_vencimiento": "2027-12-31",
				}
			).insert()
		if not frappe.db.exists("Customer", "_Test Cliente ISC"):
			frappe.get_doc(
				{"doctype": "Customer", "customer_name": "_Test Cliente ISC", "tax_id": RNC_CLIENTE}
			).insert()
		# Caja de 24 botellas de 0.355 L al 5%, precio al por menor de la caja RD$2,400
		alcohol = {
			"rd_isc_categoria": isc.ALCOHOL,
			"rd_isc_producto": "Cerveza",
			"rd_isc_envases": 24,
			"rd_isc_litros": 8.52,
			"rd_isc_grado": 5,
			"rd_isc_precio_por_menor": 2400,
		}
		_articulo(CERVEZA, rd_isc_origen=isc.PRODUCCION_LOCAL, **alcohol)
		_articulo(CERVEZA_IMPORTADA, rd_isc_origen=isc.IMPORTADO, **alcohol)
		_articulo(INTERNET, rd_isc_categoria=isc.TELECOMUNICACIONES, rd_bien_o_servicio="Servicio")
		cls.llave, cls.cert = firma.cargar_certificado(certificado_de_prueba(), "prueba")

	def setUp(self):
		frappe.db.savepoint("isc_rd")
		perfil.guardar(
			EMPRESA,
			{
				"tamano": perfil.GRANDE,
				"tipo_sociedad": "Sociedad Anónima (SA)",
				"isc_alcohol": 1,
				"isc_telecomunicaciones": 1,
			},
		)

	def tearDown(self):
		frappe.db.rollback(save_point="isc_rd")
		frappe.clear_document_cache(perfil.DOCTYPE, EMPRESA)
		for codigo in (CERVEZA, CERVEZA_IMPORTADA, INTERNET, CIGARRILLOS):
			frappe.clear_document_cache("Item", codigo)

	def test_tasas_vigentes(self):
		self.assertEqual(isc.tasa(isc.ALCOHOL, FECHA).monto_especifico, 768.65)
		self.assertEqual(isc.tasa(isc.TABACO, FECHA, "10 cigarrillos").monto_especifico, 32.51)
		self.assertEqual(isc.tasa(isc.SEGUROS_VIDA, "2027-06-30").ad_valorem, 11)
		self.assertEqual(isc.tasa(isc.SEGUROS_VIDA, "2028-01-01").ad_valorem, 6)
		self.assertEqual(isc.tasa(isc.SEGUROS_VIDA, "2030-01-01").ad_valorem, 0)
		# Desde 2027 los montos específicos se ajustan cada año: hasta que se registren, no hay tasa
		self.assertIsNone(isc.tasa(isc.ALCOHOL, "2027-01-15"))

	def test_venta_de_alcohol(self):
		"""Específico por litro de alcohol absoluto más 10% del precio al por menor; ITBIS sobre precio + ISC."""
		si = _venta(CERVEZA, 2, 2000)
		linea = si.items[0]
		self.assertAlmostEqual(linea.rd_isc_base_especifica, 0.852, places=4)  # 2 x 8.52 L x 5%
		self.assertEqual(linea.rd_isc_especifico, 654.89)  # 0.852 x 768.65
		self.assertEqual(linea.rd_isc_base_ad_valorem, 4800)
		self.assertEqual(linea.rd_isc_ad_valorem, 480)

		fila_isc, fila_itbis = si.taxes[0], si.taxes[1]
		self.assertEqual(
			(fila_isc.charge_type, fila_isc.account_head), (isc.TIPO_CARGO, isc.cuenta_isc(EMPRESA))
		)
		self.assertEqual(fila_isc.tax_amount, 1134.89)
		self.assertEqual((fila_itbis.charge_type, fila_itbis.row_id), ("On Previous Row Total", "1"))
		self.assertEqual(fila_itbis.tax_amount, flt((4000 + 1134.89) * 0.18, 2))
		self.assertEqual(si.grand_total, flt(4000 + 1134.89 + fila_itbis.tax_amount, 2))

		si.submit()
		from erpnext_rd.dgii_reportes import datos

		fila_607 = next(f for f in datos.datos_607(EMPRESA, 2026, 11) if f["ncf"] == si.rd_ncf)
		self.assertEqual(flt(fila_607["isc"]), 1134.89)

		resumen = {f.categoria: f for f in isc.resumen_mensual(EMPRESA, 2026, 11)}
		self.assertEqual(resumen[isc.ALCOHOL].total, 1134.89)
		self.assertAlmostEqual(resumen[isc.ALCOHOL].base_especifica, 0.852, places=4)

		# Con NCF serie B no hay e-CF
		with self.assertRaises(frappe.ValidationError):
			isc.validar_ecf(si)

	def _ecf(self, si, tipo: int = 31) -> dict:
		si.rd_tipo_comprobante = f"E{tipo}"
		si.rd_ncf = f"E{tipo}0000000001"
		si.rd_ncf_vencimiento = "2027-12-31"
		si.company_address_display = "Av. 27 de Febrero 1, Santo Domingo"
		isc.validar_ecf(si)
		contenido = datos_ecf.datos_ecf(si)
		firmado = firma.firmar(esquemas.construir(tipo, contenido), self.llave, self.cert)
		self.assertEqual(esquemas.errores(tipo, firmado), [])
		return contenido

	def test_ecf_de_alcohol(self):
		"""Tabla I del formato e-CF: 006 cerveza (específico) y 023 (ad valorem); ITBIS sobre neto + ISC."""
		si = _venta(CERVEZA, 2, 2000)
		contenido = self._ecf(si)
		linea = contenido["DetallesItems"]["Item"][0]
		self.assertEqual(
			[i["TipoImpuesto"] for i in linea["TablaImpuestoAdicional"]["ImpuestoAdicional"]], ["006", "023"]
		)
		self.assertEqual(linea["CantidadReferencia"], "24.00")  # botellas por caja
		self.assertEqual(linea["TablaSubcantidad"]["SubcantidadItem"][0]["Subcantidad"], "0.355")  # litros
		self.assertEqual(linea["GradosAlcohol"], "5.00")
		self.assertEqual(linea["PrecioUnitarioReferencia"], "100.00")  # PVP de una botella

		# Cálculo de la DGII: cantidad x referencia x subcantidad x grados x tasa
		self.assertEqual(flt(2 * 24 * 0.355 * 0.05 * 768.65, 2), 654.89)
		totales = contenido["Encabezado"]["Totales"]
		especifico, ad_valorem = totales["ImpuestosAdicionales"]["ImpuestoAdicional"]
		self.assertEqual((especifico["TipoImpuesto"], especifico["TasaImpuestoAdicional"]), ("006", "768.65"))
		self.assertEqual(especifico["MontoImpuestoSelectivoConsumoEspecifico"], "654.89")
		self.assertEqual((ad_valorem["TipoImpuesto"], ad_valorem["TasaImpuestoAdicional"]), ("023", "10.00"))
		self.assertEqual(ad_valorem["MontoImpuestoSelectivoConsumoAdvalorem"], "480.00")
		self.assertEqual(totales["MontoImpuestoAdicional"], "1134.89")
		self.assertEqual(totales["MontoGravadoI1"], "4000.00")
		self.assertEqual(totales["TotalITBIS1"], datos_ecf.monto((4000 + 1134.89) * 0.18))
		self.assertEqual(totales["MontoTotal"], datos_ecf.monto(si.grand_total))

	def test_base_neta_del_formato_dgii(self):
		"""(PVP / 1.18 - específico unitario) / 1.10 x 10%, como en el formato e-CF."""
		fila = frappe.get_all(
			"Tasa ISC", filters={"parent": "Configuracion DGII", "categoria": isc.ALCOHOL}, pluck="name"
		)[0]
		frappe.db.set_value("Tasa ISC", fila, "base_ad_valorem", isc.BASE_NETA)
		si = _venta(CERVEZA, 2, 2000)
		especifico_botella = 654.89 / 48
		esperado = (100 / 1.18 - especifico_botella) / 1.10 * 0.10 * 48
		self.assertAlmostEqual(si.items[0].rd_isc_ad_valorem, esperado, delta=0.01)
		self.assertAlmostEqual(si.items[0].rd_isc_ad_valorem, 310.26, delta=0.01)
		ad_valorem = self._ecf(si)["Encabezado"]["Totales"]["ImpuestosAdicionales"]["ImpuestoAdicional"][1]
		self.assertEqual(
			ad_valorem["MontoImpuestoSelectivoConsumoAdvalorem"], f"{si.items[0].rd_isc_ad_valorem:.2f}"
		)

	def test_ecf_de_telecomunicaciones(self):
		"""004: otros impuestos adicionales; el ITBIS sigue sobre el neto."""
		si = _venta(INTERNET, 1, 1000)
		contenido = self._ecf(si)
		linea = contenido["DetallesItems"]["Item"][0]
		self.assertEqual(linea["TablaImpuestoAdicional"]["ImpuestoAdicional"], [{"TipoImpuesto": "004"}])
		self.assertNotIn("CantidadReferencia", linea)
		totales = contenido["Encabezado"]["Totales"]
		self.assertEqual(
			totales["ImpuestosAdicionales"]["ImpuestoAdicional"][0]["OtrosImpuestosAdicionales"], "100.00"
		)
		self.assertEqual((totales["TotalITBIS1"], totales["MontoTotal"]), ("180.00", "1280.00"))

	def test_ecf_de_cigarrillos(self):
		"""Cartón de 10 cajetillas de 20: 019 (por cajetilla) y 036 (20% del PVP)."""
		perfil.guardar(EMPRESA, {"isc_tabaco": 1})
		frappe.clear_document_cache(perfil.DOCTYPE, EMPRESA)
		_articulo(
			CIGARRILLOS,
			rd_isc_categoria=isc.TABACO,
			rd_isc_producto="Cigarrillos que contienen tabaco",
			rd_isc_origen=isc.PRODUCCION_LOCAL,
			rd_isc_cigarrillos="20",
			rd_isc_cajetillas=10,
			rd_isc_precio_por_menor=3000,
		)
		frappe.clear_document_cache("Item", CIGARRILLOS)
		si = _venta(CIGARRILLOS, 1, 2500)
		contenido = self._ecf(si)
		linea = contenido["DetallesItems"]["Item"][0]
		self.assertEqual(
			[i["TipoImpuesto"] for i in linea["TablaImpuestoAdicional"]["ImpuestoAdicional"]], ["019", "036"]
		)
		self.assertEqual(linea["CantidadReferencia"], "10.00")
		self.assertEqual(linea["TablaSubcantidad"]["SubcantidadItem"][0]["Subcantidad"], "20.000")
		self.assertEqual(linea["PrecioUnitarioReferencia"], "300.00")
		self.assertNotIn("GradosAlcohol", {k for k, v in linea.items() if v is not None})
		especifico, ad_valorem = contenido["Encabezado"]["Totales"]["ImpuestosAdicionales"][
			"ImpuestoAdicional"
		]
		self.assertEqual(especifico["MontoImpuestoSelectivoConsumoEspecifico"], "650.20")  # 10 x 65.02
		self.assertEqual(ad_valorem["MontoImpuestoSelectivoConsumoAdvalorem"], "600.00")  # 20% x 3,000

	def test_ecf_sin_codigo_o_tipo_que_no_lleva_isc(self):
		si = _venta(CERVEZA, 1, 2000)
		si.rd_tipo_comprobante = "E46"
		with self.assertRaises(frappe.ValidationError):
			isc.validar_ecf(si)

		si.rd_tipo_comprobante = "E31"
		frappe.db.set_value("Item", CERVEZA, "rd_isc_producto", None)
		frappe.clear_document_cache("Item", CERVEZA)
		with self.assertRaises(frappe.ValidationError):
			isc.validar_ecf(si)

		si.items[0].rd_isc_categoria = isc.VAPEADORES
		with self.assertRaises(frappe.ValidationError):
			isc.validar_ecf(si)

	def test_importado_y_empresa_sin_isc_no_cobran(self):
		si = _venta(CERVEZA_IMPORTADA, 1, 2000)
		self.assertFalse(any(t.charge_type == isc.TIPO_CARGO for t in si.taxes))
		self.assertEqual(si.taxes[0].charge_type, "On Net Total")

		perfil.guardar(EMPRESA, {"isc_alcohol": 0})
		frappe.clear_document_cache(perfil.DOCTYPE, EMPRESA)
		si = _venta(CERVEZA, 1, 2000)
		self.assertFalse(si.items[0].rd_isc_categoria)
		self.assertEqual(si.total_taxes_and_charges, 360)

	def test_servicio_de_telecomunicaciones(self):
		"""10% sobre el valor del servicio; el ITBIS sigue sobre el neto (art. 339, 3)."""
		si = _venta(INTERNET, 1, 1000)
		self.assertEqual(si.taxes[0].tax_amount, 100)
		self.assertEqual((si.taxes[1].charge_type, si.taxes[1].tax_amount), ("On Net Total", 180))
		self.assertEqual((si.items[0].rd_isc_base_ad_valorem, si.items[0].rd_isc_ad_valorem), (1000, 100))

	def test_bloquea_sin_tasa_o_sin_datos(self):
		with self.assertRaises(frappe.ValidationError):
			_venta(CERVEZA, 1, 2000, fecha="2027-01-15")
		frappe.db.set_value("Item", CERVEZA, "rd_isc_grado", 0)
		frappe.clear_document_cache("Item", CERVEZA)
		with self.assertRaises(frappe.ValidationError):
			_venta(CERVEZA, 1, 2000)

	def test_requisitos_y_recordatorio(self):
		estados = {r["requisito"]: r["estado"] for r in perfil.evaluar(EMPRESA)}
		self.assertEqual(estados["Tasas del ISC vigentes"], perfil.CUMPLIDO)
		self.assertEqual(estados["Cuenta del ISC por pagar"], perfil.CUMPLIDO)
		self.assertEqual(estados["Artículos clasificados en el ISC"], perfil.CUMPLIDO)
		self.assertNotIn("Impuesto selectivo al consumo (ISC)", estados)

		obligaciones = {o["obligacion"]: o["vence"] for o in recordatorios.obligaciones(EMPRESA, 2026, 11)}
		vence = next(v for o, v in obligaciones.items() if o.startswith("Declaración del ISC"))
		self.assertEqual(str(vence), "2026-12-21")  # el 20 de diciembre de 2026 es domingo
