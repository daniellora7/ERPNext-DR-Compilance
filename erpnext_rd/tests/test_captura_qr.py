"""Captura de compras, etapa 2: e-CF impreso o en PDF (QR, texto del PDF, verificación DGII y factura)
y la factura en papel sin QR (datos escritos a mano y consulta pública de NCF).

La DGII se simula."""

import io
from unittest.mock import patch

import frappe
from frappe.utils import flt, get_datetime, getdate

from erpnext_rd.captura_compras import api, qr
from erpnext_rd.dgii_fiscal import consulta_ncf
from erpnext_rd.dgii_fiscal.impresion import url_timbre_ecf
from erpnext_rd.ecf.cliente import ErrorDGII
from erpnext_rd.tests.test_captura_compras import (
	CODIGO,
	EMPRESA,
	RNC_EMPRESA,
	RNC_PROVEEDOR,
	BaseCaptura,
)


def url(encf, total=1180, comprador=RNC_EMPRESA, emisor=RNC_PROVEEDOR) -> str:
	return url_timbre_ecf(
		rnc_emisor=emisor,
		rnc_comprador=comprador,
		encf=encf,
		fecha_emision="2026-10-20",
		monto_total=total,
		fecha_firma="2026-10-20 09:15:00",
		codigo_seguridad="Ab12Cd",
		ambiente="TesteCF",
	)


def pdf(lineas: list[str]) -> bytes:
	"""PDF mínimo de una página con texto (como el que genera el sistema del proveedor)."""
	texto = " ".join(f"({linea}) '" for linea in lineas)
	flujo = f"BT /F1 10 Tf 40 800 Td 14 TL {texto} ET".encode("latin-1")
	objetos = [
		b"<< /Type /Catalog /Pages 2 0 R >>",
		b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
		b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 842] /Contents 4 0 R"
		b" /Resources << /Font << /F1 5 0 R >> >> >>",
		b"<< /Length %d >>\nstream\n" % len(flujo) + flujo + b"\nendstream",
		b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>",
	]
	salida = b"%PDF-1.4\n"
	posiciones = []
	for i, objeto in enumerate(objetos, start=1):
		posiciones.append(len(salida))
		salida += b"%d 0 obj\n" % i + objeto + b"\nendobj\n"
	xref = len(salida)
	salida += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objetos) + 1)
	salida += b"".join(b"%010d 00000 n \n" % p for p in posiciones)
	salida += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objetos) + 1, xref)
	return salida


TEXTO_FACTURA = [
	"PLASTICOS DEL CARIBE SRL",
	"RNC: 131-88073-8",
	"Factura de Credito Fiscal Electronica",
	"e-NCF: E310000002001",
	"Fecha de emision: 20-10-2026",
	f"RNC Comprador: {RNC_EMPRESA}",
	"Subtotal gravado: RD$ 1,000.00",
	"ITBIS 18%: 180.00",
	"Total: RD$ 1,180.00",
	"Código de seguridad: Ab12Cd",
	"Fecha de firma: 20-10-2026 09:15:00",
]


class DGIIAceptado:
	estado = "Aceptado"

	def __init__(self, *args, **kwargs):
		pass

	def consultar_estado(self, encf, rnc_comprador, codigo, rnc_emisor=None):
		assert rnc_emisor == RNC_PROVEEDOR
		return {"codigo": 1, "estado": self.estado}


class DGIIRechazado(DGIIAceptado):
	estado = "Rechazado"


