"""e-CF: contingencia (serie B y su e-CF de reemplazo, plazo de 72 horas), conservación de lo firmado y
certificado de quien firma lo recibido."""

from unittest.mock import patch

import frappe
from cryptography.hazmat.primitives import serialization
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, now_datetime

from erpnext_rd.ecf import conservacion, contingencia, emision, esquemas, firma, monitor, receptor
from erpnext_rd.rd_compliance import perfil
from erpnext_rd.tests import test_isc
from erpnext_rd.tests.test_ecf import autoridad_de_prueba, certificado_de_prueba, datos_e31
from erpnext_rd.tests.test_isc import EMPRESA, FECHA

SERVICIO = "_Test Servicio Contingencia"
CONFIG = "Configuracion DGII"


def _venta(**otros):
	from erpnext.controllers.accounts_controller import get_taxes_and_charges

	si = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": EMPRESA,
			"customer": "_Test Cliente ISC",
			"set_posting_time": 1,
			"posting_date": FECHA,
			"due_date": FECHA,
			"items": [{"item_code": SERVICIO, "qty": 1, "rate": 1000}],
			"company_address_display": "Av. 27 de Febrero 1, Santo Domingo",
			**otros,
		}
	)
	si.taxes_and_charges = frappe.db.get_value(
		"Sales Taxes and Charges Template", {"company": EMPRESA, "title": "ITBIS 18%"}
	)
	si.set("taxes", get_taxes_and_charges("Sales Taxes and Charges Template", si.taxes_and_charges))
	return si.insert()


