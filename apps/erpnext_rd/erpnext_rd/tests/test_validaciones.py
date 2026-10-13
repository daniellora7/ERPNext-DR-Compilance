from frappe.tests import UnitTestCase

from erpnext_rd.dgii_fiscal.validaciones import (
	es_cedula_valida,
	es_identificacion_valida,
	es_ncf_valido,
	es_rnc_valido,
	formatear_ncf,
	limpiar_identificacion,
	parsear_ncf,
	tipo_identificacion,
)


class TestValidaciones(UnitTestCase):
	# Números con dígito verificador correcto (la cédula aparece en el padrón público de la DGII)
	def test_rnc(self):
		self.assertTrue(es_rnc_valido("101010632"))
		self.assertTrue(es_rnc_valido("1-01-01063-2"))
		self.assertFalse(es_rnc_valido("101010633"))
		self.assertFalse(es_rnc_valido("12345"))
		self.assertFalse(es_rnc_valido(None))

	def test_cedula(self):
		self.assertTrue(es_cedula_valida("00100322338"))
		self.assertTrue(es_cedula_valida("001-0032233-8"))
		self.assertFalse(es_cedula_valida("00100322339"))
		self.assertFalse(es_cedula_valida("0010032233"))

	def test_tipo_identificacion(self):
		self.assertEqual(tipo_identificacion("101-01063-2"), "RNC")
		self.assertEqual(tipo_identificacion("00100322338"), "Cédula")
		self.assertIsNone(tipo_identificacion("ABC"))
		self.assertTrue(es_identificacion_valida("00100322338"))
		self.assertEqual(limpiar_identificacion(" 1-01 "), "101")

	def test_formatear_ncf(self):
		self.assertEqual(formatear_ncf("B", "01", 5), "B0100000005")
		self.assertEqual(formatear_ncf("E", "31", 1), "E310000000001")
		with self.assertRaises(ValueError):
			formatear_ncf("B", "01", 100000000)
		with self.assertRaises(ValueError):
			formatear_ncf("B", "01", 0)

	def test_parsear_ncf(self):
		self.assertEqual(parsear_ncf("b0200000123")["codigo"], "B02")
		self.assertEqual(parsear_ncf("E320000000077")["secuencial"], 77)
		self.assertIsNone(parsear_ncf("B020000012"))  # 7 dígitos
		self.assertIsNone(parsear_ncf("E3200000077"))  # serie E con 8 dígitos
		self.assertTrue(es_ncf_valido("B0100000001", "B01"))
		self.assertFalse(es_ncf_valido("B0100000001", "B02"))


class TestImpresion(UnitTestCase):
	def test_url_timbre_credito_fiscal(self):
		from erpnext_rd.dgii_fiscal.impresion import url_timbre_ecf

		url = url_timbre_ecf(
			rnc_emisor="101010632",
			rnc_comprador="101003723",
			encf="E310000000001",
			fecha_emision="2026-10-12",
			monto_total=1180,
			fecha_firma="2026-10-12 14:05:09",
			codigo_seguridad="AbC123",
			ambiente="TesteCF",
		)
		self.assertTrue(url.startswith("https://ecf.dgii.gov.do/testecf/ConsultaTimbre?"))
		self.assertIn("RncComprador=101003723", url)
		self.assertIn("FechaEmision=12-10-2026", url)
		self.assertIn("MontoTotal=1180.00", url)
		self.assertIn("FechaFirma=12-10-2026+14%3A05%3A09", url)

	def test_url_timbre_consumo_menor(self):
		from erpnext_rd.dgii_fiscal.impresion import url_timbre_ecf

		url = url_timbre_ecf(
			rnc_emisor="101010632", encf="E320000000005", monto_total=500, codigo_seguridad="XyZ789", ambiente="eCF"
		)
		self.assertEqual(
			url,
			"https://fc.dgii.gov.do/ecf/ConsultaTimbreFC?RncEmisor=101010632&ENCF=E320000000005"
			"&MontoTotal=500.00&CodigoSeguridad=XyZ789",
		)

	def test_qr(self):
		from erpnext_rd.dgii_fiscal.impresion import qr_data_uri

		self.assertTrue(qr_data_uri("https://ecf.dgii.gov.do").startswith("data:image/svg+xml;base64,"))
