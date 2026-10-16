from datetime import date
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from erpnext_rd.rd_compliance import recordatorios

EMPRESA = "_Test Empresa RD"


def vencimientos(company, anio, mes):
	return {o["obligacion"]: str(o["vence"]) for o in recordatorios.obligaciones(company, anio, mes)}


class TestRecordatorios(IntegrationTestCase):
	def setUp(self):
		frappe.db.set_single_value(
			"Configuracion DGII",
			{
				"recordatorios_activos": 1,
				"recordatorios_dias": 3,
				"recordatorios_destinatarios": "contabilidad@example.com, gerencia@example.com",
			},
		)
		frappe.clear_document_cache("Configuracion DGII", "Configuracion DGII")

	def tearDown(self):
		frappe.db.rollback()
		frappe.clear_document_cache("Configuracion DGII", "Configuracion DGII")

	def test_vencimientos_corridos_a_dia_habil(self):
		# Período septiembre 2026: el 10/10 es sábado, el 15/10 jueves y el 20/10 martes
		fechas = vencimientos(EMPRESA, 2026, 9)
		self.assertEqual(fechas["IR-17 (retenciones de ISR) de septiembre 2026"], "2026-10-12")
		self.assertEqual(fechas["Formatos 606, 607, 608 y 609 de septiembre 2026"], "2026-10-15")
		self.assertEqual(fechas["IT-1 (ITBIS) de septiembre 2026"], "2026-10-20")

	def test_avisa_dias_antes_y_el_mismo_dia(self):
		with patch.object(recordatorios, "_con_nomina", return_value=False):
			antes = recordatorios.pendientes(EMPRESA, date(2026, 10, 12), 3)
			mismo_dia = recordatorios.pendientes(EMPRESA, date(2026, 10, 15), 3)
			nada = recordatorios.pendientes(EMPRESA, date(2026, 10, 13), 3)
		self.assertEqual(
			[(o["obligacion"], o["faltan"]) for o in antes],
			[
				("IR-17 (retenciones de ISR) de septiembre 2026", 0),
				("Formatos 606, 607, 608 y 609 de septiembre 2026", 3),
			],
		)
		self.assertEqual([o["faltan"] for o in mismo_dia], [0])
		self.assertEqual(nada, [])

	def test_nomina_tss_e_ir3(self):
		with patch.object(recordatorios, "_con_nomina", return_value=True):
			fechas = vencimientos(EMPRESA, 2026, 9)
		# Tercer día hábil de octubre 2026 (1, 2 y 5: el 3 y el 4 son fin de semana)
		self.assertEqual(fechas["Pago de la TSS de septiembre 2026"], "2026-10-05")
		self.assertEqual(fechas["IR-3 (retenciones a asalariados) de septiembre 2026"], "2026-10-12")

	def test_un_correo_por_empresa_con_avisos(self):
		with (
			patch.object(recordatorios, "empresas_rd", return_value=[EMPRESA]),
			patch.object(recordatorios, "_con_nomina", return_value=False),
			patch.object(recordatorios, "secuencias_con_aviso", return_value=[]),
			patch.object(frappe, "sendmail") as sendmail,
		):
			self.assertEqual(recordatorios.enviar_recordatorios(date(2026, 10, 12)), 1)
			self.assertEqual(recordatorios.enviar_recordatorios(date(2026, 10, 13)), 0)
		kwargs = sendmail.call_args.kwargs
		self.assertEqual(kwargs["recipients"], ["contabilidad@example.com", "gerencia@example.com"])
		self.assertIn("IR-17", kwargs["message"])
		self.assertIn("Vence hoy", kwargs["message"])

	def test_desactivados_no_envian(self):
		frappe.db.set_single_value("Configuracion DGII", "recordatorios_activos", 0)
		frappe.clear_document_cache("Configuracion DGII", "Configuracion DGII")
		with patch.object(frappe, "sendmail") as sendmail:
			self.assertEqual(recordatorios.enviar_recordatorios(date(2026, 10, 12)), 0)
		sendmail.assert_not_called()

	def test_secuencias_los_lunes(self):
		secuencia = {"tipo_comprobante": "B01", "name": "B01-1", "estado": "por_agotarse", "disponibles": 5}
		with (
			patch.object(recordatorios, "empresas_rd", return_value=[EMPRESA]),
			patch.object(recordatorios, "_con_nomina", return_value=False),
			patch.object(recordatorios, "secuencias_con_aviso", return_value=[secuencia]),
			patch.object(frappe, "sendmail") as sendmail,
		):
			# Martes 13/10 sin vencimientos: no se envía; lunes 19/10: sí
			self.assertEqual(recordatorios.enviar_recordatorios(date(2026, 10, 13)), 0)
			self.assertEqual(recordatorios.enviar_recordatorios(date(2026, 10, 19)), 1)
		self.assertIn("por agotarse", sendmail.call_args.kwargs["message"])
