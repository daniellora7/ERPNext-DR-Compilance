"""Archivo de autodeterminación mensual de la TSS: formato de ancho fijo (instructivo v6.0)."""

import frappe
from frappe.tests import IntegrationTestCase

from erpnext_rd.nomina_rd import tss
from erpnext_rd.tests.test_empleado import cedula_valida


def fila(**datos):
	return {
		"employee": "HR-EMP-0001",
		"clave_nomina": "001",
		"tipo_documento": "C",
		"documento": "00100000001",
		"nombres": "José Ramón",
		"primer_apellido": "Peña",
		"segundo_apellido": "Núñez",
		"sexo": "M",
		"fecha_nacimiento": "1990-03-07",
		"salario_ss": 80_000,
		"salario_isr": 80_000,
		"otras_remuneraciones": 10_000,
		"tipo_ingreso": "0001",
		"regalia": 0,
		"prestaciones": 0,
		**datos,
	}


class TestArchivoTSS(IntegrationTestCase):
	def test_posiciones_del_detalle(self):
		d = tss.linea_detalle(fila())
		self.assertEqual(len(d), 312)
		self.assertEqual(d[0:4], "D001")  # tipo de registro y clave de nómina (1-4)
		self.assertEqual(d[4], "C")  # tipo de documento (5)
		self.assertEqual(d[5:30], "00100000001".ljust(25))  # documento (6-30)
		self.assertEqual(d[30:80].rstrip(), "JOSE RAMON")  # nombres (31-80), sin tildes
		self.assertEqual(d[80:120].rstrip(), "PENA")  # primer apellido (81-120)
		self.assertEqual(d[120:160].rstrip(), "NUNEZ")  # segundo apellido (121-160)
		self.assertEqual(d[160], "M")  # sexo (161)
		self.assertEqual(d[161:169], "07031990")  # nacimiento DDMMAAAA (162-169)
		self.assertEqual(d[169:185], "0000000080000.00")  # salario SS (170-185)
		self.assertEqual(d[185:201], "0000000000000.00")  # aporte voluntario (186-201)
		self.assertEqual(d[201:217], "0000000000000.00")  # salario ISR igual al SS: en ceros (202-217)
		self.assertEqual(d[217:233], "0000000010000.00")  # otras remuneraciones (218-233)
		self.assertEqual(d[233:244], " " * 11)  # agente de retención (234-244)
		self.assertEqual(d[308:312], "0001")  # tipo de ingreso (309-312)

	def test_salario_isr_distinto(self):
		d = tss.linea_detalle(fila(salario_isr=75_000.5))
		self.assertEqual(d[201:217], "0000000075000.50")

	def test_ingresos_exentos_al_final(self):
		d = tss.linea_detalle(fila(regalia=30_000, prestaciones=114_141.74))
		self.assertEqual(len(d), 366)
		self.assertEqual(d[312:330], "010000000030000.00")  # regalía (313-330)
		self.assertEqual(d[330:348], "020000000114141.74")  # preaviso y cesantía (331-348)
		self.assertEqual(d[348:366], "030000000000000.00")  # pensión alimenticia (349-366)

	def test_documento_del_trabajador(self):
		def emp(**datos):
			base = {"rd_cedula": None, "rd_nss": None, "passport_number": None, "rd_numero_documento": None}
			return frappe._dict({**base, **datos})

		cedula = cedula_valida("0010000004")
		self.assertEqual(tss.documento(emp(rd_cedula=cedula))[:2], ("C", cedula))
		# Cédula que no valida: va igual, con observación
		tipo, _numero, avisos = tss.documento(emp(rd_cedula=cedula[:10] + str((int(cedula[10]) + 1) % 10)))
		self.assertEqual((tipo, len(avisos)), ("C", 1))
		# Extranjero: NSS antes que pasaporte
		self.assertEqual(tss.documento(emp(rd_nss="12345678", passport_number="AB1"))[:2], ("N", "12345678"))
		self.assertEqual(tss.documento(emp(passport_number="ab-123"))[:2], ("P", "AB123"))
		# Otro documento sin NSS: la TSS no lo recibe
		tipo, _numero, avisos = tss.documento(emp(rd_tipo_documento="Otro", rd_numero_documento="MIG-1"))
		self.assertIsNone(tipo)
		self.assertIn("NSS", avisos[0])

	def test_rectificativa(self):
		d = tss.linea_rectificativa(fila())
		self.assertEqual(len(d), 258)
		self.assertEqual(d[0:3], "DNC")  # detalle, trabajador normal, cédula (1-3)
		self.assertEqual(d[3:28], "00100000001".ljust(25))  # documento (4-28)
		self.assertEqual(d[28:78].rstrip(), "JOSE RAMON")  # nombres (29-78)
		self.assertEqual(d[159:167], "07031990")  # nacimiento (160-167)
		self.assertEqual(d[167:183], "0000000080000.00")  # salario ISR, siempre (168-183)
		self.assertEqual(d[183:199], "0000000010000.00")  # otras remuneraciones (184-199)
		self.assertEqual(d[199:210], " " * 11)  # agente de retención (200-210)
		con_exentos = tss.linea_rectificativa(fila(regalia=30_000, tipo_ingreso="0006"))
		self.assertEqual((len(con_exentos), con_exentos[1]), (312, "P"))
		self.assertEqual(con_exentos[258:276], "010000000030000.00")  # regalía (259-276)

	def test_encabezados(self):
		_nombre, am = tss.armar_archivo("101000001", "AM", 2026, 10, ["D"])
		self.assertEqual(am.split("\r\n")[0], "EAM  101000001102026")
		nombre, rt = tss.armar_archivo("101000001", "RT", 2026, 10, ["D"])
		self.assertEqual(nombre, "RT_101000001_102026.txt")
		self.assertEqual(rt.split("\r\n")[0], "ERT    101000001102026")  # proceso en 4 posiciones

	def test_novedad(self):
		from erpnext_rd.nomina_rd import novedades

		d = novedades.linea_novedad(fila(tipo_novedad="SA", fecha_inicio="2026-10-15", fecha_fin=None))
		self.assertEqual(len(d), 330)
		self.assertEqual(d[0:6], "D001SA")  # detalle, clave de nómina, tipo de novedad (1-6)
		self.assertEqual(d[6:14], "15102026")  # fecha de inicio (7-14)
		self.assertEqual(d[14:22], " " * 8)  # fecha de fin, solo licencias (15-22)
		self.assertEqual(d[22], "C")  # tipo de documento (23)
		self.assertEqual(d[23:48], "00100000001".ljust(25))  # documento (24-48)
		self.assertEqual(d[187:203], "0000000080000.00")  # salario SS (188-203)
		self.assertEqual(d[326:330], "0001")  # tipo de ingreso (327-330)
		vacaciones = novedades.linea_novedad(
			fila(tipo_novedad="VC", fecha_inicio="2026-10-05", fecha_fin="2026-10-22", prestaciones=1)
		)
		self.assertEqual((len(vacaciones), vacaciones[14:22]), (384, "22102026"))
