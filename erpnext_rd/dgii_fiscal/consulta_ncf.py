"""Verificación del NCF y del RNC del proveedor en las facturas de compra.

- NCF: consulta pública de la DGII (Oficina Virtual > Consultas > NCF, sin captcha). Dice si el
  NCF corresponde al RNC del emisor y hasta cuándo es válido. Un NCF vencido hoy sigue siendo
  válido si el comprobante es de antes de su vencimiento. Los e-NCF que la DGII aún no recibió
  responden "No encontrado": quedan sin verificar.
- RNC: el padrón de la DGII (Contribuyente DGII). Avisa si el proveedor no está ACTIVO
  (suspendido, dado de baja, cese temporal, anulado).

Un NCF que no corresponde o vencido no da derecho a adelantar el ITBIS ni a deducir el gasto. Por
defecto solo se avisa; *Configuracion DGII* puede impedir validar la factura. Si la DGII no
responde, la factura queda "Sin verificar" y se puede volver a consultar desde el formulario.
"""

import re
from datetime import datetime
from html import unescape

import frappe
import requests
from frappe import _
from frappe.utils import getdate, now_datetime

from erpnext_rd.dgii_fiscal.identificacion import identificacion_valida
from erpnext_rd.dgii_fiscal.validaciones import limpiar_identificacion, parsear_ncf

URL_CONSULTA = "https://dgii.gov.do/app/WebApps/ConsultasWeb2/ConsultasWeb/consultas/ncf.aspx"
TIEMPO_ESPERA = 10
PREFIJO = "ctl00$cphMain$"

VALIDO = "Válido"
VENCIDO = "Vencido"
NO_CORRESPONDE = "No corresponde al RNC"
SIN_VERIFICAR = "Sin verificar"
ESTADOS = (VALIDO, VENCIDO, NO_CORRESPONDE, SIN_VERIFICAR)
INVALIDOS = (VENCIDO, NO_CORRESPONDE)
ACTIVO = "ACTIVO"


def _texto(html: str, etiqueta: str) -> str:
	encontrado = re.search(rf'id="cphMain_{etiqueta}"[^>]*>(.*?)</span>', html, re.S)
	return unescape(re.sub(r"<[^>]+>", "", encontrado.group(1))).strip() if encontrado else ""


def leer_respuesta(html: str) -> frappe._dict:
	"""Resultado de la página de la DGII: estado (de ESTADOS), vigencia, razón social y mensaje."""
	resultado = frappe._dict(estado=SIN_VERIFICAR, vigencia=None, razon_social="", tipo="", mensaje="")
	estado = _texto(html, "lblEstado").upper()
	if estado:
		vigencia = _texto(html, "lblVigencia")
		try:
			resultado.vigencia = datetime.strptime(vigencia, "%d/%m/%Y").date() if vigencia else None
		except ValueError:
			resultado.vigencia = None
		resultado.razon_social = _texto(html, "lblRazonSocial")
		resultado.tipo = _texto(html, "lblTipoComprobante")
		resultado.estado = (
			VALIDO if estado == "VIGENTE" else VENCIDO if estado == "VENCIDO" else SIN_VERIFICAR
		)
		resultado.mensaje = estado.capitalize()
		return resultado

	plano = unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html)))
	if "no es correcto o no corresponde" in plano:
		resultado.estado = NO_CORRESPONDE
		resultado.mensaje = _("El NCF no es correcto o no corresponde a este RNC")
	elif "No encontrado" in plano:
		resultado.mensaje = _("La DGII aún no ha recibido este e-CF del emisor")
	return resultado


def consultar(rnc: str, ncf: str, rnc_comprador: str | None = None) -> frappe._dict:
	"""Consulta un NCF en la DGII. Si la DGII no responde, el estado es SIN_VERIFICAR."""
	sesion = requests.Session()
	sesion.headers["User-Agent"] = "Mozilla/5.0 ERPNext-RD"
	try:
		pagina = sesion.get(URL_CONSULTA, timeout=TIEMPO_ESPERA)
		pagina.raise_for_status()
		ocultos = dict(re.findall(r'<input[^>]*name="(__[A-Z]+)"[^>]*value="([^"]*)"', pagina.text))
		respuesta = sesion.post(
			URL_CONSULTA,
			data={
				**ocultos,
				f"{PREFIJO}txtRNC": limpiar_identificacion(rnc),
				f"{PREFIJO}txtNCF": ncf,
				f"{PREFIJO}txtRncComprador": limpiar_identificacion(rnc_comprador),
				f"{PREFIJO}txtCodigoSeg": "",
				f"{PREFIJO}btnConsultar": "Buscar",
			},
			timeout=TIEMPO_ESPERA,
		)
		respuesta.raise_for_status()
	except requests.RequestException:
		return frappe._dict(
			estado=SIN_VERIFICAR, vigencia=None, mensaje=_("La consulta de la DGII no respondió")
		)
	return leer_respuesta(respuesta.text)


def estado_para_la_fecha(resultado: frappe._dict, fecha) -> str:
	"""Un NCF vencido hoy es válido si el comprobante se emitió antes de su vencimiento."""
	if resultado.estado == VENCIDO and resultado.vigencia and fecha and getdate(fecha) <= resultado.vigencia:
		return VALIDO
	return resultado.estado


