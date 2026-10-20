from datetime import date
from unittest.mock import MagicMock, patch

import requests
from frappe.tests import UnitTestCase

from erpnext_rd.dgii_fiscal import consulta_ncf


def pagina(cuerpo: str) -> str:
	return f"""<html><body><form>
<input type="hidden" name="__VIEWSTATE" id="__VIEWSTATE" value="abc" />
<input type="hidden" name="__EVENTVALIDATION" id="__EVENTVALIDATION" value="def" />
{cuerpo}</form></body></html>"""


ENCONTRADO = pagina(
	"""<table><tr><th>RNC / Cédula</th><td><span id="cphMain_lblRncCedula">101010632</span></td></tr>
<tr><th>Nombre / Razón Social</th><td><span id="cphMain_lblRazonSocial">BANCO POPULAR DOMINICANO S A</span></td></tr>
<tr><th>Tipo de comprobante</th><td><span id="cphMain_lblTipoComprobante">FACTURA DE CR&Eacute;DITO FISCAL</span></td></tr>
<tr><th>Estado</th><td><span id="cphMain_lblEstado">{estado}</span></td></tr>
<tr><th>Válido hasta</th><td><span id="cphMain_lblVigencia">31/12/2019</span></td></tr></table>
<span id="cphMain_lblInformacion">El NCF digitado es válido.</span>"""
)
NO_CORRESPONDE = pagina(
	'<span id="cphMain_lblMensaje">El Número de Comprobante Fiscal ingresado no es correcto o no '
	"corresponde a este RNC</span>"
)


class TestConsultaNCF(UnitTestCase):
	def test_leer_respuesta(self):
		r = consulta_ncf.leer_respuesta(ENCONTRADO.replace("{estado}", "VENCIDO"))
		self.assertEqual(r.estado, consulta_ncf.VENCIDO)
		self.assertEqual(r.vigencia, date(2019, 12, 31))
		self.assertEqual(r.tipo, "FACTURA DE CRÉDITO FISCAL")
		self.assertEqual(
			consulta_ncf.leer_respuesta(ENCONTRADO.replace("{estado}", "VIGENTE")).estado, consulta_ncf.VALIDO
		)
		self.assertEqual(consulta_ncf.leer_respuesta(NO_CORRESPONDE).estado, consulta_ncf.NO_CORRESPONDE)
		self.assertEqual(
			consulta_ncf.leer_respuesta(pagina("No encontrado")).estado, consulta_ncf.SIN_VERIFICAR
		)

	def test_vencido_segun_la_fecha_del_comprobante(self):
		r = consulta_ncf.leer_respuesta(ENCONTRADO.replace("{estado}", "VENCIDO"))
		self.assertEqual(consulta_ncf.estado_para_la_fecha(r, "2019-11-30"), consulta_ncf.VALIDO)
		self.assertEqual(consulta_ncf.estado_para_la_fecha(r, "2020-01-02"), consulta_ncf.VENCIDO)

	def test_envia_el_formulario_de_la_dgii(self):
		sesion = MagicMock()
		sesion.get.return_value = MagicMock(text=pagina(""))
		sesion.post.return_value = MagicMock(text=NO_CORRESPONDE)
		with patch.object(consulta_ncf.requests, "Session", return_value=sesion):
			r = consulta_ncf.consultar("101-01063-2", "B0100000001")
		self.assertEqual(r.estado, consulta_ncf.NO_CORRESPONDE)
		datos = sesion.post.call_args.kwargs["data"]
		self.assertEqual(datos["__VIEWSTATE"], "abc")
		self.assertEqual(datos["ctl00$cphMain$txtRNC"], "101010632")
		self.assertEqual(datos["ctl00$cphMain$txtNCF"], "B0100000001")

	def test_sin_respuesta_queda_sin_verificar(self):
		sesion = MagicMock()
		sesion.get.side_effect = requests.ConnectionError()
		with patch.object(consulta_ncf.requests, "Session", return_value=sesion):
			self.assertEqual(
				consulta_ncf.consultar("101010632", "B0100000001").estado, consulta_ncf.SIN_VERIFICAR
			)
