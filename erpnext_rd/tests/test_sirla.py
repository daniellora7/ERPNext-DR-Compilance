"""Planillas DGT-3 / DGT-4 del SIRLA: formato de ancho fijo."""

from frappe.tests import IntegrationTestCase

from erpnext_rd.nomina_rd import sirla


def fila(**datos):
	return {
		"employee": "HR-EMP-0001",
		"novedad": "NI",
		"tipo_documento": "C",
		"documento": "00100000001",
		"nombres": "José Ramón",
		"primer_apellido": "Peña",
		"segundo_apellido": "Núñez",
		"fecha_nacimiento": "1990-03-07",
		"sexo": "M",
		"salario": 80_000,
		"fecha_ingreso": "2025-01-01",
		"fecha_salida": None,
		"ocupacion": "2411",
		"cargo": "Contador",
		"inicio_vacaciones": "2026-07-01",
		"fin_vacaciones": "2026-07-18",
		"turno": "1",
		"localidad": "0001",
		"nacionalidad": "",
		"fecha_cambio": None,
		"nivel_educativo": "6",
		"discapacidad": "",
		**datos,
	}


class TestPlanillasSIRLA(IntegrationTestCase):
	def test_detalle_dgt3(self):
		d = sirla.linea(fila(), sirla.DGT3)
		self.assertEqual(len(d), 443)
		self.assertEqual(d[0:5], "DNI C")  # registro, novedad (2-4), tipo de documento (5)
		self.assertEqual(d[5:30], "00100000001".ljust(25))  # documento (6-30)
		self.assertEqual(d[30:80].rstrip(), "JOSE RAMON")  # nombres (31-80)
		self.assertEqual(d[160:168], "07031990")  # nacimiento (161-168)
		self.assertEqual(d[168], "M")  # sexo (169)
		self.assertEqual(d[169:185], "0000000080000.00")  # salario (170-185)
		self.assertEqual(d[185:193], "01012025")  # ingreso (186-193)
		self.assertEqual(d[193:199], "002411")  # ocupación (194-199)
		self.assertEqual(d[199:349].rstrip(), "CONTADOR")  # cargo (200-349)
		self.assertEqual(d[349:365], "0107202618072026")  # vacaciones (350-365)
		self.assertEqual(d[365:371], "000001")  # turno (366-371)
		self.assertEqual(d[371:377], "000001")  # localidad (372-377)
		self.assertEqual(d[388:393], "00006")  # nivel educativo (389-393)

	def test_detalle_dgt4(self):
		d = sirla.linea(fila(novedad="NC", fecha_cambio="2026-10-05", nacionalidad="VEN"), sirla.DGT4)
		self.assertEqual(len(d), 451)
		self.assertEqual(d[1:4], "NC ")
		self.assertEqual(d[193:201], "00000000")  # fecha de salida (194-201): no aplica
		self.assertEqual(d[201:207], "002411")  # ocupación (202-207)
		self.assertEqual(d[379:385], "000001")  # localidad (380-385)
		self.assertEqual(d[385:388], "VEN")  # nacionalidad (386-388)
		self.assertEqual(d[388:396], "05102026")  # fecha del cambio (389-396)
		self.assertEqual(d[396:401], "00006")  # nivel educativo (397-401)
