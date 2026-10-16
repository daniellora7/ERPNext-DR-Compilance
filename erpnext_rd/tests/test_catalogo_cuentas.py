from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from erpnext_rd.dgii_fiscal import catalogo_cuentas as cc
from erpnext_rd.dgii_fiscal import catalogos as cat
from erpnext_rd.nomina_rd import hrms_instalado


class TestEstructuraCatalogo(IntegrationTestCase):
	def test_numeros_unicos_y_padres(self):
		numeros = [c[0] for c in cc.CUENTAS]
		self.assertEqual(len(numeros), len(set(numeros)))
		for numero in numeros:
			if len(numero) > 1:
				self.assertIsNotNone(cc._padre(numero, set(numeros)), numero)

	def test_tipos_de_cuenta_obligatorios(self):
		tipos = {c[2] for c in cc.CUENTAS}
		for requerido in (
			"Cash",
			"Bank",
			"Receivable",
			"Payable",
			"Stock",
			"Tax",
			"Fixed Asset",
			"Cost of Goods Sold",
			"Depreciation",
			"Stock Adjustment",
			"Round Off",
			"Temporary",
		):
			self.assertIn(requerido, tipos)

	def test_raices(self):
		raiz = cc.arbol()
		self.assertEqual(
			{v["root_type"] for v in raiz.values()}, {"Asset", "Liability", "Equity", "Income", "Expense"}
		)
		self.assertEqual(
			raiz["ACTIVOS"]["ACTIVOS CORRIENTES"]["Caja"]["Caja General"]["account_number"], "110101"
		)

	def test_herencia_tipos_606_607(self):
		datos = cc.datos_dgii()
		self.assertEqual(datos["6201"]["tbs"], cat.TIPOS_BIENES_SERVICIOS[1])
		self.assertEqual(datos["6901"]["tbs"], cat.TIPOS_BIENES_SERVICIOS[10])
		self.assertEqual(datos["5101"]["tbs"], cat.TIPOS_BIENES_SERVICIOS[8])
		self.assertEqual(datos["4201"]["ing"], cat.TIPOS_INGRESO[1])
		self.assertEqual(datos["210301"]["concepto"], cat.ITBIS)
		self.assertNotIn("tbs", datos["110101"])

	def test_cuentas_por_defecto_existen(self):
		numeros = {c[0] for c in cc.CUENTAS}
		for numero in cc.CUENTAS_POR_DEFECTO.values():
			self.assertIn(numero, numeros)
		for _titulo, _defecto, filas in cc.PLANTILLAS_VENTA + cc.PLANTILLAS_COMPRA:
			for fila in filas:
				self.assertIn(fila[1], numeros)


class TestAplicarCatalogo(IntegrationTestCase):
	def setUp(self):
		frappe.db.set_single_value("Configuracion DGII", "aplicar_catalogo_cuentas", 1)

	def _empresa(self, nombre, abbr, pais, moneda):
		if frappe.db.exists("Company", nombre):
			return frappe.get_doc("Company", nombre)
		return frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": nombre,
				"abbr": abbr,
				"country": pais,
				"default_currency": moneda,
				"chart_of_accounts": "Standard",
				"create_chart_of_accounts_based_on": "Standard Template",
			}
		).insert()

	def test_empresa_rd_recibe_catalogo_dgii(self):
		empresa = self._empresa("_Test Catalogo RD", "TCRD", "Dominican Republic", "DOP")
		empresa.reload()

		self.assertEqual(empresa.rd_catalogo_dgii, 1)
		self.assertEqual(empresa.default_receivable_account, "110301 - Clientes Locales - TCRD")
		self.assertEqual(empresa.default_payable_account, "210101 - Proveedores Locales - TCRD")
		self.assertEqual(empresa.default_inventory_account, "110401 - Inventario de Materia Prima - TCRD")
		self.assertEqual(empresa.round_off_account, "6607 - Redondeos - TCRD")

		cuentas = frappe.get_all("Account", filters={"company": empresa.name}, pluck="account_number")
		self.assertEqual(len(cuentas), len(cc.CUENTAS))

		itbis = frappe.get_doc("Account", "210301 - ITBIS por Pagar (Cobrado en Ventas) - TCRD")
		self.assertEqual(itbis.rd_concepto_fiscal, cat.ITBIS)
		self.assertEqual(itbis.account_type, "Tax")
		self.assertEqual(
			frappe.db.get_value("Account", "6202 - Energía Eléctrica - TCRD", "rd_tipo_bienes_servicios"),
			cat.TIPOS_BIENES_SERVICIOS[1],
		)

		plantilla = frappe.get_doc(
			"Sales Taxes and Charges Template", {"company": empresa.name, "is_default": 1}
		)
		self.assertEqual(plantilla.title, "ITBIS 18%")
		self.assertEqual(plantilla.taxes[0].rate, 18)

		retencion = frappe.get_doc(
			"Purchase Taxes and Charges Template",
			{"company": empresa.name, "title": "Servicios de Persona Jurídica - Retención 30% del ITBIS"},
		)
		self.assertEqual(retencion.taxes[1].add_deduct_tax, "Deduct")
		self.assertEqual(retencion.taxes[1].charge_type, "On Previous Row Amount")

		# Ley 30-26: retención de ISR a personas físicas al 15% (servicios técnicos 3% efectivo)
		for titulo, tasa in (
			("Servicios de Persona Física - Retención 100% ITBIS y 15% ISR", 15),
			("Servicios Técnicos de Persona Física - Retención 100% ITBIS y 3% ISR", 3),
			("Retención ISR 15% (sin ITBIS)", 15),
		):
			plantilla_isr = frappe.get_doc(
				"Purchase Taxes and Charges Template", {"company": empresa.name, "title": titulo}
			)
			self.assertEqual(plantilla_isr.taxes[-1].rate, tasa)

		# Frappe HR (si está instalado) usa la cuenta del catálogo para los reclamos de gastos
		if hrms_instalado():
			for cuenta in frappe.get_all(
				"Expense Claim Account", filters={"company": empresa.name}, pluck="default_account"
			):
				self.assertEqual(cuenta, "6111 - Reembolsos de Gastos a Empleados - TCRD")

		# La plantilla estándar de ERPNext (ITBIS 16%) no debe quedar
		self.assertFalse(
			frappe.db.exists(
				"Sales Taxes and Charges Template",
				{"company": empresa.name, "title": "Dominican Republic Tax"},
			)
		)

	def test_empresa_de_otro_pais_conserva_su_catalogo(self):
		empresa = self._empresa("_Test Catalogo MX", "TCMX", "Mexico", "MXN")
		empresa.reload()

		self.assertFalse(empresa.rd_catalogo_dgii)
		self.assertFalse(frappe.db.exists("Account", {"company": empresa.name, "account_number": "110101"}))
		self.assertFalse(cc.aplicar_catalogo_dgii(empresa.name))

	def test_no_reemplaza_si_hay_movimientos(self):
		empresa = self._empresa("_Test Catalogo RD", "TCRD", "Dominican Republic", "DOP")
		with patch.object(cc, "tiene_movimientos", return_value=True):
			self.assertFalse(cc.aplicar_catalogo_dgii(empresa.name))

	def test_respeta_configuracion_desactivada(self):
		frappe.db.set_single_value("Configuracion DGII", "aplicar_catalogo_cuentas", 0)
		empresa = self._empresa("_Test Catalogo RD Manual", "TCRM", "Dominican Republic", "DOP")
		empresa.reload()
		self.assertFalse(empresa.rd_catalogo_dgii)
