"""e-CF: armado del XML guiado por los XSD oficiales, firma XMLDSig y validación (sin certificado real)."""

import datetime

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import pkcs12
from frappe.tests import IntegrationTestCase
from lxml import etree

from erpnext_rd.ecf import datos as d
from erpnext_rd.ecf import esquemas, firma


def certificado_de_prueba(clave: str = "prueba") -> bytes:
	"""Un .p12 autofirmado, como el que entrega la entidad certificadora (solo para pruebas)."""
	llave = rsa.generate_private_key(public_exponent=65537, key_size=2048)
	nombre = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, "EMPRESA DE PRUEBA SRL")])
	hoy = datetime.datetime.now(datetime.UTC)
	cert = (
		x509.CertificateBuilder()
		.subject_name(nombre)
		.issuer_name(nombre)
		.public_key(llave.public_key())
		.serial_number(x509.random_serial_number())
		.not_valid_before(hoy - datetime.timedelta(days=1))
		.not_valid_after(hoy + datetime.timedelta(days=365))
		.sign(llave, hashes.SHA256())
	)
	return pkcs12.serialize_key_and_certificates(
		b"prueba", llave, cert, None, serialization.BestAvailableEncryption(clave.encode())
	)


def datos_e31(**cambios) -> dict:
	datos = {
		"Encabezado": {
			"Version": "1.0",
			"IdDoc": {
				"TipoeCF": 31,
				"eNCF": "E310000000001",
				"FechaVencimientoSecuencia": "31-12-2027",
				"IndicadorMontoGravado": 0,
				"TipoIngresos": "01",
				"TipoPago": 1,
				"TablaFormasPago": {"FormaDePago": [{"FormaPago": 1, "MontoPago": "2950.00"}]},
			},
			"Emisor": {
				"RNCEmisor": "101000001",
				"RazonSocialEmisor": "EMPRESA DE PRUEBA SRL",
				"DireccionEmisor": "Calle Primera 1, Santo Domingo",
				"FechaEmision": "15-10-2026",
			},
			"Comprador": {"RNCComprador": "131880738", "RazonSocialComprador": "CLIENTE SRL"},
			"Totales": {
				"MontoGravadoTotal": "2500.00",
				"MontoGravadoI1": "2500.00",
				"ITBIS1": 18,
				"TotalITBIS": "450.00",
				"TotalITBIS1": "450.00",
				"MontoTotal": "2950.00",
			},
		},
		"DetallesItems": {
			"Item": [
				{
					"NumeroLinea": 1,
					"IndicadorFacturacion": 1,
					"NombreItem": "Envase plástico 1 L",
					"IndicadorBienoServicio": 1,
					"CantidadItem": "100.00",
					"PrecioUnitarioItem": "25",
					"MontoItem": "2500.00",
				}
			]
		},
		"FechaHoraFirma": "15-10-2026 10:30:00",
	}
	datos.update(cambios)
	return datos