class TestCapturaQR(BaseCaptura):
	def capturar(self, encf, **kw):
		with patch("frappe.enqueue"):
			return frappe.get_doc(api.CAPTURA, api.crear(EMPRESA, url_timbre=url(encf), **kw)["name"])

	# ------------------------------------------------------------ lectura

	def test_leer_url_completa_y_fc(self):
		datos = qr.leer_url(url("E310000002002"))
		self.assertEqual(
			(datos["rnc_emisor"], datos["rnc_comprador"], datos["encf"], datos["codigo_seguridad"]),
			(RNC_PROVEEDOR, RNC_EMPRESA, "E310000002002", "Ab12Cd"),
		)
		self.assertEqual(datos["monto_total"], 1180)
		self.assertEqual(datos["fecha_emision"], getdate("2026-10-20"))
		self.assertEqual(datos["fecha_firma"], get_datetime("2026-10-20 09:15:00"))

		fc = qr.leer_url(
			"https://fc.dgii.gov.do/ecf/ConsultaTimbreFC?RncEmisor=101010632&ENCF=E320000000005"
			"&MontoTotal=500.00&CodigoSeguridad=XyZ789"
		)
		self.assertEqual((fc["encf"], fc["monto_total"], fc["rnc_comprador"]), ("E320000000005", 500, None))

	def test_url_que_no_es_de_la_dgii(self):
		buena = url("E310000002003")
		for mala in (
			buena.replace("ecf.dgii.gov.do", "ecf.dgii.gov.do.falso.com"),
			buena.replace("https://", "http://"),
			buena.replace("ConsultaTimbre", "Otra"),
			"https://ecf.dgii.gov.do/testecf/ConsultaTimbre?RncEmisor=131880738",
			"texto cualquiera",
		):
			with self.subTest(mala=mala):
				self.assertRaises(frappe.ValidationError, qr.leer_url, mala)

	def test_texto_del_pdf(self):
		datos = qr.leer_pdf(pdf(TEXTO_FACTURA), RNC_EMPRESA)
		self.assertEqual(datos["encf"], "E310000002001")
		self.assertEqual((datos["rnc_emisor"], datos["rnc_comprador"]), (RNC_PROVEEDOR, RNC_EMPRESA))
		self.assertEqual((datos["monto_total"], datos["total_itbis"]), (1180, 180))
		self.assertEqual(datos["codigo_seguridad"], "Ab12Cd")
		self.assertEqual(datos["fecha_firma"], get_datetime("2026-10-20 09:15:00"))
		self.assertEqual(qr.leer_pdf(b"no es un pdf"), {})

	# ------------------------------------------------------------ captura

	def test_qr_verificado_completado_y_factura(self):
		captura = self.capturar(
			"E310000002004",
			rd_tipo_bienes_servicios="09 - Compras y gastos que formarán parte del costo de venta",
		)
		self.assertEqual(
			(captura.estado, captura.proveedor, captura.origen), ("Pendiente", self.proveedor, "QR")
		)

		with patch("erpnext_rd.captura_compras.qr.ClienteDGII", DGIIAceptado):
			api.verificar_en_segundo_plano(captura.name)
		captura.reload()
		self.assertEqual(captura.estado_dgii, "Aceptado")

		self.assertEqual(api.completar(captura.name, 180)["estado"], "Lista")
		factura = frappe.get_doc("Purchase Invoice", api.crear_factura(captura.name))
		captura.reload()
		self.assertEqual(captura.estado, "Factura creada")
		self.assertEqual(factura.docstatus, 0)
		self.assertEqual(factura.rd_ncf, "E310000002004")
		self.assertEqual(factura.rd_codigo_seguridad, "Ab12Cd")
		self.assertEqual(flt(factura.net_total), 1000)
		self.assertEqual(flt(factura.grand_total), 1180)

	def test_sin_itbis_no_crea_factura(self):
		captura = self.capturar("E310000002005")
		self.assertRaises(frappe.ValidationError, api.crear_factura, captura.name)

	def test_rechazado_en_la_dgii(self):
		captura = self.capturar("E310000002006", total_itbis=180)
		with patch("erpnext_rd.captura_compras.qr.ClienteDGII", DGIIRechazado):
			api.verificar(captura.name)
		captura.reload()
		self.assertEqual(captura.estado, "Requiere revisión")
		self.assertRaises(frappe.ValidationError, api.crear_factura, captura.name)

	def test_dgii_sin_servicio(self):
		captura = self.capturar("E310000002007")

		class Caida(DGIIAceptado):
			def consultar_estado(self, *args, **kwargs):
				raise ErrorDGII("Servicio no disponible", 503)

		with patch("erpnext_rd.captura_compras.qr.ClienteDGII", Caida):
			self.assertEqual(api.verificar(captura.name), "Error")

	def test_factura_de_otra_empresa(self):
		with patch("frappe.enqueue"):
			self.assertRaises(
				frappe.ValidationError,
				api.crear,
				EMPRESA,
				url_timbre=url("E310000002008", comprador="131880738"),
			)

	def test_duplicados(self):
		self.capturar("E310000002009")
		self.assertRaises(frappe.ValidationError, self.capturar, "E310000002009")
		# El mismo envío del celular repetido devuelve la misma captura
		primera = self.capturar("E310000002010", id_cliente="cel-1")
		self.assertEqual(self.capturar("E310000002010", id_cliente="cel-1").name, primera.name)

	def test_pdf_lee_el_itbis(self):
		archivo = frappe.get_doc(
			{"doctype": "File", "file_name": "factura.pdf", "content": pdf(TEXTO_FACTURA), "is_private": 1}
		).insert()
		with patch("frappe.enqueue"):
			resumen = api.crear(EMPRESA, file_url=archivo.file_url)
		captura = frappe.get_doc(api.CAPTURA, resumen["name"])
		self.assertEqual((captura.origen, captura.encf, captura.estado), ("PDF", "E310000002001", "Lista"))
		self.assertEqual((captura.total_itbis, captura.fuente_montos), (180, "Texto del PDF"))
		archivo.reload()
		self.assertEqual(archivo.attached_to_name, captura.name)

	def test_llega_el_xml_despues(self):
		captura = self.capturar("E310000002011", total_itbis=450)
		factura = api.crear_factura(captura.name)
		recibido = self.recibir(self.xml("E310000002011", [self.linea(1, "Envase", 2500, codigo=CODIGO)]))
		captura.reload()
		self.assertEqual(captura.ecf_recibido, recibido.name)
		self.assertIn("difiere", captura.avisos)
		self.assertEqual(recibido.factura_compra, factura)

	def test_borrar_la_factura_reabre_la_captura(self):
		captura = self.capturar("E310000002012", total_itbis=180)
		factura = api.crear_factura(captura.name)
		frappe.delete_doc("Purchase Invoice", factura)
		captura.reload()
		self.assertFalse(captura.factura_compra)
		self.assertEqual(captura.estado, "Lista")