class TestContingencia(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		test_isc.TestISC.setUpClass()
		test_isc._articulo(SERVICIO, rd_bien_o_servicio="Servicio")

	def setUp(self):
		frappe.db.savepoint("contingencia")
		perfil.guardar(EMPRESA, {"tamano": perfil.GRANDE, "ecf_estado": perfil.ECF_EMISOR})
		frappe.get_doc(
			{
				"doctype": "Secuencia NCF",
				"company": EMPRESA,
				"tipo_comprobante": "E31",
				"desde": 1,
				"hasta": 100,
				"fecha_vencimiento": "2027-12-31",
			}
		).insert()
		archivo = frappe.get_doc(
			{"doctype": "File", "file_name": "ecf.p12", "content": certificado_de_prueba(), "is_private": 1}
		).insert()
		if frappe.db.exists("Emisor ECF", EMPRESA):
			self.emisor = frappe.get_doc("Emisor ECF", EMPRESA)
		else:
			self.emisor = frappe.new_doc("Emisor ECF")
			self.emisor.company = EMPRESA
		self.emisor.update({"habilitado": 0, "certificado": archivo.file_url, "clave_certificado": "prueba"})
		self.emisor.save()

	def tearDown(self):
		frappe.db.rollback(save_point="contingencia")
		frappe.clear_document_cache(perfil.DOCTYPE, EMPRESA)

	def _declarar(self, desde, hasta=None):
		self.emisor.update({"contingencia_desde": desde, "contingencia_hasta": hasta})
		self.emisor.save()

	def test_sin_contingencia_no_se_vende_con_serie_b(self):
		self.assertEqual(_venta().rd_tipo_comprobante, "E31")
		self.assertRaises(frappe.ValidationError, _venta, rd_tipo_comprobante="B01")

	def test_venta_en_contingencia_y_su_ecf_de_reemplazo(self):
		self._declarar(add_days(FECHA, -1))
		si = _venta()
		self.assertEqual((si.rd_tipo_comprobante, si.rd_contingencia_ecf), ("B01", 1))
		si.submit()
		self.assertTrue(si.rd_ncf.startswith("B01"))
		self.assertEqual([p.name for p in contingencia.pendientes(EMPRESA)], [si.name])

		# La salida de la contingencia da el plazo de 30 días para el reemplazo
		self._declarar(add_days(FECHA, -1), FECHA)
		self.assertEqual(
			str(frappe.db.get_value("Sales Invoice", si.name, "rd_plazo_reemplazo")), add_days(FECHA, 30)
		)

		nombre = contingencia.emitir_reemplazo(si.name)
		envio = frappe.get_doc("Envio ECF", nombre)
		self.assertEqual((envio.es_reemplazo, envio.ncf_reemplazado, envio.tipo_ecf), (1, si.rd_ncf, "E31"))
		xml = emision.leer_xml(envio.xml)
		self.assertEqual(esquemas.errores(31, xml), [])
		referencia = firma.leer(xml).find("InformacionReferencia")
		self.assertEqual(referencia.findtext("NCFModificado"), si.rd_ncf)
		self.assertEqual(referencia.findtext("CodigoModificacion"), "4")
		factura = frappe.db.get_value("Sales Invoice", si.name, ["rd_ncf", "rd_encf_reemplazo"], as_dict=True)
		self.assertEqual((factura.rd_ncf, factura.rd_encf_reemplazo), (si.rd_ncf, envio.encf))
		self.assertEqual(contingencia.pendientes(EMPRESA), [])
		self.assertRaises(frappe.ValidationError, contingencia.emitir_reemplazo, si.name)

		# Va solo a la DGII: no se entrega al comprador
		envio.db_set("estado", "Aceptado")
		self.assertRaises(frappe.ValidationError, emision.entregar, envio.name)

	def test_contingencia_de_mas_de_15_dias(self):
		self._declarar(add_days(FECHA, -20))
		self.assertRaises(frappe.ValidationError, _venta)

	def test_fechas_de_la_contingencia(self):
		self.emisor.contingencia_hasta = FECHA
		self.assertRaises(frappe.ValidationError, self.emisor.save)
		self.emisor.reload()
		self.emisor.update({"contingencia_desde": FECHA, "contingencia_hasta": add_days(FECHA, -1)})
		self.assertRaises(frappe.ValidationError, self.emisor.save)

	def test_plazo_de_72_horas_sin_conexion(self):
		ahora = now_datetime()
		envios = monitor.con_plazo(
			[{"fecha_firma": add_to_date(ahora, hours=-80)}, {"fecha_firma": add_to_date(ahora, hours=-10)}]
		)
		self.assertEqual([e["vencido"] for e in envios], [True, False])
		self.assertEqual(envios[1]["vence"], add_to_date(envios[1]["fecha_firma"], hours=72))


class TestConservacion(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		test_isc.TestISC.setUpClass()

	def setUp(self):
		frappe.db.savepoint("conservacion")

	def tearDown(self):
		frappe.db.rollback(save_point="conservacion")

	def _con_xml(self, doctype, **campos):
		doc = frappe.get_doc({"doctype": doctype, "company": EMPRESA, **campos}).insert(
			ignore_permissions=True
		)
		archivo = emision.guardar_xml(doctype, doc.name, "xml", f"{doc.name}.xml", b"<ECF/>")
		return doc, frappe.get_doc("File", {"file_url": archivo})

	def test_ecf_firmado_no_se_borra(self):
		envio, archivo = self._con_xml("Envio ECF", encf="E310000000099", tipo_ecf="E31", estado="Firmado")
		self.assertRaises(frappe.ValidationError, frappe.delete_doc, "Envio ECF", envio.name)
		self.assertRaises(frappe.ValidationError, archivo.delete)
		self.assertTrue(conservacion.protegido("Envio ECF", envio.name))

	def test_recibido_se_conserva_y_el_invalido_no(self):
		recibido, archivo = self._con_xml("ECF Recibido", encf="E310000000098", estado="Recibido")
		self.assertRaises(frappe.ValidationError, frappe.delete_doc, "ECF Recibido", recibido.name)
		self.assertRaises(frappe.ValidationError, archivo.delete)
		invalido, _archivo = self._con_xml("ECF Recibido", encf="E310000000097", estado="No recibido")
		frappe.delete_doc("ECF Recibido", invalido.name)
		self.assertFalse(frappe.db.exists("ECF Recibido", invalido.name))


class TestCertificadoFirmante(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		cls.ca = autoridad_de_prueba()
		cls.pem = cls.ca[1].public_bytes(serialization.Encoding.PEM).decode()

	def setUp(self):
		frappe.db.savepoint("certificado")

	def tearDown(self):
		frappe.db.rollback(save_point="certificado")

	def _firmado(self, p12: bytes) -> bytes:
		llave, cert = firma.cargar_certificado(p12, "prueba")
		return firma.firmar(esquemas.construir(31, datos_e31()), llave, cert)

	def test_vigencia_y_entidad(self):
		autofirmado = self._firmado(certificado_de_prueba())
		emitido = self._firmado(certificado_de_prueba(emisor=self.ca))
		vencido = self._firmado(certificado_de_prueba(vence_en_dias=-1))
		cert = firma.certificado_firmante
		self.assertIsNone(firma.problema_certificado(cert(autofirmado), []))
		self.assertEqual(firma.problema_certificado(cert(vencido), []), "vencido")
		self.assertEqual(firma.problema_certificado(None, []), "sin_certificado")
		autorizados = firma.cargar_autorizados(self.pem)
		self.assertEqual(firma.problema_certificado(cert(autofirmado), autorizados), "no_autorizado")
		self.assertIsNone(firma.problema_certificado(cert(emitido), autorizados))

	def test_entidades_en_la_configuracion(self):
		from erpnext_rd.ecf.recepcion import certificado_aceptable

		autofirmado = self._firmado(certificado_de_prueba())
		emitido = self._firmado(certificado_de_prueba(emisor=self.ca))
		self.assertTrue(certificado_aceptable(autofirmado))
		frappe.db.set_single_value(CONFIG, "certificados_autorizados_ecf", self.pem)
		self.assertFalse(certificado_aceptable(autofirmado))
		self.assertTrue(certificado_aceptable(emitido))
		frappe.db.set_single_value(CONFIG, "certificados_autorizados_ecf", "no es un PEM")
		self.assertFalse(certificado_aceptable(emitido))

	def test_limite_de_peticiones(self):
		_metodo, semilla = receptor.RUTAS["fe/autenticacion/api/semilla"]
		peticion = frappe._dict(method="GET")
		ip = f"prueba-{frappe.generate_hash(length=10)}"
		with (
			patch.object(frappe.local, "request", peticion, create=True),
			patch.object(frappe.local, "request_ip", ip, create=True),
		):
			for _i in range(30):
				semilla()
			self.assertRaises(frappe.RateLimitExceededError, semilla)
