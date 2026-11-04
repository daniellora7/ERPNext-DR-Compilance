"""Licitaciones del Estado (Fases 10.3 y 10.4): descarga de procesos de compra y alertas por correo.

Sin red: la API de la DGCP se simula con datos ficticios con la estructura de sus respuestas.
"""

from datetime import datetime, timedelta
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, get_datetime, now_datetime

from erpnext_rd.licitaciones import alertas, api_dgcp, procesos, proveedor
from erpnext_rd.tests.test_licitaciones import EMPRESA, crear_empresa


def utc(dt: datetime) -> str:
	"""Fecha local (UTC-4) en el formato de la API."""
	return (dt + timedelta(hours=4)).strftime("%Y-%m-%dT%H:%M:%SZ")


AHORA = get_datetime("2026-11-04 10:00:00")
NUEVO, VIEJO, ABIERTO, AJENO = (
	"_T-DAF-CM-2026-0001",
	"_T-DAF-CM-2026-0002",
	"_T-DAF-CM-2026-0003",
	"_T-DAF-CM-2026-0004",
)


def fila_proceso(codigo: str, publicado: datetime, **otros) -> dict:
	return {
		"codigo_proceso": codigo,
		"codigo_unidad_compra": 171,
		"unidad_compra": "Institución de Prueba",
		"modalidad": "Contratación Menor",
		"tipo_excepcion": "Proceso ordinario",
		"titulo": f"Adquisición de fundas plásticas {codigo}",
		"descripcion": "Fundas para basura",
		"estado_proceso": "Proceso publicado",
		"divisa": "DOP",
		"monto_estimado": 150000,
		"fecha_publicacion": utc(publicado),
		"fecha_fin_recepcion_ofertas": utc(publicado + timedelta(days=7)),
		"dirigido_mipymes": "Si",
		"dirigido_mipymes_mujeres": "No",
		"url": f"https://comunidad.comprasdominicana.gob.do/{codigo}",
		**otros,
	}


def articulo(codigo: str, publicado: datetime, familia: str = "24110000") -> dict:
	return {
		"codigo_proceso": codigo,
		"fecha_publicacion": utc(publicado),
		"familia_unspsc": familia,
		"clase_unspsc": familia[:6] + "00",
		"subclase_unspsc": familia[:6] + "03",
		"descripcion_articulo": "Bolsas plásticas",
		"descripcion_usuario": "Fundas negras 30 galones",
		"cantidad": 100,
		"unidad_medida": "Unidad",
		"precio_unitario_estimado": 1000,
		"precio_total_estimado": 100000,
	}


class ApiSimulada:
	"""Responde como la API según la ruta y los parámetros, y anota las consultas."""

	def __init__(self):
		self.consultas = []
		self.detalle = {
			NUEVO: fila_proceso(NUEVO, AHORA - timedelta(hours=5)),
			ABIERTO: fila_proceso(
				ABIERTO, AHORA - timedelta(days=30), estado_proceso="Proceso adjudicado y celebrado"
			),
		}

	def __call__(self, ruta: str, **p) -> list[dict]:
		self.consultas.append((ruta, p))
		if ruta == "procesos/articulos" and p.get("familia") == "24110000":
			return [articulo(NUEVO, AHORA - timedelta(hours=5)), articulo(VIEJO, AHORA - timedelta(days=40))]
		if ruta == "procesos/articulos" and p.get("proceso") == NUEVO:
			return [articulo(NUEVO, AHORA), articulo(NUEVO, AHORA, "44110000")]
		if ruta == "procesos" and p.get("startdate"):
			return [self.detalle[NUEVO], fila_proceso(AJENO, AHORA)]
		if ruta == "procesos" and p.get("proceso"):
			return [self.detalle[p["proceso"]]] if p["proceso"] in self.detalle else []
		return []


