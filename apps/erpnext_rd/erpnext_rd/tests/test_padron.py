from frappe.tests import UnitTestCase

from erpnext_rd.padron_rnc.padron import parsear_linea


class TestPadron(UnitTestCase):
	def test_parsear_linea(self):
		fila = parsear_linea(
			"03101823817|MARCO SERGIO RICARDO||SERVICIOS PERSONALES| | | | |25/06/2003|ACTIVO|NORMAL\r\n"
		)
		self.assertEqual(fila, ("03101823817", "MARCO SERGIO RICARDO", "", "SERVICIOS PERSONALES", "25/06/2003", "ACTIVO", "NORMAL"))

	def test_linea_invalida(self):
		self.assertIsNone(parsear_linea("ROOM ARCE|X||Y| | | | ||ACTIVO|NORMAL"))
		self.assertIsNone(parsear_linea("101010632|incompleta"))
