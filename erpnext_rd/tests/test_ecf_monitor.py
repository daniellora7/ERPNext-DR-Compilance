"""Monitor de e-CF del Panel RD Compliance: conteo por estado, lo que pide acción y el emisor."""

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, add_to_date, now_datetime, nowdate

from erpnext_rd.ecf import monitor
from erpnext_rd.tests import test_isc
from erpnext_rd.tests.test_isc import EMPRESA


class TestMonitorECF(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		test_isc.TestISC.setUpClass()

	def setUp(self):
		frappe.db.savepoint("monitor_ecf")
		frappe.db.delete("Envio ECF", {"company": EMPRESA})
		frappe.db.delete("Emisor ECF", {"company": EMPRESA})

	def tearDown(self):
		frappe.db.rollback(save_point="monitor_ecf")

	def _envio(self, encf: str, estado: str, **campos):
		return frappe.get_doc(
			{
				"doctype": "Envio ECF",
				"company": EMPRESA,
				"encf": encf,
				"tipo_ecf": encf[:3],
				"estado": estado,
				"ambiente": "TesteCF",
				**campos,
			}
		).insert(ignore_permissions=True)

	def _emisor(self, vigente_hasta, habilitado=1):
		# Sin certificado: db_insert no pasa por la validación del archivo .p12
		frappe.get_doc(
			{
				"doctype": "Emisor ECF",
				"name": EMPRESA,
				"company": EMPRESA,
				"habilitado": habilitado,
				"vigente_hasta": vigente_hasta,
			}
		).db_insert()

	def test_conteo_y_pendientes(self):
		self._envio("E310000000001", "Aceptado")
		self._envio("E310000000002", "Aceptado")
		self._envio("E310000000003", "Rechazado", mensajes="RNC del comprador inválido")
		self._envio(
			"E310000000004",
			"Contingencia",
			intentos=2,
			proximo_intento=add_to_date(now_datetime(), minutes=30),
		)
		self._envio("E310000000005", "Aceptado", estado_comprador="Error", intentos_comprador=1)
		self._envio("E320000000001", "Aceptado", es_rfce=1)

		r = monitor.resumen(EMPRESA)
		self.assertEqual(r["conteo"]["por_estado"]["Aceptado"], 4)
		self.assertEqual(r["conteo"]["por_estado"]["Rechazado"], 1)
		self.assertEqual(r["conteo"]["por_estado"]["Error"], 0, "todos los estados, aunque estén en cero")
		self.assertEqual(r["conteo"]["total"], 6)

		self.assertEqual([e.encf for e in r["contingencia"]], ["E310000000004"])
		self.assertEqual([e.encf for e in r["con_problemas"]], ["E310000000003"])
		self.assertEqual([e.encf for e in r["entregas"]["fallidas"]], ["E310000000005"])
		# Los dos E31 aceptados sin entregar; el RFCE (consumo) no se entrega al comprador
		self.assertEqual(r["entregas"]["pendientes"], 2)

	def test_periodo(self):
		viejo = self._envio("E310000000009", "Rechazado")
		frappe.db.set_value(
			"Envio ECF", viejo.name, "creation", add_days(nowdate(), -40), update_modified=False
		)
		self.assertEqual(monitor.resumen(EMPRESA, dias=30)["conteo"]["total"], 0)
		self.assertFalse(monitor.resumen(EMPRESA, dias=30)["con_problemas"])
		self.assertEqual(monitor.resumen(EMPRESA, dias=90)["conteo"]["total"], 1)

	def test_emisor_y_certificado(self):
		self.assertEqual(monitor.emisor(EMPRESA), {"configurado": False})

		self._emisor(add_days(nowdate(), 10))
		e = monitor.emisor(EMPRESA)
		self.assertEqual(
			(e["configurado"], e["certificado"], e["dias_certificado"]), (True, "por_vencer", 10)
		)

		frappe.db.set_value("Emisor ECF", EMPRESA, "vigente_hasta", add_days(nowdate(), -1))
		self.assertEqual(monitor.emisor(EMPRESA)["certificado"], "vencido")
		frappe.db.set_value("Emisor ECF", EMPRESA, "vigente_hasta", add_days(nowdate(), 200))
		self.assertEqual(monitor.emisor(EMPRESA)["certificado"], "vigente")

	def test_solo_empresas_rd(self):
		otra = frappe.get_all(
			"Company", filters={"country": ("!=", "Dominican Republic")}, pluck="name", limit=1
		)
		if not otra:
			self.skipTest("no hay empresas de otro país")
		with self.assertRaises(frappe.ValidationError):
			monitor.resumen(otra[0])

	def test_bloque_del_panel(self):
		# Sin emisor ni envíos la empresa no factura en electrónico: el panel no muestra el bloque
		self.assertIsNone(monitor.resumen_panel(EMPRESA))
		self._envio("E310000000001", "Aceptado")
		self._envio("E310000000002", "Aceptado condicional")
		self._envio("E310000000003", "Error")
		self._envio("E310000000004", "Contingencia")
		r = monitor.resumen_panel(EMPRESA)
		self.assertEqual((r["total"], r["aceptados"], r["rechazados"], r["contingencia"]), (4, 2, 1, 1))
		self.assertFalse(r["emisor"]["configurado"])
