"""Licitaciones del Estado (Fase 10.6): adjudicaciones, pedido de venta, precios de referencia y
retenciones.

Sin red: las respuestas de la API de la DGCP se simulan con la estructura de `/contratos`.
"""

from datetime import timedelta
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from erpnext_rd.licitaciones import adjudicaciones, ofertas, procesos, proveedor
from erpnext_rd.tests.test_licitaciones import EMPRESA, crear_empresa
from erpnext_rd.tests.test_licitaciones_ofertas import PROCESO, crear_proceso

RPE_PROPIO, RPE_OTRO = "99001", "88002"


def contrato(rpe: str, valor: float = 950_000, **otros) -> dict:
	return {
		"codigo_contrato": f"_T-CONT-{rpe}",
		"codigo_proceso": PROCESO,
		"estado_contrato": "Activo",
		"estado_adjudicacion": "Confirmada y enviada",
		"fecha_adjudicacion": "2026-11-10T22:07:36.21Z",
		"divisa": "DOP",
		"valor_contratado": valor,
		"metodo_pago": "Transferencia",
		"plazo_pago_factura": "60 días",
		"url_contrato": "https://comunidad.comprasdominicana.gob.do/contrato",
		"rpe": rpe,
		"razon_social": "Proveedora de Prueba, SRL" if rpe == RPE_PROPIO else "Competidora, SRL",
		**otros,
	}


