"""Soporte del reembolso del ITBIS de los exportadores (Fase 8.4)."""

from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from erpnext_rd.dgii_reportes.report.soporte_reembolso_itbis_exportadores import (
	soporte_reembolso_itbis_exportadores as reporte,
)
from erpnext_rd.rd_compliance import perfil
from erpnext_rd.tests import test_isc
from erpnext_rd.tests.test_isc import EMPRESA


def _it1(ventas=0, exportaciones=0, itbis=0, deducible=0, saldo_anterior=0):
	resultado = itbis - deducible - saldo_anterior
	return frappe._dict(
		ventas_brutas=ventas,
		notas_credito=0,
		exportaciones=exportaciones,
		itbis_facturado=itbis,
		itbis_notas_credito=0,
		itbis_compras=deducible,
		itbis_deducible=deducible,
		itbis_a_pagar=max(resultado, 0),
		nuevo_saldo_favor=max(-resultado, 0),
	)


class TestReembolsoExportadores(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		test_isc.TestISC.setUpClass()

	def setUp(self):
		frappe.db.savepoint("reembolso")

	def tearDown(self):
		frappe.db.rollback(save_point="reembolso")
		frappe.clear_document_cache(perfil.DOCTYPE, EMPRESA)

	def test_saldo_a_favor_pasa_de_un_mes_al_siguiente(self):
		datos = {
			1: dict(ventas=1_000_000, exportaciones=800_000, itbis=36_000, deducible=90_000),
			2: dict(ventas=500_000, exportaciones=500_000, itbis=0, deducible=20_000),
		}

		def it1(company, anio, mes, saldo_favor_anterior=0):
			return _it1(saldo_anterior=saldo_favor_anterior, **datos.get(mes, {}))

		with patch.object(reporte.declaraciones, "resumen_it1", side_effect=it1):
			filas = reporte.meses(EMPRESA, 2026, saldo_favor_inicial=5_000)
			columnas, datos_reporte, mensaje, _grafico, resumen = reporte.execute(
				{"company": EMPRESA, "anio": 2026, "saldo_favor_inicial": 5_000}
			)

		# Marzo en adelante sigue el saldo a favor, sin ventas ni compras
		self.assertEqual([f["mes"] for f in filas[:2]], ["2026-01", "2026-02"])
		enero, febrero = filas[0], filas[1]
		self.assertEqual((enero["ventas_locales"], enero["porcentaje_exportacion"]), (200_000, 80))
		self.assertEqual((enero["saldo_anterior"], enero["saldo_a_favor"]), (5_000, 59_000))
		self.assertEqual((febrero["saldo_anterior"], febrero["saldo_a_favor"]), (59_000, 79_000))
		self.assertEqual(resumen[2]["value"], 79_000)
		self.assertIn("Oficina Virtual", mensaje)

	def test_requisito_del_exportador(self):
		perfil.guardar(EMPRESA, {"tamano": perfil.GRANDE, "exportador": 1})
		frappe.clear_document_cache(perfil.DOCTYPE, EMPRESA)
		requisito = next(
			r
			for r in perfil.evaluar(EMPRESA)
			if r["requisito"] == "Exportaciones en el 607 (reembolso del ITBIS)"
		)
		self.assertEqual(requisito["estado"], perfil.FALTA)
		nombres = [r["requisito"] for r in perfil.evaluar(EMPRESA)]
		self.assertNotIn("Reembolso o compensación del ITBIS de exportadores", nombres)
