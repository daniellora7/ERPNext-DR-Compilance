"""Impuesto sobre los activos (Fase 8.5): formulario IR-2-c2 de la DGII y Código Tributario arts. 401
a 407, con la exención del sector agropecuario de la Ley 30-26 (art. 32)."""

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from erpnext_rd.dgii_reportes import estados_ir2, ir2
from erpnext_rd.rd_compliance import perfil
from erpnext_rd.tests import test_isc
from erpnext_rd.tests.test_isc import EMPRESA

EJERCICIO = 2023


class TestLiquidacionActivos(UnitTestCase):
	def test_casillas_del_formulario(self):
		# 32 = 10 000 000 - 2 500 000 + 300 000 = 7 800 000; 33 = 1 % = 78 000
		r = ir2.liquidar_activos(10_000_000, 2_500_000, 300_000, 1, 50_000)
		self.assertEqual((r.activos_imponibles, r.impuesto_activos), (7_800_000, 78_000))
		# 35 = 78 000 - 50 000 (ISR liquidado); en dos cuotas iguales
		self.assertEqual((r.credito_isr_activos, r.activos_pagar, r.activos_cuota), (50_000, 28_000, 14_000))
		# 38 = 35 - pagos a cuenta y créditos autorizados
		self.assertEqual(
			ir2.liquidar_activos(10_000_000, 2_500_000, 300_000, 1, 50_000, 8_000).activos_pagar, 20_000
		)

	def test_el_isr_liquidado_extingue_el_impuesto(self):
		# Art. 407, párrafo I: si el ISR liquidado es igual o mayor, no hay nada que pagar
		r = ir2.liquidar_activos(5_000_000, 0, 0, 1, 80_000)
		self.assertEqual((r.impuesto_activos, r.activos_pagar, r.activos_cuota), (50_000, 0, 0))

	def test_sin_base_negativa(self):
		r = ir2.liquidar_activos(1_000_000, 3_000_000, 0, 1, 0)
		self.assertEqual((r.activos_imponibles, r.impuesto_activos), (0, 0))


class TestImpuestoActivosEnElCuadre(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		test_isc.TestISC.setUpClass()

	def setUp(self):
		frappe.db.savepoint("impuesto_activos")
		frappe.db.delete(ir2.DOCTYPE, {"company": EMPRESA, "ejercicio": EJERCICIO})

	def tearDown(self):
		frappe.db.rollback(save_point="impuesto_activos")
		frappe.clear_document_cache(perfil.DOCTYPE, EMPRESA)

	def _sector(self, sector):
		perfil.guardar(EMPRESA, {"sector_activos": sector})
		frappe.clear_document_cache(perfil.DOCTYPE, EMPRESA)

	def _cuadre(self):
		return frappe.get_doc({"doctype": ir2.DOCTYPE, "company": EMPRESA, "ejercicio": EJERCICIO}).insert()

	def test_sector_general_desde_el_anexo_a1(self):
		self._sector(perfil.ACTIVOS_GENERAL)
		c = self._cuadre()
		a1 = estados_ir2.calcular(EMPRESA, c.desde, c.hasta)
		self.assertEqual(c.activos_totales, a1.totales_a1["6"])
		self.assertEqual(
			c.activos_exentos, round(sum(a1.a1.get(x, 0) for x in ("2.2", "2.6", "3.2", "4.2")), 2)
		)
		self.assertEqual((c.sector_activos, c.activos_exento, c.tasa_activos), (perfil.ACTIVOS_GENERAL, 0, 1))

		# Los montos se corrigen a mano y la liquidación se rehace
		c.update(
			{
				"activos_totales": 20_000_000,
				"activos_exentos": 4_000_000,
				"activos_depreciacion_exentos": 0,
				"beneficio_contable": 200_000,
				"anticipos_pagados": 0,
			}
		)
		c.save()
		self.assertEqual((c.activos_imponibles, c.impuesto_activos), (16_000_000, 160_000))
		self.assertEqual(c.credito_isr_activos, c.impuesto_liquidado)
		self.assertEqual(c.activos_pagar, round(160_000 - c.impuesto_liquidado, 2))
		self.assertEqual(c.activos_cuota, round(c.activos_pagar / 2, 2))

	def test_agropecuaria_exenta(self):
		self._sector(perfil.ACTIVOS_AGROPECUARIO)
		c = self._cuadre()
		c.activos_totales = 20_000_000
		c.save()
		self.assertEqual(c.activos_exento, 1)
		self.assertEqual((c.activos_imponibles, c.impuesto_activos, c.activos_pagar), (0, 0, 0))

	def test_exenta_del_isr_tambien_de_los_activos(self):
		self._sector(perfil.ACTIVOS_GENERAL)
		c = self._cuadre()
		c.update({"activos_totales": 20_000_000, "exencion_total": 1})
		c.save()
		self.assertEqual((c.activos_exento, c.impuesto_activos), (1, 0))

	def test_financiera_o_electrica_sobre_activos_fijos_netos(self):
		self._sector(perfil.ACTIVOS_FIJOS_NETOS)
		c = self._cuadre()
		a1 = estados_ir2.calcular(EMPRESA, c.desde, c.hasta).a1
		fijos = sum(a1.get(x, 0) for x in ("2.1", "2.3", "2.4", "2.5"))
		depreciacion = sum(a1.get(x, 0) for x in ("5.1", "5.3", "5.4"))
		self.assertEqual(c.activos_totales, round(fijos - depreciacion, 2))
		self.assertEqual((c.activos_exentos, c.activos_depreciacion_exentos), (0, 0))

	def test_formato_impreso(self):
		self._sector(perfil.ACTIVOS_GENERAL)
		c = self._cuadre()
		c.update({"activos_totales": 20_000_000, "activos_exentos": 0})
		c.save()
		html = frappe.get_print(ir2.DOCTYPE, c.name, ir2.FORMATO["name"])
		self.assertIn("Impuesto sobre los activos (IR-2-c2)", html)
		self.assertIn("32. Activos imponibles", html)
