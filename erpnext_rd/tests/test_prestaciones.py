"""Prestaciones del Código de Trabajo (preaviso y cesantía) y feriados de RD, sin documentos."""

import unittest

import frappe

from erpnext_rd.nomina_rd import feriados, prestaciones


def tramos(lista):
	return [frappe._dict(desde_meses=d, hasta_meses=h, dias=dias, por_cada_anio=p) for d, h, dias, p in lista]


CESANTIA = tramos(prestaciones.TRAMOS_CESANTIA)
PREAVISO = tramos(prestaciones.TRAMOS_PREAVISO)


class TestPrestacionesRD(unittest.TestCase):
	def test_meses_de_servicio(self):
		# La fecha de salida es el último día trabajado
		self.assertEqual(prestaciones.meses_de_servicio("2025-01-01", "2025-12-31"), 12)
		self.assertEqual(prestaciones.meses_de_servicio("2025-01-15", "2025-04-13"), 2)
		self.assertEqual(prestaciones.meses_de_servicio("2025-01-15", "2025-04-14"), 3)

	def test_cesantia_art_80(self):
		casos = {
			2: 0,  # menos de 3 meses
			4: 6,  # 3 a 6 meses
			8: 13,  # 6 a 12 meses
			12: 21,
			31: 2 * 21 + 13,  # 2 años y 7 meses
			59: 4 * 21 + 13,
			72: 6 * 23,  # desde 5 años, 23 días por cada año
			88: 7 * 23 + 6,  # 7 años y 4 meses
		}
		for meses, dias in casos.items():
			self.assertEqual(prestaciones.dias_de_prestacion(meses, CESANTIA), dias, f"{meses} meses")

	def test_preaviso_art_76(self):
		for meses, dias in {2: 0, 3: 7, 7: 14, 12: 28, 120: 28}.items():
			self.assertEqual(prestaciones.dias_de_prestacion(meses, PREAVISO), dias, f"{meses} meses")


class TestFeriadosRD(unittest.TestCase):
	def test_feriados_con_traslados_ley_139_97(self):
		lista = frappe.new_doc("Holiday List")
		lista.update({"holiday_list_name": "_Test", "from_date": "2027-01-01", "to_date": "2027-12-31"})
		feriados.agregar_feriados(lista, "2027-01-01", "2027-12-31", "Sunday")
		fechas = {str(h.holiday_date): h for h in lista.holidays}

		# Reyes (miércoles 6) pasa al lunes 4; Duarte (martes 26) al lunes 25; el 1 de mayo cae sábado
		self.assertIn("2027-01-04", fechas)
		self.assertNotIn("2027-01-06", fechas)
		self.assertIn("2027-01-25", fechas)
		self.assertIn("2027-05-01", fechas)
		self.assertEqual(fechas["2027-12-25"].description, "Día de Navidad")
		self.assertEqual(sum(1 for h in lista.holidays if h.weekly_off), 52)

		# Sin repetir fechas al volver a correr
		total = len(lista.holidays)
		feriados.agregar_feriados(lista, "2027-01-01", "2027-12-31", "Sunday")
		self.assertEqual(len(lista.holidays), total)

	def test_lista_por_defecto_del_sitio(self):
		if not frappe.get_all("Company", filters={"country": "Dominican Republic"}, limit=1):
			self.skipTest("sin empresas RD")
		feriados.asegurar_lista_feriados()
		self.assertTrue(frappe.db.exists("Holiday List", feriados.LISTA))
		hasta = frappe.db.get_value("Holiday List", feriados.LISTA, "to_date")
		self.assertGreaterEqual(str(hasta), f"{frappe.utils.getdate().year + 1}-12-31")
		frappe.db.rollback()
