"""Operaciones con partes relacionadas (Fase 8.3): resumen para la DIOR, requisito y recordatorio."""

from datetime import date

import frappe
from frappe.tests import IntegrationTestCase

from erpnext_rd.dgii_reportes import dior
from erpnext_rd.dgii_reportes.report.operaciones_relacionadas_dior import operaciones_relacionadas_dior
from erpnext_rd.rd_compliance import perfil, recordatorios
from erpnext_rd.tests import test_isc
from erpnext_rd.tests.test_isc import EMPRESA, FECHA

CLIENTE = "_Test Cliente ISC"
SERVICIO = "_Test Servicio DIOR"


class TestDIOR(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		test_isc.TestISC.setUpClass()
		test_isc._articulo(SERVICIO)

	def setUp(self):
		frappe.db.savepoint("dior")
		perfil.guardar(EMPRESA, {"tamano": perfil.GRANDE, "partes_relacionadas": 1})

	def tearDown(self):
		frappe.db.rollback(save_point="dior")
		frappe.clear_document_cache(perfil.DOCTYPE, EMPRESA)

	def _venta(self, monto: float):
		si = frappe.get_doc(
			{
				"doctype": "Sales Invoice",
				"company": EMPRESA,
				"customer": CLIENTE,
				"set_posting_time": 1,
				"posting_date": FECHA,
				"due_date": FECHA,
				"items": [{"item_code": SERVICIO, "qty": 1, "rate": monto}],
			}
		).insert()
		si.submit()
		return si

	def _requisito(self):
		return next(
			r for r in perfil.evaluar(EMPRESA) if r["requisito"] == "Partes relacionadas marcadas (DIOR)"
		)

	def test_resumen_del_ejercicio(self):
		self.assertEqual(self._requisito()["estado"], perfil.FALTA)
		frappe.db.set_value(
			"Customer", CLIENTE, {"rd_parte_relacionada": 1, "rd_vinculacion": "Mismo accionista"}
		)
		self._venta(1000)
		self._venta(500)
		self.assertEqual(self._requisito()["estado"], perfil.CUMPLIDO)

		filas = dior.operaciones(EMPRESA, "2026-01-01", "2026-12-31")
		self.assertEqual(len(filas), 1)
		fila = filas[0]
		self.assertEqual(
			(fila.tipo, fila.contraparte, fila.vinculacion, fila.documentos, fila.monto),
			(dior.VENTA, CLIENTE, "Mismo accionista", 2, 1500),
		)
		# Fuera del ejercicio no cuenta
		self.assertEqual(dior.operaciones(EMPRESA, "2025-01-01", "2025-12-31"), [])

		columnas, datos, mensaje = operaciones_relacionadas_dior.execute(
			{"company": EMPRESA, "desde": "2026-01-01", "hasta": "2026-12-31"}
		)
		self.assertEqual(datos[0]["monto"], 1500)
		self.assertIn("29-06-2027", mensaje.replace("/", "-"))

	def test_vence_180_dias_despues_del_cierre(self):
		self.assertEqual(dior.fecha_limite("2026-12-31"), date(2027, 6, 29))
		obligaciones = [o["obligacion"] for o in recordatorios.obligaciones(EMPRESA, 2026, 12)]
		self.assertTrue(any(o.startswith("DIOR") for o in obligaciones))
		# Sin partes relacionadas en el perfil no hay DIOR
		perfil.guardar(EMPRESA, {"partes_relacionadas": 0})
		frappe.clear_document_cache(perfil.DOCTYPE, EMPRESA)
		obligaciones = [o["obligacion"] for o in recordatorios.obligaciones(EMPRESA, 2026, 12)]
		self.assertFalse(any(o.startswith("DIOR") for o in obligaciones))

	def _prestamo(self, monto: float, cobro: bool = False):
		cuentas = frappe.get_cached_value(
			"Company", EMPRESA, ["default_receivable_account", "default_cash_account"], as_dict=True
		)
		cliente = {"account": cuentas.default_receivable_account, "party_type": "Customer", "party": CLIENTE}
		caja = {"account": cuentas.default_cash_account}
		lineas = (
			[{**caja, "debit_in_account_currency": monto}, {**cliente, "credit_in_account_currency": monto}]
			if cobro
			else [
				{**cliente, "debit_in_account_currency": monto},
				{**caja, "credit_in_account_currency": monto},
			]
		)
		je = frappe.get_doc(
			{
				"doctype": "Journal Entry",
				"company": EMPRESA,
				"posting_date": FECHA,
				"voucher_type": "Journal Entry",
				"accounts": lineas,
			}
		).insert()
		je.submit()
		return je

	def test_prestamos_y_otros_asientos(self):
		frappe.db.set_value(
			"Customer", CLIENTE, {"rd_parte_relacionada": 1, "rd_vinculacion": "Mismo accionista"}
		)
		self._prestamo(10_000)
		self._prestamo(4_000, cobro=True)
		self._venta(1000)

		filas = {f.tipo: f for f in dior.operaciones(EMPRESA, "2026-01-01", "2026-12-31")}
		self.assertEqual(set(filas), {dior.VENTA, dior.ASIENTO})
		asiento = filas[dior.ASIENTO]
		# Préstamo dado y cobro parcial: dos operaciones, sin compensarlas
		self.assertEqual((asiento.documentos, asiento.cargos, asiento.abonos), (2, 10_000, 4_000))

	def test_aviso_del_ajuste_1_9_en_el_ir2(self):
		from erpnext_rd.dgii_reportes import ir2

		frappe.db.set_value(
			"Customer", CLIENTE, {"rd_parte_relacionada": 1, "rd_vinculacion": "Mismo accionista"}
		)
		self._venta(1000)
		frappe.db.delete(ir2.DOCTYPE, {"company": EMPRESA, "ejercicio": 2026})
		cuadre = frappe.get_doc({"doctype": ir2.DOCTYPE, "company": EMPRESA, "ejercicio": 2026}).insert()
		self.assertIn(ir2.AJUSTE_PRECIOS_TRANSFERENCIA, cuadre.avisos)

		cuadre.append(
			"ajustes", {"concepto": ir2.AJUSTE_PRECIOS_TRANSFERENCIA, "monto": 50, "origen": ir2.MANUAL}
		)
		cuadre.traer_datos()
		self.assertNotIn(ir2.AJUSTE_PRECIOS_TRANSFERENCIA, cuadre.avisos or "")

	def test_codigos_de_operacion(self):
		c = dior.codigo_operacion
		self.assertEqual(c(True, False, False, True, False), dior.VENTA_BIENES)
		self.assertEqual(c(True, False, False, True, True), dior.EXPORTACION)
		self.assertEqual(c(True, False, False, False, False), dior.VENTA_SERVICIOS)
		self.assertEqual(c(True, True, False, True, False), "131")
		self.assertEqual(c(False, False, True, False, True), dior.IMPORTACION_ACTIVOS)
		self.assertEqual(c(False, False, False, True, False), dior.COMPRA_BIENES)
		self.assertEqual(c(False, False, False, False, True), dior.COMPRA_SERVICIOS)
		self.assertEqual(c(False, True, False, False, False), "225")

	def test_hoja_de_detalle(self):
		frappe.db.set_value(
			"Customer",
			CLIENTE,
			{
				"rd_parte_relacionada": 1,
				"rd_vinculacion": "Mismo accionista",
				"rd_supuesto_vinculacion": dior.SUPUESTOS_VINCULACION[1],
			},
		)
		self._venta(1000)
		self._venta(500)
		hoja = dior.hoja_detalle(EMPRESA, "2026-01-01", "2026-12-31")

		self.assertEqual(len(hoja["empresas"]), 1)
		empresa = hoja["empresas"][0]
		self.assertEqual(len(empresa), len(dior.COLUMNAS_EMPRESAS))
		self.assertEqual(empresa[-1], "2", "solo el código del supuesto")

		self.assertEqual(len(hoja["operaciones"]), 1)
		operacion = hoja["operaciones"][0]
		self.assertEqual(len(operacion), len(dior.COLUMNAS_OPERACIONES))
		self.assertEqual(operacion[0], empresa[0], "el nombre coincide con el de la pestaña Empresas")
		# Servicio vendido en pesos: valor original = monto, tasa 1
		self.assertEqual(
			operacion[1:7], [dior.VENTA_SERVICIOS, "Prestacion de servicios", 1500, "DOP", 1.0, 1500]
		)

		from io import BytesIO

		from openpyxl import load_workbook

		dior.descargar_hoja_detalle(EMPRESA, "2026-01-01", "2026-12-31")
		libro = load_workbook(BytesIO(frappe.response["filecontent"]))
		self.assertEqual(libro.sheetnames, ["Empresas", "Operaciones"])
		self.assertEqual(libro["Operaciones"]["B2"].value, dior.VENTA_SERVICIOS)
