"""e-CF: anulación de rangos, contingencia, recepción de e-CF de proveedores con acuse y aprobación
comercial, entrega al comprador, servicios públicos del receptor y set de pruebas de CerteCF.

La DGII y los otros contribuyentes se simulan; los certificados son autofirmados."""

import copy
from typing import ClassVar
from unittest.mock import patch

import frappe
import requests
from frappe.tests import IntegrationTestCase
from frappe.utils import add_to_date, now_datetime
from lxml import etree

from erpnext_rd.ecf import certificacion, emision, esquemas, firma, recepcion
from erpnext_rd.tests.test_ecf import SEMILLA, Respuesta, certificado_de_prueba, datos_e31

EMPRESA = "_Test ECF RD"
RNC_EMPRESA = "130000001"
RNC_PROVEEDOR = "131880738"
RECEPTOR = "https://receptor.test"


class SesionCompleta:
	"""DGII y otro contribuyente simulados. `caida` hace que la DGII responda 503."""

	caida: ClassVar[bool] = False
	llamadas: ClassVar[list] = []

	def get(self, url, **kw):
		type(self).llamadas.append(("GET", url, kw))
		if url.endswith("/semilla"):
			return Respuesta(contenido=SEMILLA)
		if "consultadirectorio" in url:
			return Respuesta(
				[
					{
						"nombre": "Cliente",
						"urlRecepcion": RECEPTOR,
						"urlAceptacion": RECEPTOR,
						"urlOpcional": RECEPTOR,
					}
				]
			)
		return Respuesta({"trackId": "T-1", "codigo": 1, "estado": "Aceptado", "mensajes": []})

	def post(self, url, **kw):
		type(self).llamadas.append(("POST", url, kw))
		if url.endswith(("/validarsemilla", "/validacioncertificado")):
			assert firma.verificar(kw["files"]["xml"][1]), "la semilla debe llegar firmada"
			return Respuesta({"token": "TOKEN-1", "expira": "2099-01-01T00:00:00Z"})
		if url.startswith(RECEPTOR + "/fe/recepcion"):
			xml = kw["files"]["xml"][1]
			acuse = etree.Element("ARECF")
			detalle = etree.SubElement(acuse, "DetalleAcusedeRecibo")
			etree.SubElement(detalle, "Estado").text = "0"
			etree.SubElement(detalle, "eNCF").text = firma.leer(xml).findtext("Encabezado/IdDoc/eNCF")
			return Respuesta(contenido=etree.tostring(acuse))
		if url.startswith(RECEPTOR):
			return Respuesta({})
		if type(self).caida:
			return Respuesta({"mensaje": "Servicio no disponible"}, estado=503)
		if "anulacionrangos" in url:
			return Respuesta({"rnc": RNC_EMPRESA, "codigo": 1, "nombre": "Aceptado", "mensajes": []})
		if "aprobacioncomercial" in url:
			return Respuesta({"mensaje": ["Recibido"], "estado": "Aceptado"})
		if "recepcionfc" in url:
			return Respuesta({"codigo": 1, "estado": "Aceptado", "mensajes": []})
		return Respuesta({"trackId": "T-1", "error": None, "mensaje": None})


def dgii():
	return patch("erpnext_rd.ecf.cliente.requests.Session", SesionCompleta)


def ecf_del_proveedor(llave, cert, encf="E310000000077", comprador=RNC_EMPRESA) -> bytes:
	datos = datos_e31()
	datos["Encabezado"]["IdDoc"]["eNCF"] = encf
	datos["Encabezado"]["Emisor"]["RNCEmisor"] = RNC_PROVEEDOR
	datos["Encabezado"]["Comprador"]["RNCComprador"] = comprador
	return firma.firmar(esquemas.construir(31, datos), llave, cert)


def acuse(xml: bytes) -> tuple[str, str | None]:
	raiz = firma.leer(xml)
	return raiz.findtext("DetalleAcusedeRecibo/Estado"), raiz.findtext(
		"DetalleAcusedeRecibo/CodigoMotivoNoRecibido"
	)


