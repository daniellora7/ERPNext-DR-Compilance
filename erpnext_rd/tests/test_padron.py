import io
import zipfile
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from erpnext_rd.padron_rnc import padron
from erpnext_rd.padron_rnc.padron import parsear_linea

VERSION = "Sat, 10 Oct 2026 07:02:47 GMT"
VERSION_OTRO_SERVIDOR = "Sat, 10 Oct 2026 07:02:49 GMT"
VERSION_NUEVA = "Sat, 17 Oct 2026 07:00:00 GMT"


def respuesta_dgii(status: int, version: str | None = None) -> MagicMock:
	"""Respuesta simulada del servidor de la DGII (sin descargar nada)."""
	contenido = b""
	if status == 200:
		buffer = io.BytesIO()
		with zipfile.ZipFile(buffer, "w") as z:
			z.writestr(
				"DGII_RNC.TXT", "101010632|EMPRESA DE PRUEBA||COMERCIO| | | | |01/01/2000|ACTIVO|NORMAL\n"
			)
		contenido = buffer.getvalue()
	r = MagicMock(
		status_code=status, content=contenido, headers={"Last-Modified": version} if version else {}
	)
	r.raise_for_status.return_value = None
	return r


class TestPadron(UnitTestCase):
	def test_parsear_linea(self):
		fila = parsear_linea(
			"03101823817|MARCO SERGIO RICARDO||SERVICIOS PERSONALES| | | | |25/06/2003|ACTIVO|NORMAL\r\n"
		)
		self.assertEqual(
			fila,
			(
				"03101823817",
				"MARCO SERGIO RICARDO",
				"",
				"SERVICIOS PERSONALES",
				"25/06/2003",
				"ACTIVO",
				"NORMAL",
			),
		)

	def test_linea_invalida(self):
		self.assertIsNone(parsear_linea("ROOM ARCE|X||Y| | | | ||ACTIVO|NORMAL"))
		self.assertIsNone(parsear_linea("101010632|incompleta"))

	def test_sincronizacion_diaria_a_las_2am(self):
		"""El padrón se actualiza cada día a las 2:00 a. m. y pasa por `encolar` (cola long, 1 h)."""
		from erpnext_rd import hooks

		self.assertEqual(
			hooks.scheduler_events["cron"]["0 2 * * *"], ["erpnext_rd.padron_rnc.padron.encolar"]
		)
		self.assertNotIn("weekly_long", hooks.scheduler_events)

	def test_mismo_archivo_aunque_el_servidor_ignore_la_condicion(self):
		"""Si el servidor responde 200 con el mismo Last-Modified, no se importa de nuevo."""
		with patch.object(padron.requests, "get", return_value=respuesta_dgii(200, VERSION)):
			self.assertEqual(padron.descargar_padron(VERSION), (None, VERSION))

	def test_copia_de_otro_servidor_es_la_misma_version(self):
		"""Los servidores de la DGII publican el mismo archivo con segundos de diferencia."""
		with patch.object(
			padron.requests, "get", return_value=respuesta_dgii(200, VERSION_OTRO_SERVIDOR)
		) as get:
			self.assertEqual(padron.descargar_padron(VERSION), (None, VERSION))
		# Se pide con el margen, así esos servidores responden 304 sin enviar el archivo
		self.assertEqual(
			get.call_args.kwargs["headers"]["If-Modified-Since"], "Sat, 10 Oct 2026 08:02:47 GMT"
		)

	def test_version_nueva_se_descarga(self):
		with patch.object(padron.requests, "get", return_value=respuesta_dgii(200, VERSION_NUEVA)):
			contenido, version = padron.descargar_padron(VERSION)
		self.assertTrue(contenido)
		self.assertEqual(version, VERSION_NUEVA)


