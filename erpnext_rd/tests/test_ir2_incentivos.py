"""Incentivos en la liquidación del IR-2 (Fase 8.6): casillas 3, 4, 10, 15, 16 y 20 del instructivo
de marzo de 2026, y su propuesta desde los incentivos del perfil tributario."""

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from erpnext_rd.dgii_reportes import ir2
from erpnext_rd.rd_compliance import perfil
from erpnext_rd.tests import test_isc
from erpnext_rd.tests.test_isc import EMPRESA

EJERCICIO = 2023


class TestLiquidacionIncentivos(UnitTestCase):
	def test_orden_de_las_casillas(self):
		# 7 = 1 000 000 + 200 000 - 300 000 (exención) - 50 000 (dividendos) - 100 000 = 750 000
		# 9 = 7 - 150 000 (pérdidas) = 600 000; 11 = 9 - 100 000 (Ley 392-07) = 500 000; 12 = 135 000
		r = ir2.liquidar(
			1_000_000,
			200_000,
			100_000,
			150_000,
			27,
			35_000,
			exencion=300_000,
			dividendos=50_000,
			deduccion_inversion=100_000,
		)
		self.assertEqual(
			(r.renta_antes_perdidas, r.renta_antes_deduccion, r.renta_neta_imponible),
			(750_000, 600_000, 500_000),
		)
		self.assertEqual((r.impuesto_liquidado, r.diferencia_pagar), (135_000, 100_000))

	def test_la_deduccion_no_deja_renta_negativa(self):
		r = ir2.liquidar(100_000, 0, 0, 0, 27, 0, deduccion_inversion=250_000)
		self.assertEqual((r.renta_neta_imponible, r.impuesto_liquidado), (0, 0))


class TestIncentivosDelPerfil(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		test_isc.TestISC.setUpClass()

	def setUp(self):
		frappe.db.savepoint("ir2_incentivos")
		perfil.guardar(EMPRESA, {"tamano": perfil.GRANDE})
		frappe.db.delete(ir2.DOCTYPE, {"company": EMPRESA, "ejercicio": EJERCICIO})

	def tearDown(self):
		frappe.db.rollback(save_point="ir2_incentivos")
		frappe.clear_document_cache(perfil.DOCTYPE, EMPRESA)

	def _incentivo(self, regimen, desde=None, hasta=None, exento_isr=0):
		doc = frappe.get_doc(perfil.DOCTYPE, EMPRESA)
		doc.append(
			"incentivos",
			{
				"regimen": regimen,
				"desde": desde,
				"hasta": hasta,
				"exento_isr": exento_isr,
				"resolucion": "R-1",
			},
		)
		doc.save()
		frappe.clear_document_cache(perfil.DOCTYPE, EMPRESA)

	def _cuadre(self):
		return frappe.get_doc({"doctype": ir2.DOCTYPE, "company": EMPRESA, "ejercicio": EJERCICIO}).insert()

	def test_zona_franca_exenta_todo_el_ejercicio(self):
		self._incentivo("Zona franca (Ley 8-90)", desde="2020-01-01", exento_isr=1)
		c = self._cuadre()
		self.assertTrue(c.exencion_total)
		c.beneficio_contable = 2_000_000
		c.anticipos_pagados = 10_000
		c.save()
		self.assertEqual(
			(c.exencion_incentivos, c.renta_neta_imponible, c.impuesto_liquidado), (2_000_000, 0, 0)
		)
		self.assertEqual(c.saldo_favor, 10_000)

		# Sin la exención total, el monto aprobado se escribe a mano
		c.exencion_total = 0
		c.exencion_incentivos = 500_000
		c.save()
		self.assertEqual(c.renta_neta_imponible, 1_500_000)

	def test_exencion_de_parte_del_ejercicio(self):
		self._incentivo("Turismo (Ley 158-01)", desde=f"{EJERCICIO}-07-01", exento_isr=1)
		c = self._cuadre()
		self.assertFalse(c.exencion_total)
		self.assertIn("casilla 3", c.avisos)

	def test_avisos_y_creditos(self):
		self._incentivo("Proindustria (Ley 392-07)")
		self._incentivo("Energías renovables (Ley 57-07)")
		self._incentivo("Cine (Ley 108-10)", hasta=f"{EJERCICIO - 1}-12-31")  # vencido: no avisa
		c = self._cuadre()
		self.assertIn("casilla 10", c.avisos)
		self.assertIn("casilla 16", c.avisos)
		self.assertNotIn("casilla 15", c.avisos)

		c.beneficio_contable = 1_000_000
		c.deduccion_inversion = 200_000
		c.credito_energia_renovable = 50_000
		c.credito_inversion_cine = 10_000
		c.credito_fiscal_cine = 6_000
		c.save()
		self.assertEqual((c.renta_antes_deduccion, c.renta_neta_imponible), (1_000_000, 800_000))
		self.assertEqual(c.impuesto_liquidado, 216_000)
		self.assertEqual(c.diferencia_pagar, 150_000)

		c.traer_datos()
		self.assertNotIn("casilla 10", c.avisos, "con el monto escrito ya no avisa")

	def test_formato_impreso(self):
		self._incentivo("Proindustria (Ley 392-07)")
		c = self._cuadre()
		c.beneficio_contable = 1_000_000
		c.deduccion_inversion = 200_000
		c.save()
		ir2.crear_formato()
		html = frappe.get_print(ir2.DOCTYPE, c.name, ir2.FORMATO["name"])
		self.assertIn("Deducción por inversión (Ley 392-07)", html)
		self.assertNotIn("Crédito por energía renovable", html)