def estado_en_padron(numero: str | None) -> str | None:
	"""Estado del contribuyente en el padrón (ACTIVO, SUSPENDIDO...), o None si no aparece."""
	numero = limpiar_identificacion(numero)
	return frappe.db.get_value("Contribuyente DGII", numero, "estado") if numero else None


def avisar_padron(numero: str | None, nombre: str):
	"""Aviso si el contribuyente aparece en el padrón con un estado distinto de ACTIVO."""
	estado = estado_en_padron(numero)
	if estado and estado != ACTIVO:
		frappe.msgprint(
			_("{0} (RNC / Cédula {1}) aparece como {2} en el padrón de la DGII.").format(
				frappe.bold(nombre), numero, frappe.bold(estado)
			),
			title=_("Contribuyente no activo"),
			indicator="orange",
		)


def _consulta_activa() -> bool:
	"""En pruebas e importaciones no se consulta a la DGII (los tests lo simulan con un mock)."""
	if frappe.flags.in_test or frappe.flags.in_import or frappe.flags.in_migrate:
		return False
	return bool(frappe.db.get_single_value("Configuracion DGII", "consultar_ncf_dgii"))


def _se_puede_consultar(doc, tipo) -> bool:
	return bool(
		doc.rd_ncf
		and parsear_ncf(doc.rd_ncf)
		and not tipo.emitido_por_comprador
		and identificacion_valida(doc.tax_id)
	)


def _rnc_empresa(company: str) -> str:
	from erpnext_rd.dgii_reportes.datos import rnc_empresa

	return rnc_empresa(company) or ""


def verificar(doc, tipo, avisar: bool = True) -> str | None:
	"""Consulta el NCF de la factura de compra y guarda el resultado en el documento."""
	if not _se_puede_consultar(doc, tipo):
		doc.rd_ncf_estado_dgii = doc.rd_ncf_vigencia_dgii = None
		return None
	comprador = _rnc_empresa(doc.company) if doc.rd_ncf.startswith("E") else None
	resultado = consultar(doc.tax_id, doc.rd_ncf, comprador)
	estado = estado_para_la_fecha(resultado, doc.bill_date or doc.posting_date)
	doc.rd_ncf_estado_dgii = estado
	doc.rd_ncf_vigencia_dgii = resultado.vigencia
	if avisar and estado in INVALIDOS:
		mensaje = (
			_("El NCF {0} venció el {1}, antes de la fecha del comprobante.").format(
				doc.rd_ncf, frappe.format(resultado.vigencia, "Date")
			)
			if estado == VENCIDO
			else _("La DGII indica que el NCF {0} no es correcto o no corresponde al RNC {1}.").format(
				doc.rd_ncf, doc.tax_id
			)
		)
		frappe.msgprint(
			mensaje + " " + _("Sin un NCF válido no se puede adelantar el ITBIS ni deducir el gasto."),
			title=_("NCF del proveedor no válido"),
			indicator="orange",
		)
	return estado


def al_validar_compra(doc, tipo):
	"""Desde ncf.validar_compra: consulta solo si cambió el NCF o el proveedor (o nunca se consultó)."""
	cambio = doc.is_new() or any(doc.has_value_changed(c) for c in ("rd_ncf", "tax_id", "supplier"))
	if not cambio and doc.rd_ncf_estado_dgii:
		return
	if cambio and not tipo.emitido_por_comprador:
		avisar_padron(doc.tax_id, doc.supplier_name or doc.supplier)
	if _consulta_activa():
		verificar(doc, tipo)


def antes_de_validar_compra(doc):
	"""Desde ncf.antes_de_validar_compra: bloquea si así se configuró."""
	if doc.rd_ncf_estado_dgii in INVALIDOS and frappe.db.get_single_value(
		"Configuracion DGII", "bloquear_ncf_invalido"
	):
		frappe.throw(
			_(
				"El NCF {0} figura como «{1}» en la DGII. Corrija el NCF o pida al proveedor uno válido."
			).format(doc.rd_ncf, _(doc.rd_ncf_estado_dgii)),
			title=_("NCF del proveedor no válido"),
		)


@frappe.whitelist()
def verificar_factura(name: str) -> dict:
	"""Botón de la factura de compra: vuelve a consultar el NCF en la DGII (también ya validada)."""
	doc = frappe.get_doc("Purchase Invoice", name)
	doc.check_permission("write")
	tipo = frappe.get_cached_doc("Tipo Comprobante Fiscal", doc.rd_tipo_comprobante)
	if not _se_puede_consultar(doc, tipo):
		frappe.throw(_("Esta factura no tiene un NCF del proveedor que se pueda consultar."))
	estado = verificar(doc, tipo, avisar=False)
	doc.db_set(
		{
			"rd_ncf_estado_dgii": estado,
			"rd_ncf_vigencia_dgii": doc.rd_ncf_vigencia_dgii,
		},
		update_modified=False,
	)
	return {"estado": estado, "vigencia": doc.rd_ncf_vigencia_dgii, "consultado": now_datetime()}