class TestAdjudicaciones(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		crear_empresa()
		ofertas.asegurar_configuracion()

	def setUp(self):
		frappe.db.savepoint("adjudicaciones")
		frappe.get_doc(
			{
				"doctype": proveedor.DOCTYPE,
				"company": EMPRESA,
				"rpe": RPE_PROPIO,
				"estado_rpe": "Activo",
				"rubros": [{"familia_unspsc": "24110000"}],
			}
		).insert()
		self.tasa = patch.object(ofertas, "_tasa", return_value=1.0)
		self.tasa.start()
		self.commit = patch.object(frappe.db, "commit")
		self.commit.start()

	def tearDown(self):
		self.commit.stop()
		self.tasa.stop()
		frappe.db.rollback(save_point="adjudicaciones")
		frappe.clear_document_cache(proveedor.DOCTYPE, EMPRESA)

	def _oferta(self, estado: str, cierre_dias: int = -1):
		crear_proceso(PROCESO, fecha_fin_recepcion_ofertas=now_datetime() + timedelta(days=cierre_dias))
		nombre = ofertas.crear_oportunidad(PROCESO, EMPRESA)
		frappe.db.set_value(ofertas.DOCTYPE, nombre, "rd_estado_oferta", estado)
		return nombre

	def _resolver(self, filas):
		proceso = frappe.get_doc(procesos.DOCTYPE, PROCESO)
		adjudicaciones.guardar_contratos(proceso, filas)
		adjudicaciones.resolver(proceso)
		return frappe.db.get_value(ofertas.DOCTYPE, {"rd_proceso_dgcp": PROCESO}, "rd_estado_oferta")

	def test_ganada(self):
		self._oferta(ofertas.PRESENTADA)
		self.assertEqual(self._resolver([contrato(RPE_OTRO), contrato(RPE_PROPIO)]), adjudicaciones.GANADA)
		proceso = frappe.get_doc(procesos.DOCTYPE, PROCESO)
		self.assertEqual(len(proceso.contratos), 2)
		self.assertEqual(proceso.contratos[1].valor_contratado, 950_000)

	def test_perdida(self):
		self._oferta(ofertas.PRESENTADA)
		self.assertEqual(self._resolver([contrato(RPE_OTRO)]), adjudicaciones.PERDIDA)

	def test_no_presentada(self):
		self._oferta(ofertas.EN_PREPARACION)
		self.assertEqual(self._resolver([contrato(RPE_OTRO)]), adjudicaciones.NO_PRESENTADA)

	def test_sin_contratos_no_cambia(self):
		self._oferta(ofertas.PRESENTADA)
		self.assertEqual(self._resolver([]), ofertas.PRESENTADA)

	def test_seguimiento_en_la_sincronizacion(self):
		self._oferta(ofertas.PRESENTADA)
		consultas = []

		def api(ruta, **p):
			consultas.append((ruta, p.get("proceso")))
			if ruta == "contratos":
				return [contrato(RPE_PROPIO)]
			return []

		with patch.object(adjudicaciones.api_dgcp, "consultar", side_effect=api):
			self.assertEqual(adjudicaciones.seguir_adjudicaciones(), 1)
		self.assertIn(("contratos", PROCESO), consultas)
		self.assertEqual(
			frappe.db.get_value(ofertas.DOCTYPE, {"rd_proceso_dgcp": PROCESO}, "rd_estado_oferta"),
			adjudicaciones.GANADA,
		)
		# Ya ganada: no se vuelve a seguir
		self.assertEqual(adjudicaciones.seguidos(), [])

	def test_proceso_abierto_no_se_sigue(self):
		self._oferta(ofertas.PRESENTADA, cierre_dias=5)
		self.assertEqual(adjudicaciones.seguidos(), [])

	def test_pedido_de_venta(self):
		nombre = self._oferta(ofertas.PRESENTADA)
		self.assertRaises(frappe.ValidationError, adjudicaciones.crear_pedido, nombre)
		self._resolver([contrato(RPE_PROPIO)])
		pedido = adjudicaciones.crear_pedido(nombre)
		oportunidad = frappe.get_doc(ofertas.DOCTYPE, nombre)
		self.assertEqual(pedido.doctype, "Sales Order")
		self.assertEqual(
			(pedido.customer, pedido.company, pedido.po_no, pedido.rd_proceso_dgcp),
			(oportunidad.party_name, EMPRESA, f"_T-CONT-{RPE_PROPIO}", PROCESO),
		)
		self.assertEqual((pedido.items[0].item_name, pedido.items[0].qty), ("Fundas negras 30 galones", 500))

	def test_precios_de_referencia(self):
		crear_proceso(PROCESO)
		frappe.db.set_value(
			"Articulo Proceso DGCP", {"parent": PROCESO}, "subclase_unspsc", "24111503", update_modified=False
		)
		frappe.cache.delete_value("erpnext_rd:adjudicatarios:_T-OTRO-1")

		def api(ruta, **p):
			if ruta == "contratos/articulos":
				return [
					{
						"codigo_proceso": f"_T-OTRO-{n % 2}",
						"descripcion_articulo": "Bolsas",
						"unidad_medida": "Unidad",
						"cantidad": 10,
						"precio_unitario": precio,
						"fecha_creacion_contrato": "2026-11-01T12:00:00Z",
					}
					for n, precio in enumerate((10, 30, 20))
				] + [{"codigo_proceso": PROCESO, "precio_unitario": 999, "unidad_medida": "Unidad"}]
			if ruta == "contratos":
				return [{"razon_social": "Ganadora, SRL"}]
			return []

		with patch.object(adjudicaciones.api_dgcp, "consultar", side_effect=api):
			grupos = adjudicaciones.precios_referencia(PROCESO)
		self.assertEqual(len(grupos), 1)
		# El propio proceso no cuenta como referencia
		self.assertEqual(
			grupos[0]["resumen"],
			[{"unidad": "Unidad", "contratos": 3, "minimo": 10, "mediana": 20, "maximo": 30}],
		)
		self.assertEqual(grupos[0]["filas"][0]["adjudicatario"], "Ganadora, SRL")

	def test_retencion_esperada(self):
		conf = frappe._dict(pct_retencion_isr=5, base_retencion_isr="Sin ITBIS", isr_exento_con_ecf=1)
		pago = frappe._dict(
			references=[
				frappe._dict(reference_doctype="Sales Invoice", reference_name="F1", allocated_amount=1180),
				frappe._dict(reference_doctype="Sales Invoice", reference_name="F2", allocated_amount=590),
			]
		)
		facturas = {
			"F1": frappe._dict(grand_total=1180, net_total=1000),
			"F2": frappe._dict(grand_total=1180, net_total=1000),
		}
		with (
			patch.object(adjudicaciones, "_factura", side_effect=facturas.get),
			patch.object(adjudicaciones, "_ecf_aceptado", side_effect=lambda f: f == "F2"),
		):
			# F1: 5 % de 1,000; F2 tiene e-CF aceptado: sin retención
			self.assertEqual(adjudicaciones.isr_esperado(pago, conf), 50)
			conf.isr_exento_con_ecf = 0
			conf.base_retencion_isr = "Con ITBIS"
			# Con ITBIS: 5 % de 1,180 y la mitad de F2 (cobro parcial)
			self.assertAlmostEqual(adjudicaciones.isr_esperado(pago, conf), 59 + 29.5)

	def test_aviso_apagado_por_defecto(self):
		self.assertFalse(frappe.utils.cint(ofertas.configuracion().avisar_retenciones))