class TestIntercambioECF(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Company", EMPRESA):
			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": EMPRESA,
					"abbr": "_TECF",
					"country": "Dominican Republic",
					"default_currency": "DOP",
					"tax_id": RNC_EMPRESA,
					"chart_of_accounts": "Standard",
					"create_chart_of_accounts_based_on": "Standard Template",
				}
			).insert()
		archivo = frappe.get_doc(
			{"doctype": "File", "file_name": "ecf.p12", "content": certificado_de_prueba(), "is_private": 1}
		).insert()
		frappe.get_doc(
			{
				"doctype": "Emisor ECF",
				"company": EMPRESA,
				"habilitado": 1,
				"certificado": archivo.file_url,
				"clave_certificado": "prueba",
			}
		).insert()
		cls.secuencia = frappe.get_doc(
			{
				"doctype": "Secuencia NCF",
				"company": EMPRESA,
				"tipo_comprobante": "E31",
				"desde": 1,
				"hasta": 100,
				"fecha_vencimiento": "2027-12-31",
			}
		).insert()
		# Certificado del proveedor (otro contribuyente)
		cls.llave_proveedor, cls.cert_proveedor = firma.cargar_certificado(certificado_de_prueba(), "prueba")
		frappe.db.set_single_value("Configuracion DGII", "ambiente_ecf", "TesteCF")

	def setUp(self):
		SesionCompleta.caida = False
		SesionCompleta.llamadas = []
		frappe.cache.delete_value(f"erpnext_rd:ecf_token:TesteCF:{RNC_EMPRESA}")

	# ------------------------------------------------------------ anulación

	def test_anulacion_de_rangos(self):
		anulacion = frappe.get_doc(
			{
				"doctype": "Anulacion ENCF",
				"company": EMPRESA,
				"rangos": [{"secuencia": self.secuencia.name, "desde": 1, "hasta": 10}],
			}
		).insert()
		fila = anulacion.rangos[0]
		self.assertEqual(
			(fila.encf_desde, fila.encf_hasta, fila.cantidad), ("E310000000001", "E310000000010", 10)
		)
		with dgii():
			anulacion.submit()
		anulacion.reload()
		self.assertEqual(anulacion.estado, "Aceptado")
		anecf = emision.leer_xml(anulacion.xml)
		self.assertEqual(esquemas.errores("ANECF", anecf), [])
		self.assertTrue(firma.verificar(anecf))
		self.assertEqual(firma.leer(anecf).findtext("Encabezado/CantidadeNCFAnulados"), "10")
		self.assertTrue(any("anulacionrangos" in u for _m, u, _k in SesionCompleta.llamadas))
		# La secuencia salta lo anulado
		self.assertEqual(frappe.db.get_value("Secuencia NCF", self.secuencia.name, "siguiente"), 11)

		repetida = frappe.get_doc(
			{
				"doctype": "Anulacion ENCF",
				"company": EMPRESA,
				"rangos": [{"secuencia": self.secuencia.name, "desde": 5, "hasta": 12}],
			}
		)
		self.assertRaises(frappe.ValidationError, repetida.insert)

	def test_no_anula_fuera_de_la_secuencia(self):
		doc = frappe.get_doc(
			{
				"doctype": "Anulacion ENCF",
				"company": EMPRESA,
				"rangos": [{"secuencia": self.secuencia.name, "desde": 90, "hasta": 101}],
			}
		)
		self.assertRaises(frappe.ValidationError, doc.insert)

	# ---------------------------------------------------------- contingencia

	def _envio(self, encf="E310000000050", estado="Firmado"):
		datos = datos_e31()
		datos["Encabezado"]["IdDoc"]["eNCF"] = encf
		datos["Encabezado"]["Emisor"]["RNCEmisor"] = RNC_EMPRESA
		envio = emision.registrar(
			frappe.get_doc("Emisor ECF", EMPRESA), 31, datos, {"fecha_firma": now_datetime()}
		)
		envio.db_set("estado", estado)
		return envio

	def test_contingencia_y_reintento(self):
		envio = self._envio()
		SesionCompleta.caida = True
		with dgii():
			emision.enviar_a_dgii(envio)
		envio.reload()
		self.assertEqual((envio.estado, envio.intentos), ("Contingencia", 1))
		self.assertGreater(envio.proximo_intento, now_datetime())

		# Todavía no es la hora: no se reintenta
		SesionCompleta.caida = False
		with dgii():
			emision.reintentar_contingencia()
		self.assertEqual(frappe.db.get_value("Envio ECF", envio.name, "estado"), "Contingencia")

		envio.db_set("proximo_intento", add_to_date(now_datetime(), minutes=-1))
		with dgii():
			emision.reintentar_contingencia()
		envio.reload()
		self.assertEqual((envio.estado, envio.track_id), ("En proceso", "T-1"))

	def test_error_de_la_solicitud_no_es_contingencia(self):
		envio = self._envio("E310000000051")

		class Rechaza(SesionCompleta):
			def post(self, url, **kw):
				if "facturaselectronicas" in url:
					return Respuesta({"mensaje": "XML mal formado"}, estado=400)
				return super().post(url, **kw)

		with patch("erpnext_rd.ecf.cliente.requests.Session", Rechaza):
			emision.enviar_a_dgii(envio)
		self.assertEqual(frappe.db.get_value("Envio ECF", envio.name, "estado"), "Error")

	def test_entrega_al_comprador(self):
		envio = self._envio("E310000000052", estado="Aceptado")
		with dgii():
			emision.entregar_a_compradores()
		envio.reload()
		self.assertEqual(envio.estado_comprador, "Recibido")
		self.assertTrue(envio.acuse_comprador)
		urls = [u for _m, u, _k in SesionCompleta.llamadas]
		self.assertIn(RECEPTOR + "/fe/recepcion/api/ecf", urls)
		self.assertIn(RECEPTOR + "/fe/autenticacion/api/validacioncertificado", urls)

	# ------------------------------------------------------------ recepción

	def test_recepcion_con_acuse(self):
		xml = ecf_del_proveedor(self.llave_proveedor, self.cert_proveedor)
		respuesta = recepcion.recibir_ecf(xml)
		self.assertTrue(firma.verificar(respuesta))
		self.assertEqual(esquemas.errores("ARECF", respuesta), [])
		self.assertEqual(acuse(respuesta), ("0", None))
		doc = frappe.get_doc("ECF Recibido", {"company": EMPRESA, "encf": "E310000000077"})
		self.assertEqual((doc.estado, doc.rnc_emisor, doc.monto_total), ("Recibido", RNC_PROVEEDOR, 2950))
		self.assertEqual(doc.aprobacion, "Pendiente")

		# El mismo e-CF otra vez: envío duplicado
		self.assertEqual(acuse(recepcion.recibir_ecf(xml)), ("1", "3"))

	def test_recepcion_rechaza_firma_y_comprador(self):
		xml = ecf_del_proveedor(self.llave_proveedor, self.cert_proveedor, "E310000000078")
		self.assertEqual(acuse(recepcion.recibir_ecf(xml.replace(b"2950.00", b"29.00"))), ("1", "2"))
		otro = ecf_del_proveedor(self.llave_proveedor, self.cert_proveedor, "E310000000079", "101543231")
		self.assertEqual(acuse(recepcion.recibir_ecf(otro)), ("1", "4"))
		self.assertRaises(recepcion.ErrorRecepcion, recepcion.recibir_ecf, b"<no-es-xml")
		# XML con entidades externas: no se resuelven (XXE)
		xxe = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY e SYSTEM "file:///etc/passwd">]><ECF>&e;</ECF>'
		self.assertRaises(recepcion.ErrorRecepcion, recepcion.recibir_ecf, xxe)

	def test_aprobacion_comercial(self):
		recepcion.recibir_ecf(ecf_del_proveedor(self.llave_proveedor, self.cert_proveedor, "E310000000080"))
		nombre = frappe.db.get_value("ECF Recibido", {"encf": "E310000000080"})
		self.assertRaises(frappe.ValidationError, recepcion.aprobar, nombre, 0, "")
		with dgii():
			self.assertEqual(recepcion.aprobar(nombre, 0, "Precio distinto al acordado"), "Rechazado")
		doc = frappe.get_doc("ECF Recibido", nombre)
		self.assertEqual(doc.envio_aprobacion, "Enviada")
		acecf = emision.leer_xml(doc.xml_aprobacion)
		self.assertEqual(esquemas.errores("ACECF", acecf), [])
		raiz = firma.leer(acecf)
		self.assertEqual(raiz.findtext("DetalleAprobacionComercial/Estado"), "2")
		self.assertEqual(raiz.findtext("DetalleAprobacionComercial/RNCComprador"), RNC_EMPRESA)
		urls = [u for _m, u, _k in SesionCompleta.llamadas]
		self.assertTrue(any(u.endswith("/aprobacioncomercial/api/aprobacioncomercial") for u in urls))
		self.assertIn(RECEPTOR + "/fe/aprobacioncomercial/api/ecf", urls)
		self.assertRaises(frappe.ValidationError, recepcion.aprobar, nombre, 1)

	def test_aprobacion_de_un_cliente(self):
		envio = self._envio("E310000000053", estado="Aceptado")
		acecf = firma.firmar(
			esquemas.construir(
				"ACECF",
				{
					"DetalleAprobacionComercial": {
						"Version": "1.0",
						"RNCEmisor": RNC_EMPRESA,
						"eNCF": "E310000000053",
						"FechaEmision": "15-10-2026",
						"MontoTotal": "2950.00",
						"RNCComprador": "131880738",
						"Estado": 1,
						"FechaHoraAprobacionComercial": "16-10-2026 09:00:00",
					}
				},
			),
			self.llave_proveedor,
			self.cert_proveedor,
		)
		recepcion.recibir_aprobacion(acecf)
		self.assertEqual(frappe.db.get_value("Envio ECF", envio.name, "aprobacion_comercial"), "Aprobado")
		self.assertRaises(
			recepcion.ErrorRecepcion, recepcion.recibir_aprobacion, acecf.replace(b"2950", b"2951")
		)

	# ------------------------------------------------------- set de pruebas

	def test_set_de_pruebas(self):
		filas = {
			"TipoeCF": 31,
			"eNCF": "E310000000090",
			"FechaVencimientoSecuencia": "31-12-2027",
			"IndicadorMontoGravado": 0,
			"TipoIngresos": 1,  # Excel lo lee como número: va "01"
			"TipoPago": 1,
			"FormaPago[1]": 1,
			"MontoPago[1]": 2950,
			"RNCEmisor": RNC_EMPRESA,
			"RazonSocialEmisor": "EMPRESA DE PRUEBA SRL",
			"DireccionEmisor": "Calle Primera 1",
			"FechaEmision": "15-10-2026",
			"RNCComprador": "131880738",
			"RazonSocialComprador": "CLIENTE SRL",
			"MontoGravadoTotal": 2500,
			"MontoGravadoI1": 2500,
			"ITBIS1": 18,
			"TotalITBIS": 450,
			"TotalITBIS1": 450,
			"MontoTotal": 2950,
			"NumeroLinea[1]": 1,
			"IndicadorFacturacion[1]": 1,
			"NombreItem[1]": "Envase",
			"IndicadorBienoServicio[1]": 1,
			"CantidadItem[1]": 100,
			"PrecioUnitarioItem[1]": 25,
			"MontoItem[1]": 2500,
			"NombreItem[2]": "#e",
		}
		datos = certificacion.datos_de_fila(31, filas)
		self.assertEqual(datos["Encabezado"]["IdDoc"]["TipoIngresos"], "01")
		self.assertEqual(datos["Encabezado"]["Totales"]["MontoTotal"], "2950.00")
		self.assertEqual(len(datos["DetallesItems"]["Item"]), 1)

		consumo = copy.deepcopy(filas)
		consumo.update({"TipoeCF": 32, "eNCF": "E320000000090"})
		mala = {"TipoeCF": 31, "eNCF": "E310000000091"}
		encabezado = list(filas)
		csv = "\n".join(
			",".join(str(f.get(c, "")) for c in encabezado)
			for f in ({c: c for c in encabezado}, filas, consumo, mala)
		)
		archivo = frappe.get_doc(
			{"doctype": "File", "file_name": "set.csv", "content": csv.encode(), "is_private": 1}
		).insert()
		prueba = frappe.get_doc(
			{"doctype": "Set Pruebas ECF", "company": EMPRESA, "archivo": archivo.file_url}
		).insert()

		resultado = certificacion.generar(prueba.name)
		self.assertEqual(resultado, {"generados": 2, "errores": 1})
		prueba.reload()
		self.assertIn("E310000000091", prueba.resultado)
		envios = frappe.get_all(
			"Envio ECF",
			filters={"tipo_documento": "Set Pruebas ECF", "documento": prueba.name},
			fields=["encf", "es_rfce", "xml", "xml_rfce"],
			order_by="encf",
		)
		self.assertEqual([(e.encf, e.es_rfce) for e in envios], [("E310000000090", 0), ("E320000000090", 1)])
		self.assertEqual(esquemas.errores("RFCE", emision.leer_xml(envios[1].xml_rfce)), [])
		# Volver a firmar no duplica
		self.assertEqual(certificacion.generar(prueba.name)["generados"], 2)

		with dgii():
			self.assertEqual(certificacion.enviar(prueba.name), {"enviados": 2})


