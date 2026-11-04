"""Licitaciones del Estado (Fase 10.2): cliente de la API de la DGCP y perfil de proveedor.

Sin red: las respuestas imitan las de la API (estructura probada el 2026-11-04) con datos ficticios.
"""

from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, today

from erpnext_rd.licitaciones import api_dgcp, proveedor
from erpnext_rd.rd_compliance import recordatorios

EMPRESA = "_Test Proveedor Estado RD"
RNC = "101003723"

FILA_RPE = {
	"rpe": 99001,
	"razon_social": "Proveedora de Prueba, SRL",
	"tipo_documento": "RNC",
	"numero_documento": RNC,
	"estado": "Activo",
	"fecha_registro_rpe": "2007-10-23T04:00:00Z",
	"es_mipyme": "Si",
	"certificacion_micm": "Si",
	"fecha_vencimiento_certificacion_micm": "2027-05-26T04:00:00Z",
	"clasificacion": "Pequeña empresa",
	"clasificacion_empresarial": "Pequeña Empresa",
	"provee": "Bienes,Servicios",
	"url_certificacion": "https://www.dgcp.gob.do/constancia/descargar/1",
}
RUBROS = [
	{"rpe": 99001, "familia_unspsc": "24110000", "descripcion": "Recipientes y almacenamiento"},
	{"rpe": 99001, "familia_unspsc": "44110000", "descripcion": "Accesorios de oficina y escritorio"},
]


class Respuesta:
	def __init__(self, contenido, status=200, encabezados=None, error=False, mensaje=None):
		self.status_code = status
		self.headers = {"x-ratelimit-remaining": "59", "x-ratelimit-reset": "60", **(encabezados or {})}
		self._json = {
			"code": status,
			"hasError": error,
			"payload": {"content": contenido, "message": mensaje},
		}
		self.content = b"{}"

	def json(self):
		return self._json


def api_falsa(ruta: str, **parametros) -> list[dict]:
	if ruta == "proveedores":
		return [FILA_RPE] if parametros.get("numero_documento") == RNC else []
	if ruta == "proveedores/rubro":
		return RUBROS
	return []


def crear_empresa():
	"""Empresa RD de prueba (la usan también los tests de procesos)."""
	if not frappe.db.exists("Company", EMPRESA):
		frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": EMPRESA,
				"abbr": "TPER",
				"country": "Dominican Republic",
				"default_currency": "DOP",
				"tax_id": RNC,
				"chart_of_accounts": "Standard",
				"create_chart_of_accounts_based_on": "Standard Template",
			}
		).insert()


class TestApiDGCP(IntegrationTestCase):
	def test_contenido_y_sin_resultados(self):
		with patch.object(api_dgcp.requests, "get", return_value=Respuesta([{"rpe": 1}])) as get:
			self.assertEqual(api_dgcp.consultar("proveedores", numero_documento=RNC), [{"rpe": 1}])
			self.assertEqual(get.call_args.kwargs["params"], {"numero_documento": RNC})
		# Sin resultados la API devuelve content null
		with patch.object(api_dgcp.requests, "get", return_value=Respuesta(None)):
			self.assertEqual(api_dgcp.consultar("procesos", proceso="NO-EXISTE"), [])

	def test_error_de_la_api(self):
		malo = Respuesta(None, status=400, error=True, mensaje="El Type debe ser xlsx (excel) o csv (texto)")
		with patch.object(api_dgcp.requests, "get", return_value=malo):
			with self.assertRaisesRegex(api_dgcp.ErrorAPIDGCP, "Type"):
				api_dgcp.consultar("tablas/procesos", Type="json")

	def test_espera_si_se_agota_el_limite(self):
		respuestas = [
			Respuesta(None, status=429, encabezados={"x-ratelimit-reset": "7"}),
			Respuesta([{"rpe": 1}]),
		]
		with (
			patch.object(api_dgcp.requests, "get", side_effect=respuestas),
			patch.object(api_dgcp.time, "sleep") as sleep,
		):
			self.assertEqual(api_dgcp.consultar("proveedores"), [{"rpe": 1}])
		sleep.assert_called_once_with(7)

	def test_todas_las_paginas(self):
		paginas = {1: [{"n": 1}, {"n": 2}], 2: [{"n": 3}]}
		with patch.object(api_dgcp, "consultar", side_effect=lambda ruta, page, limit, **p: paginas[page]):
			self.assertEqual([f["n"] for f in api_dgcp.todas("procesos", limite=2)], [1, 2, 3])


