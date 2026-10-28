"""Captura de compras, etapa 1: e-CF recibido de un proveedor -> Factura de Compra en borrador.

La DGII y el proveedor se simulan; el certificado es autofirmado."""

import copy
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import flt

from erpnext_rd.captura_compras import convertir
from erpnext_rd.dgii_fiscal.validaciones import es_rnc_valido
from erpnext_rd.ecf import esquemas, firma, recepcion
from erpnext_rd.tests.test_ecf import certificado_de_prueba, datos_e31
from erpnext_rd.tests.test_ecf_intercambio import dgii

EMPRESA = "_Test Captura RD"
RNC_EMPRESA = "130000018"
RNC_PROVEEDOR = "131880738"
CODIGO = "ENV-1L"


def rnc_libre() -> str:
	"""Un RNC válido que no es de ningún proveedor."""
	for numero in range(131000000, 131100000):
		rnc = str(numero)
		if es_rnc_valido(rnc) and not frappe.db.exists("Supplier", {"tax_id": rnc}):
			return rnc
	raise AssertionError


class BaseCaptura(IntegrationTestCase):
	"""Empresa, proveedor, artículos, cuentas y configuración de captura (también para test_captura_qr)."""

	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		if not frappe.db.exists("Company", EMPRESA):
			frappe.get_doc(
				{
					"doctype": "Company",
					"company_name": EMPRESA,
					"abbr": "_TCAP",
					"country": "Dominican Republic",
					"default_currency": "DOP",
					"tax_id": RNC_EMPRESA,
					"chart_of_accounts": "Standard",
					"create_chart_of_accounts_based_on": "Standard Template",
				}
			).insert()
		if not frappe.db.exists("Emisor ECF", EMPRESA):
			archivo = frappe.get_doc(
				{
					"doctype": "File",
					"file_name": "cap.p12",
					"content": certificado_de_prueba(),
					"is_private": 1,
				}
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
		cls.llave, cls.cert = firma.cargar_certificado(certificado_de_prueba(), "prueba")
		frappe.db.set_single_value("Configuracion DGII", "ambiente_ecf", "TesteCF")

		cls.proveedor = frappe.db.get_value("Supplier", {"tax_id": RNC_PROVEEDOR}) or (
			frappe.get_doc(
				{
					"doctype": "Supplier",
					"supplier_name": "_Test Plásticos del Caribe",
					"supplier_group": frappe.db.get_value("Supplier Group", {"is_group": 0}),
					"tax_id": RNC_PROVEEDOR,
				}
			)
			.insert()
			.name
		)
		grupo = frappe.db.get_value("Item Group", {"is_group": 0})
		cls.envase = cls._item("_Test Envase Captura", grupo, is_stock_item=0)
		item = frappe.get_doc("Item", cls.envase)
		if not item.supplier_items:
			item.append("supplier_items", {"supplier": cls.proveedor, "supplier_part_no": CODIGO})
			item.save()
		cls.generico = cls._item("_Test Gasto Captura", grupo, is_stock_item=0)
		cls.luz = cls._item("_Test Energía Captura", grupo, is_stock_item=0)

		cuentas = frappe.get_all(
			"Account", filters={"company": EMPRESA, "root_type": "Expense", "is_group": 0}, pluck="name"
		)
		cls.cuenta_gasto, cls.cuenta_luz = cuentas[0], cuentas[1]
		cls.cuenta_itbis = frappe.db.get_value(
			"Account", {"company": EMPRESA, "account_type": "Tax", "is_group": 0}
		) or cls._cuenta("_Test ITBIS Compras", "Tax")
		cls.cuenta_retenido = cls._cuenta("_Test ITBIS Retenido Captura", "Tax")
		if not frappe.db.exists(convertir.CONFIG, EMPRESA):
			frappe.get_doc(
				{
					"doctype": convertir.CONFIG,
					"company": EMPRESA,
					"crear_borrador_automatico": 0,
					"crear_proveedor": 1,
					"item_generico": cls.generico,
					"cuenta_gasto_defecto": cls.cuenta_gasto,
					"cuenta_itbis": cls.cuenta_itbis,
					"cuenta_itbis_retenido": cls.cuenta_retenido,
					"tolerancia_redondeo": 1,
					"reglas": [
						{
							"proveedor": cls.proveedor,
							"contiene": "energía",
							"item": cls.luz,
							"cuenta_gasto": cls.cuenta_luz,
							"rd_tipo_bienes_servicios": "02 - Gastos por trabajos, suministros y servicios",
						}
					],
				}
			).insert()

	@staticmethod
	def _item(codigo, grupo, **campos):
		if not frappe.db.exists("Item", codigo):
			frappe.get_doc({"doctype": "Item", "item_code": codigo, "item_group": grupo, **campos}).insert()
		return codigo

	@staticmethod
	def _cuenta(nombre, tipo):
		padre = frappe.db.get_value(
			"Account", {"company": EMPRESA, "root_type": "Liability", "is_group": 1}, order_by="lft desc"
		)
		existente = frappe.db.get_value("Account", {"company": EMPRESA, "account_name": nombre})
		return existente or (
			frappe.get_doc(
				{
					"doctype": "Account",
					"account_name": nombre,
					"company": EMPRESA,
					"parent_account": padre,
					"account_type": tipo,
				}
			)
			.insert()
			.name
		)

	# ------------------------------------------------------------ ayudas

	def xml(self, encf, lineas=None, emisor=RNC_PROVEEDOR, tipo=31, totales=None, **extra) -> bytes:
		datos = datos_e31()
		encabezado = datos["Encabezado"]
		encabezado["IdDoc"]["TipoeCF"] = tipo
		encabezado["IdDoc"]["eNCF"] = encf
		encabezado["Emisor"]["RNCEmisor"] = emisor
		encabezado["Comprador"]["RNCComprador"] = RNC_EMPRESA
		if lineas is not None:
			datos["DetallesItems"]["Item"] = lineas
		if totales:
			encabezado["Totales"] = totales
		datos.update(extra)
		return firma.firmar(esquemas.construir(tipo, datos), self.llave, self.cert)

	def recibir(self, xml) -> "frappe.Document":
		recepcion.recibir_ecf(xml)
		raiz = firma.leer(xml)
		return frappe.get_last_doc(
			recepcion.RECIBIDO,
			filters={"company": EMPRESA, "encf": raiz.findtext("Encabezado/IdDoc/eNCF")},
		)

	def convertir(self, recibido):
		convertir.desde_ecf(recibido.name)
		recibido.reload()
		return recibido, recibido.factura_compra and frappe.get_doc(
			"Purchase Invoice", recibido.factura_compra
		)

	@staticmethod
	def linea(numero, nombre, monto, indicador=1, codigo=None, cantidad=1):
		linea = {
			"NumeroLinea": numero,
			"IndicadorFacturacion": indicador,
			"NombreItem": nombre,
			"IndicadorBienoServicio": 1,
			"CantidadItem": f"{cantidad:.2f}",
			"PrecioUnitarioItem": f"{monto / cantidad:.2f}",
			"MontoItem": f"{monto:.2f}",
		}
		if codigo:
			linea["TablaCodigosItem"] = {"CodigosItem": [{"TipoCodigo": "INTERNA", "CodigoItem": codigo}]}
		return linea


class TestCapturaCompras(BaseCaptura):
	def test_articulo_del_proveedor(self):
		recibido = self.recibir(
			self.xml(
				"E310000001001", [self.linea(1, "Envase plástico 1 L", 2500, codigo=CODIGO, cantidad=100)]
			)
		)
		self.assertEqual(recibido.estado_conversion, "Pendiente")
		self.assertEqual(len(recibido.detalle), 1)
		self.assertEqual(recibido.monto_gravado_i1, 2500)

		recibido, factura = self.convertir(recibido)
		self.assertEqual(recibido.estado_conversion, "Borrador creado", recibido.mensajes_conversion)
		self.assertEqual(factura.docstatus, 0)
		self.assertEqual(factura.items[0].item_code, self.envase)
		self.assertEqual(factura.items[0].qty, 100)
		self.assertEqual((factura.rd_ncf, factura.bill_no), ("E310000001001", "E310000001001"))
		self.assertEqual(flt(factura.total_taxes_and_charges), 450)
		self.assertEqual(flt(factura.grand_total), 2950)
		self.assertTrue(
			frappe.db.exists(
				"File", {"attached_to_doctype": "Purchase Invoice", "attached_to_name": factura.name}
			)
		)

	def test_regla_de_gasto_y_articulo_generico(self):
		totales = {
			"MontoGravadoTotal": "1500.00",
			"MontoGravadoI1": "1000.00",
			"MontoGravadoI2": "500.00",
			"ITBIS1": 18,
			"ITBIS2": 16,
			"TotalITBIS": "260.00",
			"TotalITBIS1": "180.00",
			"TotalITBIS2": "80.00",
			"MontoExento": "200.00",
			"MontoTotal": "1960.00",
		}
		lineas = [
			self.linea(1, "Servicio de energía eléctrica", 1000),
			self.linea(2, "Otro cargo", 500, indicador=2),
			self.linea(3, "Cargo exento", 200, indicador=4),
		]
		recibido, factura = self.convertir(self.recibir(self.xml("E310000001002", lineas, totales=totales)))
		self.assertEqual(recibido.estado_conversion, "Requiere revisión")
		self.assertIn("Otro cargo", recibido.mensajes_conversion)
		self.assertEqual(recibido.itbis_i2, 80)
		self.assertEqual([i.item_code for i in factura.items], [self.luz, self.generico, self.generico])
		self.assertEqual(factura.items[0].expense_account, self.cuenta_luz)
		self.assertEqual(factura.rd_tipo_bienes_servicios[:2], "02")
		self.assertEqual(flt(factura.total_taxes_and_charges), 260)
		self.assertEqual(flt(factura.grand_total), 1960)

	def test_total_que_no_cuadra(self):
		totales = copy.deepcopy(datos_e31()["Encabezado"]["Totales"])
		totales["MontoTotal"] = "3100.00"
		recibido, _factura = self.convertir(
			self.recibir(
				self.xml("E310000001003", [self.linea(1, "Envase", 2500, codigo=CODIGO)], totales=totales)
			)
		)
		self.assertEqual(recibido.estado_conversion, "Requiere revisión")
		self.assertIn("no cuadra", recibido.mensajes_conversion)

	def test_duplicado_se_enlaza(self):
		recibido = self.recibir(self.xml("E310000001004", [self.linea(1, "Envase", 2500, codigo=CODIGO)]))
		_recibido, factura = self.convertir(recibido)
		frappe.db.set_value(recepcion.RECIBIDO, recibido.name, "factura_compra", None)
		recibido.reload()
		recibido, otra = self.convertir(recibido)
		self.assertEqual(otra.name, factura.name)
		self.assertIn("Ya existía", recibido.mensajes_conversion)

	def test_proveedor_nuevo(self):
		rnc = rnc_libre()
		recibido, factura = self.convertir(
			self.recibir(self.xml("E310000001005", [self.linea(1, "Envase", 2500)], emisor=rnc))
		)
		self.assertEqual(frappe.db.get_value("Supplier", factura.supplier, "tax_id"), rnc)
		self.assertEqual(recibido.proveedor, factura.supplier)

	def test_tipo_no_convertible(self):
		recibido = self.recibir(self.xml("E310000001006", [self.linea(1, "Envase", 2500)]))
		recibido.db_set("tipo_ecf", "E46")
		recibido, factura = self.convertir(recibido)
		self.assertFalse(factura)
		self.assertEqual(recibido.estado_conversion, "Error")
		self.assertIn("E46", recibido.mensajes_conversion)

	def test_ignorar(self):
		recibido = self.recibir(self.xml("E310000001007", [self.linea(1, "Envase", 2500)]))
		self.assertEqual(convertir.ignorar(recibido.name), "Ignorado")

	def test_validar_aprueba_y_cancelar_desenlaza(self):
		frappe.db.set_value(convertir.CONFIG, EMPRESA, "aprobar_al_validar", 1)
		frappe.clear_document_cache(convertir.CONFIG, EMPRESA)
		recibido, factura = self.convertir(
			self.recibir(self.xml("E310000001008", [self.linea(1, "Envase", 2500, codigo=CODIGO)]))
		)
		with dgii():
			factura.submit()
		recibido.reload()
		self.assertEqual(recibido.factura_compra, factura.name)
		self.assertEqual(recibido.aprobacion, "Aprobado")

		factura.cancel()
		recibido.reload()
		self.assertFalse(recibido.factura_compra)
		self.assertEqual(recibido.estado_conversion, "Pendiente")

	def test_conversion_automatica(self):
		frappe.db.set_value(convertir.CONFIG, EMPRESA, "crear_borrador_automatico", 1)
		with patch("frappe.enqueue") as encolar:
			recibido = self.recibir(self.xml("E310000001009", [self.linea(1, "Envase", 2500)]))
		encolar.assert_called_once()
		self.assertEqual(encolar.call_args.kwargs["name"], recibido.name)

	def test_carga_manual(self):
		xml = self.xml("E310000001010", [self.linea(1, "Envase", 2500, codigo=CODIGO)])
		archivo = frappe.get_doc(
			{"doctype": "File", "file_name": "proveedor.xml", "content": xml, "is_private": 1}
		).insert()
		recibido = frappe.get_doc(recepcion.RECIBIDO, recepcion.cargar_xml(archivo.file_url))
		self.assertEqual(recibido.origen, "Carga manual")
		self.assertFalse(recibido.acuse)
		self.assertEqual(len(recibido.detalle), 1)
		# El mismo e-CF otra vez es un duplicado
		self.assertRaises(frappe.ValidationError, recepcion.cargar_xml, archivo.file_url)

	def test_empresa_no_rd_no_convierte(self):
		recibido = self.recibir(self.xml("E310000001011", [self.linea(1, "Envase", 2500)]))
		with patch("erpnext_rd.captura_compras.convertir.es_empresa_rd", return_value=False):
			self.assertIsNone(convertir.convertir(recibido))