class TestECF(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.llave, cls.cert = firma.cargar_certificado(certificado_de_prueba(), "prueba")

	def test_xml_en_el_orden_del_esquema(self):
		xml = esquemas.construir(31, datos_e31())
		encabezado = [e.tag for e in xml.find("Encabezado")]
		self.assertEqual(encabezado, ["Version", "IdDoc", "Emisor", "Comprador", "Totales"])
		self.assertEqual([e.tag for e in xml][-1], "FechaHoraFirma")
		# Lo que el tipo no acepta no se emite (E43 no lleva comprador)
		self.assertIsNone(esquemas.construir(43, datos_e31()).find("Encabezado/Comprador"))

	def test_dato_obligatorio(self):
		datos = datos_e31()
		del datos["Encabezado"]["Emisor"]["DireccionEmisor"]
		with self.assertRaises(esquemas.FaltaDato):
			esquemas.construir(31, datos)

	def test_firmado_valido_y_verificable(self):
		firmado = firma.firmar(esquemas.construir(31, datos_e31()), self.llave, self.cert)
		self.assertEqual(esquemas.errores(31, firmado), [])
		self.assertTrue(firma.verificar(firmado))
		self.assertEqual(len(firma.codigo_seguridad(firmado)), 6)
		raiz = etree.fromstring(firmado)
		self.assertEqual(raiz[-1].tag, "{http://www.w3.org/2000/09/xmldsig#}Signature")
		self.assertIsNone(raiz[-1].prefix)  # sin prefijo ds:, como en los ejemplos de la DGII

	def test_firma_canonica_sin_xmlns_vacio(self):
		"""Regresión: libxml2 agregaba xmlns="" al canonicalizar SignedInfo y xmlsec1 rechazaba la firma."""
		firmado = firma.firmar(esquemas.construir(31, datos_e31()), self.llave, self.cert)
		info = etree.fromstring(firmado).find(f"{{{firma.DS}}}Signature/{{{firma.DS}}}SignedInfo")
		canonico = firma._c14n_firma(info)
		self.assertNotIn(b'xmlns=""', canonico)
		self.assertTrue(canonico.startswith(b'<SignedInfo xmlns="http://www.w3.org/2000/09/xmldsig#">'))

	def test_alterado_no_verifica(self):
		firmado = firma.firmar(esquemas.construir(31, datos_e31()), self.llave, self.cert)
		alterado = firmado.replace(b"2950.00", b"2.00")
		self.assertFalse(firma.verificar(alterado))

	def test_sin_firma_no_cumple_el_esquema(self):
		xml = etree.tostring(esquemas.construir(31, datos_e31()))
		self.assertTrue(esquemas.errores(31, xml))

	def test_resumen_factura_consumo(self):
		datos = datos_e31()
		datos["Encabezado"]["IdDoc"].update(TipoeCF=32, eNCF="E320000000001")
		ecf = firma.firmar(esquemas.construir(32, datos), self.llave, self.cert)
		self.assertEqual(esquemas.errores(32, ecf), [])
		rfce = firma.firmar(
			esquemas.construir("RFCE", d.datos_rfce(datos, firma.codigo_seguridad(ecf))),
			self.llave,
			self.cert,
		)
		self.assertEqual(esquemas.errores("RFCE", rfce), [])
		self.assertEqual(
			etree.fromstring(rfce).findtext("Encabezado/CodigoSeguridadeCF"), firma.codigo_seguridad(ecf)
		)

	def test_formatos(self):
		self.assertEqual((d.monto(2950), d.precio(25.5), d.precio(0.1234)), ("2950.00", "25.5", "0.1234"))
		self.assertEqual(d.fecha("2026-10-05"), "05-10-2026")
		self.assertEqual(firma.datos_certificado(self.cert)["titular"], "EMPRESA DE PRUEBA SRL")


SEMILLA = (
	b'<?xml version="1.0" encoding="utf-8"?><SemillaModel xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
	b'xmlns:xsd="http://www.w3.org/2001/XMLSchema"><valor>abc</valor><fecha>2026-10-16T10:00:00</fecha></SemillaModel>'
)


class Respuesta:
	def __init__(self, datos=None, contenido=b"", estado=200):
		self.status_code, self._datos, self.content, self.text = estado, datos, contenido, str(datos)

	def json(self):
		if self._datos is None:
			raise ValueError
		return self._datos


class SesionDGII:
	"""Simula los servicios de la DGII y guarda lo que recibe."""

	def __init__(self):
		self.llamadas = []

	def get(self, url, **kw):
		self.llamadas.append(("GET", url, kw))
		if url.endswith("/semilla"):
			return Respuesta(contenido=SEMILLA)
		return Respuesta({"trackId": "T-1", "codigo": 1, "estado": "Aceptado", "mensajes": []})

	def post(self, url, **kw):
		self.llamadas.append(("POST", url, kw))
		if url.endswith("/validarsemilla"):
			xml = kw["files"]["xml"][1]
			assert firma.verificar(xml), "la semilla debe llegar firmada"
			return Respuesta(
				{"token": "TOKEN-1", "expira": "2099-01-01T00:00:00Z", "expedido": "2026-10-16T10:00:00Z"}
			)
		if "recepcionfc" in url:
			return Respuesta({"codigo": 1, "estado": "Aceptado", "mensajes": [], "encf": "E320000000001"})
		return Respuesta({"trackId": "T-1", "error": None, "mensaje": None})


class TestClienteDGII(IntegrationTestCase):
	def setUp(self):
		from erpnext_rd.ecf.cliente import ClienteDGII

		llave, cert = firma.cargar_certificado(certificado_de_prueba(), "prueba")
		self.sesion = SesionDGII()
		self.cliente = ClienteDGII("101000001", llave, cert, ambiente="TesteCF", sesion=self.sesion)
		frappe_cache_borrar(self.cliente._clave_cache())

	def test_token_con_semilla_firmada_y_en_cache(self):
		self.assertEqual(self.cliente.token(), "TOKEN-1")
		self.assertEqual(self.cliente.token(), "TOKEN-1")
		urls = [u for _m, u, _k in self.sesion.llamadas]
		self.assertEqual(
			urls,
			[
				"https://ecf.dgii.gov.do/testecf/autenticacion/api/autenticacion/semilla",
				"https://ecf.dgii.gov.do/testecf/autenticacion/api/autenticacion/validarsemilla",
			],
		)

	def test_envio_y_consulta(self):
		respuesta = self.cliente.enviar_ecf(b"<ECF/>", "E310000000001")
		self.assertEqual(respuesta["trackId"], "T-1")
		_metodo, url, kw = self.sesion.llamadas[-1]
		self.assertEqual(url, "https://ecf.dgii.gov.do/testecf/recepcion/api/facturaselectronicas")
		self.assertEqual(kw["headers"]["Authorization"], "bearer TOKEN-1")
		self.assertEqual(kw["files"]["xml"][0], "101000001E310000000001.xml")
		self.assertEqual(self.cliente.consultar_resultado("T-1")["estado"], "Aceptado")

	def test_rfce_al_servicio_fc(self):
		self.cliente.enviar_rfce(b"<RFCE/>", "E320000000001")
		self.assertEqual(
			self.sesion.llamadas[-1][1], "https://fc.dgii.gov.do/testecf/recepcionfc/api/recepcion/ecf"
		)


def frappe_cache_borrar(clave):
	import frappe

	frappe.cache.delete_value(clave)
