"""Perfil tributario por empresa: requisitos, exigencia y lo que cambia según el régimen."""

from datetime import date

import frappe
from frappe.tests import IntegrationTestCase

from erpnext_rd.rd_compliance import perfil

EMPRESA = "_Test Perfil RD"


def estados(company: str) -> dict[str, str]:
	return {r["requisito"]: r["estado"] for r in perfil.evaluar(company)}


class TestPerfilTributario(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Company", EMPRESA):
			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": EMPRESA,
					"abbr": "TPRD",
					"country": "Dominican Republic",
					"default_currency": "DOP",
					"tax_id": "101003723",
					"chart_of_accounts": "Standard",
					"create_chart_of_accounts_based_on": "Standard Template",
				}
			).insert()

	def setUp(self):
		frappe.db.savepoint("perfil_rd")

	def tearDown(self):
		frappe.db.rollback(save_point="perfil_rd")
		frappe.clear_document_cache(perfil.DOCTYPE, EMPRESA)

	def test_sin_perfil_es_persona_juridica_del_regimen_ordinario(self):
		p = perfil.perfil(EMPRESA)
		self.assertFalse(p.existe)
		self.assertTrue(perfil.declara_ir2(EMPRESA))
		self.assertFalse(perfil.emisor_electronico(EMPRESA))
		self.assertEqual(perfil.cierre(EMPRESA), (12, 31))
		self.assertEqual(estados(EMPRESA)["Perfil tributario completo"], perfil.FALTA)
		estado = perfil.estado_empresa(EMPRESA)
		self.assertEqual((estado["aplica"], estado["existe"]), (True, False))
		self.assertGreater(estado["faltan"], 0)

	def test_asistente_y_requisitos(self):
		perfil.guardar(EMPRESA, {"tamano": perfil.PEQUENA, "cierre_fiscal": "31 de diciembre", "ignorado": 1})
		self.assertTrue(perfil.perfil(EMPRESA).existe)
		r = estados(EMPRESA)
		self.assertEqual(r["Perfil tributario completo"], perfil.CUMPLIDO)
		self.assertEqual(r["RNC de la empresa"], perfil.CUMPLIDO)
		self.assertEqual(perfil.perfil(EMPRESA).sector_regulado, perfil.SIN_SECTOR_REGULADO)
		self.assertFalse([x for x in r if x.startswith("Reportes del sector regulado")])

		# Sin secuencias: faltan las de venta; con la de B01 ya no se pide
		detalle = {x["requisito"]: x["detalle"] for x in perfil.evaluar(EMPRESA)}
		self.assertIn("B01", detalle["Secuencias NCF de venta vigentes"])
		frappe.get_doc(
			{
				"doctype": "Secuencia NCF",
				"company": EMPRESA,
				"tipo_comprobante": "B01",
				"desde": 1,
				"hasta": 10,
				"fecha_vencimiento": "2099-12-31",
			}
		).insert()
		detalle = {x["requisito"]: x["detalle"] for x in perfil.evaluar(EMPRESA)}
		self.assertNotIn("B01", detalle["Secuencias NCF de venta vigentes"])
		self.assertIn("B02", detalle["Secuencias NCF de venta vigentes"])

		# Cierre a junio: el año fiscal de ERPNext (calendario) ya no coincide
		perfil.guardar(EMPRESA, {"cierre_fiscal": "30 de junio"})
		if perfil.anio_fiscal(EMPRESA, frappe.utils.today()):
			self.assertEqual(estados(EMPRESA)["Año fiscal según el cierre"], perfil.FALTA)
		self.assertEqual(perfil.periodo_fiscal(EMPRESA, "2026-10-18"), (date(2026, 7, 1), date(2027, 6, 30)))

	def test_emisor_electronico_vende_con_serie_e(self):
		from erpnext_rd.dgii_fiscal import ncf

		perfil.guardar(EMPRESA, {"tamano": perfil.GRANDE, "ecf_estado": perfil.ECF_EMISOR, "exportador": 1})
		self.assertEqual(ncf.serie_por_defecto(EMPRESA), "E")
		self.assertEqual(perfil.tipos_de_venta(EMPRESA), ["E31", "E32", "E34", "E46"])
		self.assertEqual(estados(EMPRESA)["Emisor e-CF con certificado vigente"], perfil.FALTA)

		factura = frappe._dict(company=EMPRESA, is_return=0, is_debit_note=0)
		with self.assertRaises(frappe.ValidationError):
			perfil.validar_serie_de_venta(factura, frappe._dict(name="B01", serie="B"))
		perfil.validar_serie_de_venta(factura, frappe._dict(name="E31", serie="E"))
		# La nota de crédito de una factura B de antes sigue en la serie B
		perfil.validar_serie_de_venta(frappe._dict(factura, is_return=1), frappe._dict(name="B04", serie="B"))

	def test_lo_que_la_app_aun_no_cubre(self):
		perfil.guardar(
			EMPRESA,
			{
				"tamano": perfil.MEDIANA,
				"regimen": perfil.RST,
				"isc_alcohol": 1,
				"partes_relacionadas": 1,
				"propina_legal": 1,
				"sector_regulado": "Seguros",
			},
		)
		r = estados(EMPRESA)
		self.assertEqual(r["Impuesto selectivo al consumo (ISC)"], perfil.PENDIENTE_APP)
		self.assertEqual(r["Operaciones con partes relacionadas (DIOR)"], perfil.PENDIENTE_APP)
		self.assertEqual(r["Régimen simplificado de tributación (RST)"], perfil.PENDIENTE_APP)
		self.assertEqual(r["Reportes del sector regulado (Seguros)"], perfil.FUERA_ALCANCE)
		# El catálogo DGII trae la plantilla de propina; sin plantillas activas, falta
		frappe.db.set_value(
			"Sales Taxes and Charges Template", {"company": EMPRESA}, "disabled", 1, update_modified=False
		)
		self.assertEqual(estados(EMPRESA)["Plantilla de propina legal"], perfil.FALTA)
		# El RST no declara el IR-2: sin cuadre, sin recordatorio y sin reglas del IR-2
		self.assertFalse(perfil.declara_ir2(EMPRESA))
		self.assertNotIn("Casillas del IR-2 en el catálogo de cuentas", r)
		with self.assertRaises(frappe.ValidationError):
			frappe.get_doc({"doctype": "Cuadre Fiscal IR2", "company": EMPRESA, "ejercicio": 2026}).insert()
		from erpnext_rd.rd_compliance import recordatorios

		self.assertFalse(
			[o for o in recordatorios.obligaciones(EMPRESA, 2026, 12) if o["obligacion"].startswith("IR-2")]
		)

	def test_cierre_del_perfil_sin_anio_fiscal(self):
		from erpnext_rd.dgii_reportes import ir2

		perfil.guardar(EMPRESA, {"tamano": perfil.MICRO, "cierre_fiscal": "30 de junio"})
		# 2040: ningún año fiscal de ERPNext lo cubre, manda el cierre del perfil
		self.assertEqual(ir2.cierre_fiscal(EMPRESA, 2040, 6), date(2040, 6, 30))
		self.assertIsNone(ir2.cierre_fiscal(EMPRESA, 2040, 12))

	def test_solo_empresas_de_rd(self):
		otra = frappe.db.get_value("Company", {"country": ("!=", "Dominican Republic")})
		if otra:
			with self.assertRaises(frappe.ValidationError):
				frappe.get_doc({"doctype": perfil.DOCTYPE, "company": otra}).insert()
			self.assertEqual(perfil.estado_empresa(otra), {"aplica": False})

	def test_perfil_en_la_empresa(self):
		"""La empresa muestra su perfil (solo lectura) con el resumen como título del enlace."""
		perfil.guardar(EMPRESA, {"regimen": "Simplificado (RST)"})
		self.assertEqual(frappe.db.get_value("Company", EMPRESA, "rd_perfil_tributario"), EMPRESA)
		self.assertEqual(
			frappe.db.get_value(perfil.DOCTYPE, EMPRESA, "resumen"),
			"Persona jurídica · Régimen Simplificado (RST)",
		)
		frappe.delete_doc(perfil.DOCTYPE, EMPRESA)
		self.assertIsNone(frappe.db.get_value("Company", EMPRESA, "rd_perfil_tributario"))

	def test_configuracion_solo_para_administradores(self):
		"""La configuración fiscal y de e-CF la edita solo el System Manager; contabilidad solo la ve."""
		for doctype in (
			"Configuracion DGII",
			"Perfil Tributario RD",
			"Emisor ECF",
			"Set Pruebas ECF",
			"Secuencia NCF",
			"Tipo Comprobante Fiscal",
		):
			for regla in frappe.get_meta(doctype).permissions:
				if regla.role != "System Manager":
					self.assertFalse(regla.write or regla.create or regla.delete, f"{doctype}: {regla.role}")
