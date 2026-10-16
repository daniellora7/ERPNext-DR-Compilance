import io
from datetime import date
from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import IntegrationTestCase, UnitTestCase

from erpnext_rd.dgii_fiscal import tasa_bcrd

VERSION = "Thu, 15 Oct 2026 22:08:00 GMT"


def excel_bcrd() -> bytes:
	"""Excel con la forma del que publica el BCRD (título, encabezado y filas Año | Mes | Día)."""
	import openpyxl

	libro = openpyxl.Workbook()
	hoja = libro.active
	hoja.title = "Diaria"
	hoja.append(["Tasas de Cambio del dólar de Referencia del Mercado Spot"])
	hoja.append([])
	hoja.append(["Año", "Mes", "Día", "Compra", "Venta"])
	hoja.append([2026, "Oct", 14, 61.1477, 61.6788])
	hoja.append([2026, "Oct", 15, 61.2578, 61.7717])
	hoja.append([2026, "Dic", 31, 62.5, 63.0])
	hoja.append(["*Nota al pie", None, None, None, None])
	libro.create_sheet("PromMensual").append(["Año", "Mes", "Compra", "Venta"])
	buffer = io.BytesIO()
	libro.save(buffer)
	return buffer.getvalue()


def respuesta(status: int, contenido: bytes = b"", version: str | None = None) -> MagicMock:
	r = MagicMock(
		status_code=status, content=contenido, headers={"Last-Modified": version} if version else {}
	)
	r.raise_for_status.return_value = None
	return r


class TestLecturaTasa(UnitTestCase):
	def test_leer_hoja_diaria(self):
		tasas = tasa_bcrd.leer_tasas(excel_bcrd())
		self.assertEqual(
			tasas,
			{
				date(2026, 10, 14): (61.1477, 61.6788),
				date(2026, 10, 15): (61.2578, 61.7717),
				date(2026, 12, 31): (62.5, 63.0),
			},
		)

	def test_registros_segun_tipo(self):
		self.assertEqual(
			tasa_bcrd.registros(61.25, 61.77, tasa_bcrd.COMPRA),
			[{"exchange_rate": 61.25, "for_selling": 1, "for_buying": 1}],
		)
		self.assertEqual(tasa_bcrd.registros(61.25, 61.77, tasa_bcrd.VENTA)[0]["exchange_rate"], 61.77)
		separada = tasa_bcrd.registros(61.25, 61.77, tasa_bcrd.SEPARADA)
		self.assertEqual(
			[(r["exchange_rate"], r["for_selling"], r["for_buying"]) for r in separada],
			[(61.25, 1, 0), (61.77, 0, 1)],
		)

	def test_sin_cambios_no_descarga(self):
		with patch.object(tasa_bcrd.requests, "get", return_value=respuesta(304)) as get:
			self.assertEqual(tasa_bcrd.descargar(VERSION), (None, VERSION))
		self.assertEqual(get.call_args.kwargs["headers"]["If-Modified-Since"], VERSION)
		with patch.object(tasa_bcrd.requests, "get", return_value=respuesta(200, b"x", VERSION)):
			self.assertEqual(tasa_bcrd.descargar(VERSION), (None, VERSION))


class TestRegistroTasa(IntegrationTestCase):
	def setUp(self):
		frappe.db.delete("Currency Exchange", {"from_currency": "USD", "to_currency": "DOP"})
		for moneda in ("USD", "DOP"):
			if not frappe.db.exists("Currency", moneda):
				frappe.get_doc({"doctype": "Currency", "currency_name": moneda, "enabled": 1}).insert()
		frappe.db.set_single_value(
			"Configuracion DGII",
			{
				"tasa_bcrd_activa": 1,
				"tasa_bcrd_tipo": tasa_bcrd.COMPRA,
				"tasa_bcrd_ultima_fecha": None,
				"tasa_bcrd_version": None,
			},
		)

	def tearDown(self):
		frappe.db.rollback()

	def tasa_erpnext(self, fecha, args=None):
		from erpnext.setup.utils import get_exchange_rate

		return get_exchange_rate("USD", "DOP", fecha, args)

	def test_registra_y_respeta_existentes(self):
		manual = frappe.get_doc(
			{
				"doctype": "Currency Exchange",
				"date": "2026-10-14",
				"from_currency": "USD",
				"to_currency": "DOP",
				"exchange_rate": 60,
				"for_buying": 1,
				"for_selling": 1,
			}
		).insert()

		with (
			patch.object(tasa_bcrd.requests, "get", return_value=respuesta(200, excel_bcrd(), VERSION)),
			patch.object(tasa_bcrd, "hay_empresas_en_pesos", return_value=True),
		):
			self.assertEqual(tasa_bcrd.actualizar_tasa(), 2)

		self.assertEqual(frappe.db.get_value("Currency Exchange", manual.name, "exchange_rate"), 60)
		self.assertEqual(self.tasa_erpnext("2026-10-15"), 61.2578)
		# Sábado: la del último día laborable
		self.assertEqual(self.tasa_erpnext("2026-10-17"), 61.2578)

		conf = frappe.get_single("Configuracion DGII")
		self.assertEqual(str(conf.tasa_bcrd_ultima_fecha), "2026-12-31")
		self.assertEqual(conf.tasa_bcrd_venta, 63.0)
		self.assertEqual(conf.tasa_bcrd_version, VERSION)

		# Mismo archivo: no se descarga ni se duplica
		with (
			patch.object(tasa_bcrd.requests, "get", return_value=respuesta(304)),
			patch.object(tasa_bcrd, "hay_empresas_en_pesos", return_value=True),
		):
			self.assertIsNone(tasa_bcrd.actualizar_tasa())

	def test_compra_en_ventas_venta_en_compras(self):
		frappe.db.set_single_value("Configuracion DGII", "tasa_bcrd_tipo", tasa_bcrd.SEPARADA)
		with (
			patch.object(tasa_bcrd.requests, "get", return_value=respuesta(200, excel_bcrd(), VERSION)),
			patch.object(tasa_bcrd, "hay_empresas_en_pesos", return_value=True),
		):
			tasa_bcrd.actualizar_tasa()
		self.assertEqual(self.tasa_erpnext("2026-10-15", "for_selling"), 61.2578)
		self.assertEqual(self.tasa_erpnext("2026-10-15", "for_buying"), 61.7717)

	def test_desactivada_no_descarga(self):
		frappe.db.set_single_value("Configuracion DGII", "tasa_bcrd_activa", 0)
		with patch.object(tasa_bcrd.requests, "get") as get:
			self.assertIsNone(tasa_bcrd.actualizar_tasa())
		get.assert_not_called()
