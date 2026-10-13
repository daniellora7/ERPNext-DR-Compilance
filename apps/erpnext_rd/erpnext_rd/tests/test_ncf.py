import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, nowdate

from erpnext_rd.dgii_fiscal.identificacion import validar_party
from erpnext_rd.dgii_fiscal.ncf import tomar_siguiente_ncf

EMPRESA = "_Test Empresa RD"


def crear_secuencia(tipo="B01", desde=1, hasta=3, **kw):
	doc = frappe.get_doc(
		{
			"doctype": "Secuencia NCF",
			"company": EMPRESA,
			"tipo_comprobante": tipo,
			"desde": desde,
			"hasta": hasta,
			**kw,
		}
	)
	doc.flags.ignore_links = True
	return doc.insert(ignore_permissions=True)


class TestSecuenciaNCF(IntegrationTestCase):
	def setUp(self):
		frappe.db.delete("Secuencia NCF", {"company": EMPRESA})

	def test_asigna_en_orden_y_agota(self):
		seq = crear_secuencia(desde=1, hasta=3)
		self.assertEqual(seq.siguiente, 1)
		self.assertEqual(seq.disponibles, 3)

		ncfs = [tomar_siguiente_ncf(EMPRESA, "B01").ncf for _ in range(3)]
		self.assertEqual(ncfs, ["B0100000001", "B0100000002", "B0100000003"])

		seq.reload()
		self.assertEqual(seq.disponibles, 0)
		self.assertEqual(seq.habilitada, 0)
		self.assertEqual(seq.ultimo_ncf, "B0100000003")

		with self.assertRaises(frappe.ValidationError):
			tomar_siguiente_ncf(EMPRESA, "B01")

	def test_serie_electronica(self):
		crear_secuencia(tipo="E31", desde=1, hasta=10)
		self.assertEqual(tomar_siguiente_ncf(EMPRESA, "E31").ncf, "E310000000001")

	def test_salta_secuencia_vencida(self):
		crear_secuencia(desde=1, hasta=5, fecha_vencimiento=add_days(nowdate(), -1))
		crear_secuencia(desde=6, hasta=10, fecha_vencimiento=add_days(nowdate(), 365))
		self.assertEqual(tomar_siguiente_ncf(EMPRESA, "B01").ncf, "B0100000006")

	def test_no_permite_solapamiento(self):
		crear_secuencia(desde=1, hasta=100)
		with self.assertRaises(frappe.ValidationError):
			crear_secuencia(desde=50, hasta=150)

	def test_rango_maximo_serie_b(self):
		with self.assertRaises(frappe.ValidationError):
			crear_secuencia(desde=1, hasta=100_000_000)


class TestIdentificacionParty(IntegrationTestCase):
	def _cliente(self, tax_id, tipo=None):
		return frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": "_Test RD",
				"tax_id": tax_id,
				"rd_tipo_identificacion": tipo,
			}
		)

	def test_normaliza_rnc(self):
		doc = self._cliente("1-01-01063-2")
		validar_party(doc)
		self.assertEqual(doc.tax_id, "101010632")
		self.assertEqual(doc.rd_tipo_identificacion, "RNC")

	def test_rechaza_rnc_invalido(self):
		with self.assertRaises(frappe.ValidationError):
			validar_party(self._cliente("101010633"))

	def test_rnc_antiguo_existente_en_padron(self):
		# RNC con dígito verificador que no cuadra pero registrado en la DGII
		frappe.db.set_single_value("Configuracion DGII", "validar_contra_padron", 1)
		frappe.get_doc({"doctype": "Contribuyente DGII", "rnc": "401007374", "razon_social": "_Test"}).insert(
			ignore_permissions=True, ignore_if_duplicate=True
		)
		doc = self._cliente("401007374")
		validar_party(doc)
		self.assertEqual(doc.rd_tipo_identificacion, "RNC")

	def test_pasaporte_sin_validacion(self):
		doc = self._cliente("ab123456", tipo="Pasaporte")
		validar_party(doc)
		self.assertEqual(doc.tax_id, "AB123456")

	def test_id_extranjero_de_cliente(self):
		doc = self._cliente("xaxx010101000")
		validar_party(doc)
		self.assertEqual(doc.tax_id, "XAXX010101000")
		self.assertEqual(doc.rd_tipo_identificacion, "Pasaporte")

	def test_proveedor_y_empresa_de_otro_pais_no_se_validan(self):
		proveedor = frappe.get_doc(
			{"doctype": "Supplier", "supplier_name": "_Test MX", "country": "Mexico", "tax_id": "98-7654321"}
		)
		validar_party(proveedor)
		self.assertEqual(proveedor.tax_id, "98-7654321")

		empresa = frappe.get_doc(
			{"doctype": "Company", "company_name": "_Test MX", "country": "Mexico", "tax_id": "EKU9003173C9"}
		)
		validar_party(empresa)
		self.assertEqual(empresa.tax_id, "EKU9003173C9")

	def test_logica_ncf_solo_en_empresas_rd(self):
		from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd, validar_venta

		empresa_mx = frappe.db.get_value("Company", {"country": ("!=", "Dominican Republic")})
		if empresa_mx:
			self.assertFalse(es_empresa_rd(empresa_mx))
		self.assertFalse(es_empresa_rd(None))

		factura = frappe.get_doc(
			{"doctype": "Sales Invoice", "company": "_Empresa inexistente", "customer": "x"}
		)
		validar_venta(factura)  # no exige secuencia NCF ni tipo de comprobante
		self.assertFalse(factura.get("rd_tipo_comprobante"))
