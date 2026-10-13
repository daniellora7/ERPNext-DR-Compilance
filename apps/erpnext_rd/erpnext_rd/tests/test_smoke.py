from frappe.tests import UnitTestCase

import erpnext_rd


class TestSmoke(UnitTestCase):
	def test_app_version(self):
		self.assertTrue(erpnext_rd.__version__)
