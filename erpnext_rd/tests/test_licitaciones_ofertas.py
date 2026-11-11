"""Licitaciones del Estado (Fase 10.5): seguimiento de ofertas con Opportunity.

Sin red: los procesos se crean directamente, como los deja la descarga de la DGCP.
"""

from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, now_datetime, today

from erpnext_rd.licitaciones import alertas, ofertas, panel, procesos, proveedor
from erpnext_rd.licitaciones.report.ofertas_estado import ofertas_estado
from erpnext_rd.tests.test_licitaciones import EMPRESA, crear_empresa

PROCESO, OBRA = "_T-OFE-CP-2026-0001", "_T-OFE-SO-2026-0002"
UNIDAD = 99171


def crear_proceso(codigo: str, **valores):
	doc = frappe.get_doc(
		{
			"doctype": procesos.DOCTYPE,
			"codigo_proceso": codigo,
			"titulo": f"Adquisición de fundas plásticas {codigo}",
			"unidad_compra": "_Test Institución de Ofertas",
			"codigo_unidad_compra": UNIDAD,
			"modalidad": "Comparación de Precios",
			"objeto_proceso": "Bienes",
			"estado_proceso": "Proceso publicado",
			"divisa": "DOP",
			"monto_estimado": 1_000_000,
			"fecha_publicacion": now_datetime(),
			"fecha_fin_recepcion_ofertas": now_datetime() + timedelta(days=10),
			"url": f"https://comunidad.comprasdominicana.gob.do/{codigo}",
			"empresas": [{"company": EMPRESA, "familias": "24110000"}],
			"articulos": [
				{
					"familia_unspsc": "24110000",
					"descripcion_articulo": "Bolsas plásticas",
					"descripcion_usuario": "Fundas negras 30 galones",
					"cantidad": 500,
					"precio_unitario_estimado": 1500,
				},
				{
					"familia_unspsc": "24110000",
					"descripcion_articulo": "Bolsas plásticas",
					"cantidad": 250,
					"precio_unitario_estimado": 1000,
				},
			],
			**valores,
		}
	)
	doc.insert(ignore_permissions=True)
	return doc