class TestPerfilProveedorEstado(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		crear_empresa()

	def setUp(self):
		frappe.db.savepoint("proveedor_estado")

	def tearDown(self):
		frappe.db.rollback(save_point="proveedor_estado")
		frappe.clear_document_cache(proveedor.DOCTYPE, EMPRESA)

	def _perfil(self, **valores):
		return frappe.get_doc({"doctype": proveedor.DOCTYPE, "company": EMPRESA, **valores}).insert()

	def _estados(self) -> dict[str, str]:
		return {r["requisito"]: r["estado"] for r in proveedor.requisitos(EMPRESA)}

	def test_consultar_rpe_llena_el_perfil_y_conserva_los_rubros_manuales(self):
		self._perfil(
			rubros=[
				{"familia_unspsc": "44110000"},
				{"familia_unspsc": "31200000", "descripcion": "Adhesivos"},
			]
		)
		with patch.object(api_dgcp, "consultar", side_effect=api_falsa):
			proveedor.consultar_rpe(EMPRESA)
		doc = frappe.get_doc(proveedor.DOCTYPE, EMPRESA)
		self.assertEqual(
			(doc.rpe, doc.estado_rpe, doc.razon_social_rpe), ("99001", "Activo", "Proveedora de Prueba, SRL")
		)
		self.assertEqual(str(doc.fecha_registro_rpe), "2007-10-23")
		self.assertEqual(
			(doc.es_mipyme, doc.certificacion_micm, str(doc.vencimiento_micm)), (1, 1, "2027-05-26")
		)
		self.assertEqual(doc.provee, "Bienes, Servicios")
		rubros = {r.familia_unspsc: r.origen for r in doc.rubros}
		# 44110000 ya estaba a mano, pero está en el RPE: queda como del RPE y sin repetir
		self.assertEqual(rubros, {"24110000": "RPE", "44110000": "RPE", "31200000": "Manual"})

		# Si la familia sale del RPE, deja de estar en el perfil; la manual sigue
		with (
			patch.object(api_dgcp, "consultar", side_effect=api_falsa),
			patch.object(api_dgcp, "rubros", return_value=RUBROS[:1]),
		):
			proveedor.consultar_rpe(EMPRESA)
		doc.reload()
		self.assertEqual({r.familia_unspsc for r in doc.rubros}, {"24110000", "31200000"})

	def test_rnc_que_no_esta_en_el_rpe(self):
		self._perfil()
		with (
			patch.object(api_dgcp, "consultar", return_value=[]),
			self.assertRaisesRegex(frappe.ValidationError, "no está inscrito"),
		):
			proveedor.actualizar_rpe(EMPRESA)

	def test_familia_unspsc_valida_y_sin_repetir(self):
		with self.assertRaisesRegex(frappe.ValidationError, "8 dígitos"):
			self._perfil(rubros=[{"familia_unspsc": "24111503"}])
		with self.assertRaisesRegex(frappe.ValidationError, "repetida"):
			self._perfil(rubros=[{"familia_unspsc": "24110000"}, {"familia_unspsc": " 24110000"}])

	def test_requisitos(self):
		self._perfil()
		r = self._estados()
		self.assertEqual(r["Inscrito en el RPE"], proveedor.FALTA)
		self.assertEqual(r["Rubros"], proveedor.FALTA)
		self.assertNotIn("RPE activo", r)

		doc = frappe.get_doc(proveedor.DOCTYPE, EMPRESA)
		proveedor.aplicar_rpe(doc, FILA_RPE | {"estado": "Desactualizado"}, RUBROS)
		doc.dgii_al_dia_hasta = add_days(today(), 30)
		doc.tss_al_dia_hasta = add_days(today(), -1)
		doc.save()
		r = self._estados()
		self.assertEqual(r["Inscrito en el RPE"], proveedor.CUMPLIDO)
		self.assertEqual(r["RPE activo"], proveedor.FALTA)
		self.assertEqual(r["Rubros"], proveedor.CUMPLIDO)
		self.assertEqual(r["Al día con la DGII"], proveedor.CUMPLIDO)
		self.assertEqual(r["Al día con la TSS"], proveedor.FALTA)
		self.assertIn("Certificación MIPYME del MICM", r)

	def test_recordatorio_de_vencimientos(self):
		hoy = date(2026, 11, 4)
		self._perfil(dgii_al_dia_hasta=add_days(hoy, 5), tss_al_dia_hasta=hoy)
		with patch.object(recordatorios, "_con_nomina", return_value=False):
			avisos = {o["obligacion"]: o["faltan"] for o in recordatorios.pendientes(EMPRESA, hoy, 5)}
		self.assertEqual(avisos["Certificación de la DGII para proveedores del Estado"], 5)
		self.assertEqual(avisos["Certificación de la TSS para proveedores del Estado"], 0)

		# Un perfil desactivado no avisa
		frappe.db.set_value(proveedor.DOCTYPE, EMPRESA, "habilitado", 0)
		frappe.clear_document_cache(proveedor.DOCTYPE, EMPRESA)
		self.assertEqual(proveedor.vencimientos(EMPRESA), [])

	def test_tarea_semanal_sigue_si_una_empresa_falla(self):
		self._perfil()
		with (
			patch.object(
				proveedor, "actualizar_rpe", side_effect=api_dgcp.ErrorAPIDGCP("caída")
			) as actualizar,
			patch.object(frappe.db, "rollback"),
			patch.object(frappe, "log_error") as log_error,
		):
			proveedor.actualizar_perfiles()
		actualizar.assert_called_once_with(EMPRESA)
		log_error.assert_called_once()
