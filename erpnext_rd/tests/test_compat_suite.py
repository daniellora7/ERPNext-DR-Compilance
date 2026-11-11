import unittest

import frappe
from frappe.utils import get_url


class TestFileCompatSuite(unittest.TestCase):
	"""Frappe Suite develop llama File.get_site_url_prefix (Frappe v17); compat_suite lo agrega en v16."""

	def _archivo(self, url):
		return frappe.get_doc({"doctype": "File", "file_url": url, "is_private": 1})

	def test_prefijo_del_sitio(self):
		self.assertEqual(self._archivo(get_url() + "/private/files/a.xml").get_site_url_prefix(), get_url())
		self.assertEqual(self._archivo("/private/files/a.xml").get_site_url_prefix(), "")
		self.assertEqual(self._archivo("https://otro.example/private/files/a.xml").get_site_url_prefix(), "")

	def test_ruta_con_puntos_sigue_bloqueada(self):
		"""El método solo deja correr la validación de Suite; `..` en la URL sigue rechazado."""
		if "suite" not in frappe.get_installed_apps():
			self.skipTest("Frappe Suite no instalada")
		with self.assertRaises(frappe.ValidationError):
			self._archivo("/private/files/../../site_config.json").insert(ignore_permissions=True)
