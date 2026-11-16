"""IR-1 de la persona física con negocio (Fase 8.8): casillas del instructivo de la DGII."""

import frappe
from frappe.tests import IntegrationTestCase

from erpnext_rd.dgii_reportes import anticipos, ir1
from erpnext_rd.nomina_rd import calculos
from erpnext_rd.rd_compliance import perfil, recordatorios
from erpnext_rd.tests import test_isc
from erpnext_rd.tests.test_isc import EMPRESA

EJERCICIO = 2026


class TestIR1(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		test_isc.TestISC.setUpClass()

	def setUp(self):
		frappe.db.savepoint("ir1")
		perfil.guardar(EMPRESA, {"tipo_contribuyente": perfil.FISICA, "regimen": perfil.ORDINARIO})
		frappe.clear_document_cache(perfil.DOCTYPE, EMPRESA)
		frappe.db.delete(ir1.DOCTYPE, {"company": EMPRESA})
		frappe.db.delete(anticipos.DOCTYPE, {"company": EMPRESA})

	def tearDown(self):
		frappe.db.rollback(save_point="ir1")
		frappe.clear_document_cache(perfil.DOCTYPE, EMPRESA)

	def _cuadre(self, **valores):
		c = frappe.get_doc({"doctype": ir1.DOCTYPE, "company": EMPRESA, "ejercicio": EJERCICIO}).insert()
		if valores:
			c.update(valores)
			c.save()
		return c

	def test_casillas(self):
		c = self._cuadre(
			beneficio_contable=1_500_000,
			gastos_no_admitidos=100_000,
			ingresos_exentos=50_000,
			dividendos=50_000,
			anticipos_pagados=20_000,
			retenciones=30_000,
		)
		# 5 = 1 500 000 + 100 000 - 50 000 - 50 000; con contabilidad no hay exención contributiva
		self.assertEqual(
			(c.renta_neta, c.exencion_contributiva, c.renta_imponible), (1_500_000, 0, 1_500_000)
		)
		self.assertEqual(c.impuesto_liquidado, calculos.isr_anual(1_500_000, anio=EJERCICIO))
		self.assertEqual(c.diferencia_pagar, round(c.impuesto_liquidado - 50_000, 2))

	def test_exencion_contributiva_y_tope_de_educacion(self):
		exento = ir1.exencion_contributiva(EJERCICIO)
		self.assertEqual(exento, 416_220)  # escala 2026
		self.assertEqual(ir1.exencion_contributiva(2027), 480_000)  # Ley 30-26
		c = self._cuadre(beneficio_contable=1_000_000, sin_contabilidad=1, gastos_educacion=500_000)
		self.assertEqual(c.exencion_contributiva, exento)
		# Tope: 10% de (5 - 6) = 58 378 y 25% de la exención = 104 055 → 58 378
		self.assertEqual(c.gastos_educacion, round((1_000_000 - exento) * 0.10, 2))
		self.assertEqual(c.renta_imponible, round(1_000_000 - exento - c.gastos_educacion, 2))

	def test_saldo_a_favor(self):
		c = self._cuadre(beneficio_contable=100_000, retenciones=25_000)
		self.assertEqual((c.impuesto_liquidado, c.diferencia_pagar, c.saldo_favor), (0, 0, 25_000))

	def test_solo_persona_fisica_del_regimen_ordinario(self):
		perfil.guardar(EMPRESA, {"tipo_contribuyente": perfil.JURIDICA})
		frappe.clear_document_cache(perfil.DOCTYPE, EMPRESA)
		self.assertRaises(frappe.ValidationError, self._cuadre)

	def test_base_de_anticipos_en_tres_cuotas(self):
		c = self._cuadre(beneficio_contable=1_500_000, retenciones=30_000)
		base = frappe.get_doc(anticipos.DOCTYPE, ir1.crear_base_anticipos(c.name))
		self.assertEqual(base.regimen, anticipos.TRES_CUOTAS)
		# Párrafo IV: sobre el impuesto que no se pagó por retención
		self.assertEqual(base.cuota_mensual, round(c.impuesto_liquidado - 30_000, 2))
		junio = anticipos.anticipo(EMPRESA, EJERCICIO + 1, 6)
		self.assertEqual((junio.cuota, str(junio.vence)), (round(base.cuota_mensual * 0.5, 2), "2027-06-30"))

	def test_recordatorio_del_31_de_marzo(self):
		obligaciones = recordatorios.obligaciones(EMPRESA, EJERCICIO, 12)
		ir1s = [o for o in obligaciones if o["obligacion"].startswith("IR-1 (")]
		self.assertEqual(len(ir1s), 1)
		self.assertEqual(str(ir1s[0]["vence"]), str(ir1.fecha_limite(EJERCICIO)))
		self.assertFalse(any(o["obligacion"].startswith("IR-2 (") for o in obligaciones))
