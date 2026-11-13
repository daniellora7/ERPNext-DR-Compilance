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
