"""Ventas a zonas francas y otros regímenes especiales (Fase 8.4): B14 / E44 sin ITBIS ni ISC."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days

from erpnext_rd.dgii_fiscal import isc, regimenes
from erpnext_rd.rd_compliance import perfil
from erpnext_rd.tests import test_isc
from erpnext_rd.tests.test_isc import CERVEZA, EMPRESA, FECHA

ZONA_FRANCA = "_Test Zona Franca RD"
RNC_ZONA_FRANCA = "101003731"


def _venta(cliente: str, item_code: str = CERVEZA, **otros):
	from erpnext.controllers.accounts_controller import get_taxes_and_charges

	si = frappe.get_doc(
		{
			"doctype": "Sales Invoice",
			"company": EMPRESA,
			"customer": cliente,
			"set_posting_time": 1,
			"posting_date": FECHA,
			"due_date": FECHA,
			"items": [{"item_code": item_code, "qty": 2, "rate": 2000}],
			**otros,
		}
	)
	si.taxes_and_charges = frappe.db.get_value(
		"Sales Taxes and Charges Template", {"company": EMPRESA, "title": "ITBIS 18%"}
	)
	si.set("taxes", get_taxes_and_charges("Sales Taxes and Charges Template", si.taxes_and_charges))
	return si.insert()


class TestRegimenesEspeciales(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		# Empresa, cliente y artículos con ISC de las pruebas del ISC
		test_isc.TestISC.setUpClass()

	def setUp(self):
		frappe.db.savepoint("regimenes")
		perfil.guardar(EMPRESA, {"tamano": perfil.GRANDE, "isc_alcohol": 1})
		self.cliente = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": ZONA_FRANCA,
				"tax_id": RNC_ZONA_FRANCA,
				"rd_regimen_especial": regimenes.ZONA_FRANCA,
				"rd_carnet_regimen": "ZF-0001",
				"rd_carnet_vence": add_days(FECHA, 30),
			}
		).insert()

	def tearDown(self):
		frappe.db.rollback(save_point="regimenes")
		frappe.clear_document_cache(perfil.DOCTYPE, EMPRESA)

	def test_b14_sin_itbis_ni_isc(self):
		si = _venta(self.cliente.name)
		self.assertEqual(si.rd_tipo_comprobante, "B14")
		self.assertEqual(si.taxes, [])
		self.assertEqual(si.grand_total, 4000)
		self.assertFalse(si.items[0].rd_isc_categoria)

	def test_carnet_vencido_o_sin_carnet(self):
		self.cliente.rd_carnet_vence = add_days(FECHA, -1)
		self.cliente.save()
		self.assertRaises(frappe.ValidationError, _venta, self.cliente.name)
		self.cliente.rd_carnet_regimen = None
		self.cliente.rd_carnet_vence = None
		self.cliente.save()
		self.assertRaises(frappe.ValidationError, _venta, self.cliente.name)

	def test_comprobante_elegido_a_mano(self):
		# Bienes que la zona franca no usa para operar: el vendedor elige B01 y lleva ITBIS e ISC
		si = _venta(self.cliente.name, rd_tipo_comprobante="B01")
		self.assertEqual(si.rd_tipo_comprobante, "B01")
		self.assertEqual(si.taxes[0].charge_type, isc.TIPO_CARGO)
		self.assertTrue(si.taxes[1].tax_amount)
		# B14 a un cliente que no es de régimen especial: no se guarda
		self.assertRaises(frappe.ValidationError, _venta, "_Test Cliente ISC", rd_tipo_comprobante="B14")

	def test_zona_franca_comercial_no_cambia_el_comprobante(self):
		self.cliente.rd_regimen_especial = regimenes.ZONA_FRANCA_COMERCIAL
		self.cliente.save()
		si = _venta(self.cliente.name)
		self.assertEqual(si.rd_tipo_comprobante, "B01")
		self.assertTrue(si.taxes)

	def test_emisor_electronico_usa_e44(self):
		self.assertEqual(regimenes.tipo_especial("E"), "E44")
		self.assertEqual(regimenes.tipo_especial("B"), "B14")
