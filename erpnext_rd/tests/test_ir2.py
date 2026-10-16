"""Cálculos del cuadre fiscal del IR-2 con los ejemplos del instructivo de la DGII."""

import json
import os

from frappe.tests import UnitTestCase

from erpnext_rd.dgii_reportes import ir2


class TestCalculosIR2(UnitTestCase):
	def test_edificaciones_ejemplos_del_instructivo(self):
		# Edificio adquirido el 2/6/2018 por 3,500,000: 7 meses en servicio
		r = ir2.depreciar_edificacion(0, 0, 3_500_000, "2018-06-02", None, "2018-01-01", "2018-12-31", 5)
		self.assertEqual((r.meses, r.base, r.depreciacion), (7, 2_041_666.67, 102_083.33))
		self.assertEqual(r.costo_final, 3_397_916.67)

		# Mejora de 1,860,000 en servicio desde el 1/8/2018: 5 meses
		r = ir2.depreciar_edificacion(0, 0, 1_860_000, "2018-08-01", None, "2018-01-01", "2018-12-31", 5)
		self.assertEqual((r.base, r.depreciacion, r.costo_final), (775_000, 38_750, 1_821_250))

		# Retiro de un edificio de 1,740,000 el 30/4/2018: 4 meses
		r = ir2.depreciar_edificacion(1_740_000, 0, 0, None, "2018-04-30", "2018-01-01", "2018-12-31", 5)
		self.assertEqual((r.meses, r.base, r.depreciacion, r.costo_final), (4, 580_000, 29_000, 1_711_000))

		# Edificio de años anteriores con una mejora en el año: el costo anterior, todo el año
		r = ir2.depreciar_edificacion(
			1_000_000, 50_000, 120_000, "2026-10-01", None, "2026-01-01", "2026-12-31", 5
		)
		self.assertEqual(r.base, 1_050_000 + 30_000)
		self.assertEqual(r.depreciacion, 54_000)

	def test_cuentas_de_categorias_2_y_3(self):
		# Balance 400,000 + ajuste 20,000 + mitad de 100,000 de adiciones - retiros 10,000 = 460,000
		r = ir2.depreciar_cuenta(400_000, 20_000, 100_000, 10_000, 25)
		self.assertEqual((r.adiciones_imponibles, r.adicion_no_depreciada), (50_000, 50_000))
		self.assertEqual((r.base, r.depreciacion), (460_000, 115_000))
		self.assertEqual(r.costo_final, 460_000 - 115_000 + 50_000)

		# Retiros mayores que el balance: sin depreciación (la diferencia es renta)
		r = ir2.depreciar_cuenta(10_000, 0, 0, 25_000, 15)
		self.assertEqual((r.base, r.depreciacion), (-15_000, 0))

	def test_ajuste_por_inflacion(self):
		valores = [(ir2.INVENTARIO, 1_000_000), (ir2.CATEGORIA_1, 3_000_000), (ir2.TERRENO, 0)]
		# Patrimonio mayor: la base son los activos no monetarios
		r = ir2.distribuir_ajuste(5_000_000, valores, 1.0495)
		self.assertEqual((r.activos_no_monetarios, r.base, r.ajuste), (4_000_000, 4_000_000, 198_000))
		self.assertEqual(
			[(f.concepto, f.ajuste) for f in r.filas], [(ir2.INVENTARIO, 49_500), (ir2.CATEGORIA_1, 148_500)]
		)
		# Patrimonio menor: la base es el patrimonio y el reparto suma exactamente el ajuste
		r = ir2.distribuir_ajuste(1_000_000, [("a", 1), ("b", 1), ("c", 1)], 1.0335)
		self.assertEqual((r.base, r.ajuste), (3, 0.1))
		r = ir2.distribuir_ajuste(1_000_003, [("a", 1_000_000), ("b", 1_000_000), ("c", 1_000_000)], 1.0335)
		self.assertAlmostEqual(sum(f.ajuste for f in r.filas), r.ajuste, places=2)
		# Patrimonio negativo o sin multiplicador: no hay ajuste
		self.assertEqual(ir2.distribuir_ajuste(-5, valores, 1.05).ajuste, 0)
		self.assertEqual(ir2.distribuir_ajuste(5_000_000, valores, 0).ajuste, 0)

	def test_liquidacion(self):
		r = ir2.liquidar(1_000_000, 200_000, 100_000, 50_000, 27, 100_000)
		self.assertEqual((r.renta_antes_perdidas, r.renta_neta_imponible), (1_100_000, 1_050_000))
		self.assertEqual((r.impuesto_liquidado, r.diferencia_pagar, r.saldo_favor), (283_500, 183_500, 0))
		r = ir2.liquidar(-300_000, 0, 0, 0, 27, 40_000)
		self.assertEqual((r.renta_neta_imponible, r.impuesto_liquidado, r.saldo_favor), (0, 0, 40_000))

	def test_meses_en_servicio(self):
		self.assertEqual(ir2.meses_en_servicio("2026-01-01", "2026-12-31"), 12)
		self.assertEqual(ir2.meses_en_servicio("2025-07-01", "2026-06-30"), 12)  # cierre a junio
		self.assertEqual(ir2.meses_en_servicio("2026-12-31", "2026-12-31"), 1)
		self.assertEqual(ir2.meses_en_servicio("2027-01-01", "2026-12-31"), 0)

	def test_conceptos_del_anexo_g_en_el_doctype(self):
		ruta = os.path.join(
			os.path.dirname(ir2.__file__),
			"..",
			"dgii_fiscal",
			"doctype",
			"ajuste_fiscal_ir2",
			"ajuste_fiscal_ir2.json",
		)
		campos = {f["fieldname"]: f for f in json.load(open(ruta, encoding="utf8"))["fields"]}
		opciones = campos["concepto"]["options"].split("\n")
		self.assertEqual(opciones, [*ir2.CONCEPTOS_POSITIVOS, *ir2.CONCEPTOS_NEGATIVOS])
		self.assertTrue(set(ir2.CONCEPTOS_CALCULADOS) <= set(opciones))