class TestServiciosReceptor(IntegrationTestCase):
	"""Las rutas públicas /fe/... en el servidor web del sitio (sin escribir en la base)."""

	URL = "http://localhost:8000"

	def _pedir(self, metodo, ruta, **kw):
		try:
			return requests.request(
				metodo,
				self.URL + ruta,
				headers={"Host": frappe.local.site, **kw.pop("headers", {})},
				timeout=30,
				**kw,
			)
		except requests.ConnectionError:
			self.skipTest("el servidor web del sitio no está disponible")

	def test_autenticacion_y_token(self):
		semilla = self._pedir("GET", "/fe/autenticacion/api/semilla")
		self.assertEqual(semilla.status_code, 200)
		self.assertTrue(firma.leer(semilla.content).findtext("valor"))

		llave, cert = firma.cargar_certificado(certificado_de_prueba(), "prueba")
		sin_firmar = self._pedir(
			"POST", "/fe/autenticacion/api/validacioncertificado", files={"xml": ("s.xml", semilla.content)}
		)
		self.assertEqual(sin_firmar.status_code, 401)

		semilla = self._pedir("GET", "/fe/autenticacion/api/semilla").content
		r = self._pedir(
			"POST",
			"/fe/autenticacion/api/validacioncertificado",
			files={"xml": ("s.xml", firma.firmar(semilla, llave, cert))},
		)
		self.assertEqual(r.status_code, 200)
		token = r.json()["token"]
		# La misma semilla no sirve dos veces
		repetida = self._pedir(
			"POST",
			"/fe/autenticacion/api/validacioncertificado",
			files={"xml": ("s.xml", firma.firmar(semilla, llave, cert))},
		)
		self.assertEqual(repetida.status_code, 401)

		sin_token = self._pedir("POST", "/fe/recepcion/api/ecf", files={"xml": ("e.xml", b"<ECF/>")})
		self.assertEqual(sin_token.status_code, 401)
		basura = self._pedir(
			"POST",
			"/fe/recepcion/api/ecf",
			files={"xml": ("e.xml", b"<no-es-xml")},
			headers={"Authorization": f"bearer {token}"},
		)
		self.assertEqual(basura.status_code, 400)
		self.assertEqual(self._pedir("GET", "/fe/recepcion/api/ecf").status_code, 405)