class TestOfertasEstado(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		crear_empresa()
		ofertas.asegurar_configuracion()

	def setUp(self):
		frappe.db.savepoint("ofertas_estado")
		self.perfil = frappe.get_doc(
			{
				"doctype": proveedor.DOCTYPE,
				"company": EMPRESA,
				"estado_rpe": "Activo",
				"dgii_al_dia_hasta": add_days(today(), 60),
				"tss_al_dia_hasta": add_days(today(), 5),
				"rubros": [{"familia_unspsc": "24110000"}],
				"destinatarios_alertas": "compras@example.com",
			}
		).insert()
		self.conf = ofertas.configuracion()
		self.conf.update(
			{
				"pct_seriedad": 1,
				"pct_fiel_cumplimiento": 4,
				"pct_fiel_cumplimiento_mipyme": 1,
				"umbral_fiel_cumplimiento_usd": 10000,
				"pct_anticipo_mipyme": 30,
				"pct_garantia_anticipo": 100,
				"pct_vicios_ocultos": 10,
				"modalidades_sin_seriedad": "Sorteo de Obras\nSubasta Inversa",
				"dias_aviso_cierre": 3,
				"dias_aviso_garantias": 15,
			}
		)
		self.conf.save()
		# Sin tasa del dólar en el sitio de pruebas: 60 pesos por dólar
		self.tasa = patch.object(ofertas, "_tasa", side_effect=lambda a, b: 1.0 if a == b else 60.0)
		self.tasa.start()

	def tearDown(self):
		self.tasa.stop()
		frappe.db.rollback(save_point="ofertas_estado")
		frappe.clear_document_cache(proveedor.DOCTYPE, EMPRESA)

	def _oferta(self, codigo=PROCESO, **valores):
		if not frappe.db.exists(procesos.DOCTYPE, codigo):
			crear_proceso(codigo, **valores)
		return frappe.get_doc(ofertas.DOCTYPE, ofertas.crear_oportunidad(codigo, EMPRESA))

	def _estados(self, doc) -> dict:
		return {d.requisito or d.documento: d.estado for d in doc.rd_documentos_oferta}

	def test_crear_oportunidad(self):
		doc = self._oferta()
		self.assertEqual(doc.rd_estado_oferta, ofertas.EVALUANDO)
		self.assertEqual(
			(doc.opportunity_from, doc.currency, doc.opportunity_amount), ("Customer", "DOP", 1_000_000)
		)
		self.assertEqual(getdate(doc.expected_closing), getdate(add_days(today(), 10)))
		self.assertEqual(len(doc.items), 2)
		primero = doc.items[0]
		self.assertEqual(
			(primero.item_name, primero.qty, primero.rate), ("Fundas negras 30 galones", 500, 1500)
		)

		# La institución queda como cliente con el comprobante gubernamental
		cliente = frappe.get_doc("Customer", doc.party_name)
		self.assertEqual((cliente.rd_unidad_compra_dgcp, cliente.rd_tipo_comprobante), (UNIDAD, "B15"))

		# No MIPYME: seriedad 1 % y fiel cumplimiento 4 % sobre el monto
		self.assertEqual(
			[(g.tipo, g.porcentaje, g.monto) for g in doc.rd_garantias],
			[(ofertas.SERIEDAD, 1, 10_000), (ofertas.FIEL_CUMPLIMIENTO, 4, 40_000)],
		)
		self.assertIsNone(doc.rd_garantias[1].notas)

		# Documentos: sin el de MIPYME; los del perfil marcados (la TSS vence antes del cierre)
		estados = self._estados(doc)
		self.assertNotIn(ofertas.CERT_MIPYME, estados)
		self.assertEqual(estados[ofertas.RPE_ACTIVO], ofertas.LISTO)
		self.assertEqual(estados[ofertas.CERT_DGII], ofertas.LISTO)
		self.assertEqual(estados[ofertas.CERT_TSS], ofertas.PENDIENTE)
		self.assertEqual(estados[ofertas.GARANTIA_SERIEDAD], ofertas.PENDIENTE)

		# Una oferta por empresa y proceso; otro proceso de la misma institución usa el mismo cliente
		self.assertEqual(ofertas.crear_oportunidad(PROCESO, EMPRESA), doc.name)
		otra = self._oferta(OBRA)
		self.assertEqual(otra.party_name, doc.party_name)

	def test_mipyme_y_obras(self):
		self.perfil.update(
			{"es_mipyme": 1, "certificacion_micm": 1, "vencimiento_micm": add_days(today(), 90)}
		)
		self.perfil.save()
		doc = self._oferta(
			OBRA, modalidad="Sorteo de Obras", objeto_proceso="Obras", monto_estimado=2_000_000
		)
		self.assertTrue(doc.rd_oferta_mipyme)
		# Sin seriedad (MIPYME y sorteo de obras), fiel cumplimiento 1 %, anticipo y vicios ocultos; solo fianza
		self.assertEqual(
			[(g.tipo, g.base, g.monto, g.instrumento) for g in doc.rd_garantias],
			[
				(ofertas.FIEL_CUMPLIMIENTO, 2_000_000, 20_000, ofertas.FIANZA),
				(ofertas.ANTICIPO, 600_000, 600_000, ofertas.FIANZA),
				(ofertas.VICIOS_OCULTOS, 2_000_000, 200_000, ofertas.FIANZA),
			],
		)
		estados = self._estados(doc)
		self.assertEqual(estados[ofertas.CERT_MIPYME], ofertas.LISTO)
		self.assertEqual(estados[ofertas.GARANTIA_SERIEDAD], ofertas.NO_APLICA)

	def test_fiel_cumplimiento_bajo_el_umbral(self):
		# RD$300,000 a 60 por dólar = US$5,000: solo si el pliego la pide
		doc = self._oferta(monto_estimado=300_000)
		fiel = next(g for g in doc.rd_garantias if g.tipo == ofertas.FIEL_CUMPLIMIENTO)
		self.assertIn("10,000", fiel.notas)

	def test_monto_de_la_oferta_y_presentada(self):
		doc = self._oferta()
		doc.rd_monto_oferta = 900_000
		doc.save()
		self.assertEqual([g.monto for g in doc.rd_garantias], [9_000, 36_000])

		# Presentada con documentos obligatorios pendientes: no se guarda
		doc.rd_estado_oferta = ofertas.PRESENTADA
		self.assertRaises(frappe.ValidationError, doc.save)

		doc.reload()
		self.perfil.tss_al_dia_hasta = add_days(today(), 60)
		self.perfil.save()
		for d in doc.rd_documentos_oferta:
			if not d.requisito:
				d.estado = ofertas.LISTO
		doc.rd_garantias[0].estado = "Emitida"
		doc.rd_estado_oferta = ofertas.PRESENTADA
		doc.save()
		self.assertEqual(getdate(doc.rd_fecha_presentacion), getdate(today()))
		self.assertFalse(ofertas.documentos_pendientes(doc))

	def test_cambios_del_proceso(self):
		doc = self._oferta()
		proceso = frappe.get_doc(procesos.DOCTYPE, PROCESO)
		nuevo_cierre = (now_datetime() + timedelta(days=15)).replace(microsecond=0)
		proceso.fecha_fin_recepcion_ofertas = nuevo_cierre
		proceso.save(ignore_permissions=True)
		ofertas.actualizar_desde_proceso(proceso)
		doc.reload()
		self.assertEqual(doc.rd_cierre_ofertas, nuevo_cierre)
		self.assertTrue(
			frappe.db.exists(
				"Comment",
				{
					"reference_doctype": ofertas.DOCTYPE,
					"reference_name": doc.name,
					"content": ("like", "%cierre%"),
				},
			)
		)

		proceso.estado_proceso = "Proceso desierto"
		proceso.save(ignore_permissions=True)
		ofertas.actualizar_desde_proceso(proceso)
		self.assertEqual(frappe.db.get_value(ofertas.DOCTYPE, doc.name, "rd_estado_oferta"), ofertas.DESIERTO)

	def test_alertas_y_reporte(self):
		doc = self._oferta(fecha_fin_recepcion_ofertas=now_datetime() + timedelta(days=2))
		doc.rd_garantias[0].update(
			{"estado": "Emitida", "vigencia_hasta": add_days(today(), 5), "emisor": "Aseguradora de Prueba"}
		)
		doc.save()
		with patch.object(frappe, "sendmail") as sendmail:
			self.assertEqual(alertas.enviar_alertas(now_datetime()), 1)
		mensaje = sendmail.call_args.kwargs["message"]
		self.assertIn(doc.name, mensaje)
		self.assertIn("Aseguradora de Prueba", mensaje)
		# El proceso no se repite en «Dejan de recibir ofertas pronto»: ya va como oferta
		self.assertNotIn(f"proceso-compra-dgcp/{PROCESO}", mensaje)

		fila = next(
			f for f in ofertas_estado.datos(frappe._dict(company=EMPRESA)) if f["oportunidad"] == doc.name
		)
		self.assertEqual((fila["proceso"], fila["documentos_pendientes"]), (PROCESO, 3))
		self.assertEqual(fila["garantias_por_gestionar"], 1)

	def test_bloque_del_panel(self):
		doc = self._oferta()
		crear_proceso(OBRA)
		bloque = panel.resumen(EMPRESA)
		self.assertEqual([o["oportunidad"] for o in bloque["ofertas"]], [doc.name])
		# El proceso con oferta no sale como nuevo; el otro sí
		self.assertEqual([p["name"] for p in bloque["nuevos"]], [OBRA])
		self.assertEqual(bloque["garantias"], [])

		# Sin perfil activo la empresa no vende al Estado: no hay bloque
		self.perfil.habilitado = 0
		self.perfil.save()
		self.assertIsNone(panel.resumen(EMPRESA))