def foto() -> bytes:
	from PIL import Image

	salida = io.BytesIO()
	Image.new("RGB", (8, 8), "white").save(salida, "JPEG")
	return salida.getvalue()


def rnc_fuera_del_padron() -> str:
	"""Un número que no está en el padrón (el sitio de pruebas puede tenerlo completo)."""
	return next(
		str(n) for n in range(999000000, 999100000) if not frappe.db.exists("Contribuyente DGII", str(n))
	)


def respuesta_ncf(estado, vigencia=None) -> frappe._dict:
	return frappe._dict(estado=estado, vigencia=getdate(vigencia) if vigencia else None, mensaje=estado)


class TestCapturaManual(BaseCaptura):
	"""Factura en papel (o e-CF sin QR): foto y datos escritos en el celular."""

	def capturar(self, ncf, **kw):
		archivo = frappe.get_doc(
			{"doctype": "File", "file_name": "factura.jpg", "content": foto(), "is_private": 1}
		).insert()
		datos = {
			"rnc_emisor": RNC_PROVEEDOR,
			"fecha_emision": "2026-10-20",
			"monto_total": 1180,
			"total_itbis": 180,
			**kw,
		}
		with patch("frappe.enqueue"):
			resumen = api.crear(EMPRESA, file_url=archivo.file_url, ncf=ncf, **datos)
		return frappe.get_doc(api.CAPTURA, resumen["name"])

	def test_factura_en_papel(self):
		captura = self.capturar("b0100000123")
		self.assertEqual(
			(captura.origen, captura.encf, captura.tipo_ecf, captura.estado, captura.proveedor),
			("Foto", "B0100000123", "B01", "Lista", self.proveedor),
		)
		with patch.object(consulta_ncf, "consultar", return_value=respuesta_ncf(consulta_ncf.VALIDO)):
			self.assertEqual(api.verificar(captura.name), "Válido")

		factura = frappe.get_doc("Purchase Invoice", api.crear_factura(captura.name))
		self.assertEqual((factura.rd_ncf, factura.rd_tipo_comprobante), ("B0100000123", "B01"))
		self.assertEqual(factura.bill_date, getdate("2026-10-20"))
		self.assertEqual((flt(factura.net_total), flt(factura.grand_total)), (1000, 1180))

	def test_ncf_vencido_o_de_otro_rnc(self):
		for ncf, respuesta, estado in (
			("B0100000124", respuesta_ncf(consulta_ncf.VENCIDO, "2026-01-31"), "Vencido"),
			("B0100000125", respuesta_ncf(consulta_ncf.NO_CORRESPONDE), "No corresponde al RNC"),
		):
			with self.subTest(estado=estado):
				captura = self.capturar(ncf)
				with patch.object(consulta_ncf, "consultar", return_value=respuesta):
					api.verificar(captura.name)
				captura.reload()
				self.assertEqual((captura.estado_dgii, captura.estado), (estado, "Requiere revisión"))
				self.assertRaises(frappe.ValidationError, api.crear_factura, captura.name)

	def test_vencido_despues_de_la_factura_es_valido(self):
		captura = self.capturar("B0100000126")
		vencido = respuesta_ncf(consulta_ncf.VENCIDO, "2026-12-31")
		with patch.object(consulta_ncf, "consultar", return_value=vencido):
			self.assertEqual(api.verificar(captura.name), "Válido")

	def test_datos_incompletos_o_mal_escritos(self):
		self.assertRaises(frappe.ValidationError, self.capturar, "B01123")
		captura = self.capturar(None, rnc_emisor=None, monto_total=None)
		self.assertEqual(captura.estado, "Requiere revisión")
		for aviso in ("NCF", "RNC", "monto total"):
			self.assertIn(aviso, captura.avisos)

	def test_buscar_emisor(self):
		rnc = rnc_fuera_del_padron()
		frappe.get_doc(
			{
				"doctype": "Contribuyente DGII",
				"rnc": rnc,
				"razon_social": "ZQX PRUEBA CAPTURA SRL",
				"estado": "ACTIVO",
			}
		).insert()
		nombre = frappe.db.get_value("Supplier", self.proveedor, "supplier_name")

		self.assertIn(self.proveedor, [e.get("proveedor") for e in api.buscar_emisor(RNC_PROVEEDOR[:5])])
		self.assertIn(self.proveedor, [e.get("proveedor") for e in api.buscar_emisor(nombre[1:6])])
		self.assertEqual([e.rnc for e in api.buscar_emisor("zqx prueba")], [rnc])
		self.assertEqual(api.buscar_emisor("zq"), [])

		datos = api.emisor(EMPRESA, rnc)
		self.assertEqual((datos["razon_social"], datos["estado"]), ("ZQX PRUEBA CAPTURA SRL", "ACTIVO"))
		self.assertEqual(api.emisor(EMPRESA, RNC_PROVEEDOR)["proveedor"], self.proveedor)