class TestProcesosCompraDGCP(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		crear_empresa()

	def setUp(self):
		frappe.db.savepoint("procesos_dgcp")
		self.perfil = frappe.get_doc(
			{
				"doctype": proveedor.DOCTYPE,
				"company": EMPRESA,
				"rubros": [{"familia_unspsc": "24110000"}],
				"destinatarios_alertas": "compras@example.com",
			}
		).insert()
		conf = frappe.get_single(procesos.CONFIGURACION)
		conf.ultima_sincronizacion = AHORA - timedelta(days=1)
		conf.dias_aviso_cierre = 3
		conf.save()
		self.zona = patch("frappe.utils.data.get_system_timezone", return_value="America/Santo_Domingo")
		self.zona.start()
		# Las corridas guardan con commit: aquí no, para deshacer todo al final
		self.commit = patch.object(frappe.db, "commit")
		self.commit.start()

	def tearDown(self):
		self.commit.stop()
		self.zona.stop()
		frappe.db.rollback(save_point="procesos_dgcp")
		frappe.clear_document_cache(proveedor.DOCTYPE, EMPRESA)

	def _sincronizar(self, api=None):
		api = api or ApiSimulada()
		with (
			patch.object(api_dgcp, "consultar", side_effect=api),
			patch.object(procesos, "now_datetime", return_value=AHORA),
		):
			return procesos.sincronizar(), api

	def test_fecha_de_la_api_en_hora_local(self):
		self.assertEqual(
			procesos.fecha_local("2026-11-04T08:01:08.4633333Z"), datetime(2026, 11, 4, 4, 1, 8, 463333)
		)
		self.assertEqual(procesos.fecha_local("2026-11-11T08:00:00Z"), datetime(2026, 11, 11, 4, 0))
		self.assertIsNone(procesos.fecha_local(None))

	def test_solo_los_procesos_de_los_rubros_desde_el_corte(self):
		resultado, api = self._sincronizar()
		self.assertEqual(resultado["nuevos"], 1)
		self.assertTrue(frappe.db.exists(procesos.DOCTYPE, NUEVO))
		# Anterior al corte (última sincronización menos 2 días) y de otro rubro: no se guardan
		self.assertFalse(frappe.db.exists(procesos.DOCTYPE, VIEJO))
		self.assertFalse(frappe.db.exists(procesos.DOCTYPE, AJENO))
		inicio = [p for r, p in api.consultas if r == "procesos" and p.get("startdate")]
		self.assertEqual(inicio[0]["startdate"], "2026-11-01")

		doc = frappe.get_doc(procesos.DOCTYPE, NUEVO)
		self.assertEqual(doc.fecha_publicacion, AHORA - timedelta(hours=5))
		self.assertEqual((doc.divisa, doc.monto_estimado, doc.dirigido_mipymes), ("DOP", 150000, 1))
		# Todos los artículos del proceso, no solo los del rubro
		self.assertEqual(len(doc.articulos), 2)
		self.assertEqual([(e.company, e.familias) for e in doc.empresas], [(EMPRESA, "24110000")])
		conf = frappe.get_single(procesos.CONFIGURACION)
		self.assertEqual(get_datetime(conf.ultima_sincronizacion), AHORA)

	def test_actualiza_los_abiertos_y_no_duplica(self):
		self._sincronizar()
		procesos.guardar(fila_proceso(ABIERTO, AHORA - timedelta(days=30)), [], {EMPRESA: {"24110000"}})
		api = ApiSimulada()
		api.detalle[NUEVO] = api.detalle[NUEVO] | {"estado_proceso": "Sobres abiertos o aperturados"}
		resultado, api = self._sincronizar(api)
		self.assertEqual(resultado, {"nuevos": 0, "actualizados": 2})
		self.assertEqual(
			frappe.db.get_value(procesos.DOCTYPE, ABIERTO, "estado_proceso"), "Proceso adjudicado y celebrado"
		)
		self.assertEqual(
			frappe.db.get_value(procesos.DOCTYPE, NUEVO, "estado_proceso"), "Sobres abiertos o aperturados"
		)
		# Un proceso que ya existe no vuelve a pedir sus artículos
		self.assertNotIn(("procesos/articulos", {"proceso": NUEVO, "page": 1, "limit": 1000}), api.consultas)
		self.assertEqual(len(frappe.get_doc(procesos.DOCTYPE, NUEVO).articulos), 2)

	def test_sin_perfiles_activos_no_consulta(self):
		frappe.db.set_value(proveedor.DOCTYPE, EMPRESA, "habilitado", 0)
		resultado, api = self._sincronizar()
		self.assertEqual(resultado, {"nuevos": 0, "actualizados": 0})
		self.assertEqual(api.consultas, [])

	def _proceso(self, codigo: str, cierre: datetime, **otros):
		fila = fila_proceso(codigo, AHORA - timedelta(days=1), **otros)
		fila["fecha_fin_recepcion_ofertas"] = utc(cierre)
		procesos.guardar(fila, [], {EMPRESA: {"24110000"}})

	def test_alertas_nuevos_filtrados_y_por_cerrar(self):
		base = now_datetime()
		self._proceso(NUEVO, base + timedelta(days=10))
		self._proceso(VIEJO, base + timedelta(days=10), titulo="Servicio de limpieza", descripcion="")
		self._proceso(ABIERTO, base + timedelta(days=10), monto_estimado=5_000_000)
		# Después de crearlos: la próxima alerta solo cuenta los creados desde esta
		ahora = now_datetime()
		self.perfil.reload()
		self.perfil.palabras_clave = "FUNDAS\nplasticas"
		self.perfil.monto_maximo = 1_000_000
		self.perfil.save()

		with patch.object(frappe, "sendmail") as sendmail:
			self.assertEqual(alertas.enviar_alertas(ahora), 1)
		correo = sendmail.call_args.kwargs
		self.assertEqual(correo["recipients"], ["compras@example.com"])
		# Palabra clave sin tildes ni mayúsculas; el de limpieza y el de 5 millones no van
		self.assertIn(NUEVO, correo["message"])
		self.assertNotIn(VIEJO, correo["message"])
		self.assertNotIn(ABIERTO, correo["message"])

		# Al día siguiente no hay nuevos; el que cierra en 2 días va aunque no pase los filtros
		frappe.db.set_value(
			procesos.DOCTYPE, VIEJO, "fecha_fin_recepcion_ofertas", add_days(ahora, 2) + timedelta(hours=1)
		)
		with patch.object(frappe, "sendmail") as sendmail:
			self.assertEqual(alertas.enviar_alertas(add_days(ahora, 1)), 1)
		mensaje = sendmail.call_args.kwargs["message"]
		self.assertIn(VIEJO, mensaje)
		self.assertNotIn(NUEVO, mensaje)

		# Sin nada que avisar no hay correo
		with patch.object(frappe, "sendmail") as sendmail:
			self.assertEqual(alertas.enviar_alertas(add_days(ahora, 5)), 0)
		sendmail.assert_not_called()

	def test_documentos_del_proceso(self):
		self._proceso(NUEVO, AHORA + timedelta(days=7))
		filas = [
			{
				"nombre_documento": "Pliego.pdf",
				"tipo_documento": "Pliego de condiciones",
				"fecha_carga_archivo": "2026-11-03T21:31:37.4056956Z",
				"url_documento": "https://comunidad.comprasdominicana.gob.do/Public/Archive/RetrieveFile/Index?DocumentId=1",
			}
		]
		with patch.object(api_dgcp, "consultar", return_value=filas):
			docs = procesos.documentos(NUEVO)
		self.assertEqual(docs[0]["nombre"], "Pliego.pdf")
		self.assertEqual(docs[0]["fecha"], datetime(2026, 11, 3, 17, 31, 37, 405695))