class TestSincronizacionPadron(IntegrationTestCase):
	"""La tarea diaria solo descarga e importa si la DGII publicó un padrón nuevo."""

	def setUp(self):
		# sincronizar_padron hace commit: aquí no, para que el rollback del test lo deshaga todo
		self.commit = patch.object(frappe.db, "commit")
		self.commit.start()
		self.addCleanup(self.commit.stop)
		if not frappe.get_all("Contribuyente DGII", limit=1):
			frappe.get_doc({"doctype": "Contribuyente DGII", "rnc": "101010632"}).insert()
		frappe.db.set_single_value(
			"Configuracion DGII", {"padron_version_dgii": VERSION, "padron_ultima_verificacion": None}
		)

	def sincronizar(self, respuesta, **kwargs):
		with (
			patch.object(padron.requests, "get", return_value=respuesta) as get,
			patch.object(padron, "importar_padron", return_value=5) as importar,
		):
			total = padron.sincronizar_padron(**kwargs)
		return total, get.call_args.kwargs["headers"], importar

	def config(self, campo):
		return frappe.db.get_single_value("Configuracion DGII", campo)

	def test_sin_cambios_no_descarga(self):
		total, encabezados, importar = self.sincronizar(respuesta_dgii(304))
		self.assertIsNone(total)
		self.assertEqual(encabezados["If-Modified-Since"], "Sat, 10 Oct 2026 08:02:47 GMT")
		importar.assert_not_called()
		self.assertEqual(self.config("padron_version_dgii"), VERSION)
		self.assertTrue(self.config("padron_ultima_verificacion"))

	def test_version_nueva_importa(self):
		total, _, importar = self.sincronizar(respuesta_dgii(200, VERSION_NUEVA))
		self.assertEqual(total, 5)
		importar.assert_called_once()
		self.assertEqual(self.config("padron_version_dgii"), VERSION_NUEVA)
		self.assertEqual(self.config("padron_registros"), 5)

	def test_boton_fuerza_la_descarga(self):
		"""El botón de Configuración DGII descarga aunque la versión sea la misma."""
		total, encabezados, importar = self.sincronizar(respuesta_dgii(200, VERSION), forzar=True)
		self.assertNotIn("If-Modified-Since", encabezados)
		self.assertEqual(total, 5)
		importar.assert_called_once()


class TestListaPadron(IntegrationTestCase):
	def test_lista_sin_filtro_de_recientes(self):
		"""La lista del padrón no se filtra sola por "últimos 90 días" (tabla grande)."""
		self.assertEqual(
			frappe.db.get_value(
				"List View Settings", "Contribuyente DGII", "disable_automatic_recency_filters"
			),
			1,
		)


class TestBusquedaPorPalabras(IntegrationTestCase):
	"""Índice FULLTEXT del padrón. InnoDB solo ve en MATCH lo que ya tiene commit: la prueba guarda dos
	contribuyentes de verdad y los borra al terminar."""

	RNCS = ("999200001", "999200002")

	def setUp(self):
		for rnc, nombre, comercial in (
			(self.RNCS[0], "ZQXW ALMACENES DEL CIBAO SRL", "ZQXW TIENDA"),
			(self.RNCS[1], "INVERSIONES ZQXW CIBAO SA", ""),
		):
			if not frappe.db.exists("Contribuyente DGII", rnc):
				frappe.get_doc(
					{
						"doctype": "Contribuyente DGII",
						"rnc": rnc,
						"razon_social": nombre,
						"nombre_comercial": comercial,
						"estado": "ACTIVO",
					}
				).insert()
		frappe.db.commit()  # nosemgrep: frappe-manual-commit
		self.addCleanup(self._borrar)

	def _borrar(self):
		frappe.db.delete("Contribuyente DGII", {"rnc": ("in", self.RNCS)})
		frappe.db.commit()  # nosemgrep: frappe-manual-commit

	def test_consulta(self):
		self.assertEqual(padron.consulta_por_palabras("Ochoa, ferret y SA"), "+Ochoa* +ferret*")
		self.assertEqual(padron.consulta_por_palabras("de la"), "")

	def test_indice_creado(self):
		self.assertTrue(frappe.db.has_index("tabContribuyente DGII", "busqueda_nombre"))

	def test_palabras_en_cualquier_orden_y_posicion(self):
		rncs = lambda texto, **kw: sorted(c.rnc for c in padron.buscar_por_palabras(texto, **kw))  # noqa: E731
		self.assertEqual(rncs("cibao zqxw"), list(self.RNCS))
		self.assertEqual(rncs("zqxw almac"), [self.RNCS[0]])
		self.assertEqual(rncs("zqxw tienda"), [self.RNCS[0]])  # nombre comercial
		self.assertEqual(rncs("cibao zqxw", excluir={self.RNCS[0]}), [self.RNCS[1]])
		self.assertEqual(rncs("zq"), [])

	def test_buscar_emisor_completa_con_palabras(self):
		from erpnext_rd.captura_compras.api import buscar_emisor

		# Ninguno empieza con «cibao zqxw»: los trae el FULLTEXT
		self.assertEqual(sorted(e.rnc for e in buscar_emisor("cibao zqxw")), list(self.RNCS))
