"""Monitor de e-CF del Panel RD Compliance (/rd-compliance/ecf).

Solo lee: reúne en una llamada lo que hay que vigilar de la facturación electrónica de una empresa.

- El emisor: si está configurado y habilitado, el ambiente y el vencimiento del certificado.
- Los envíos del período por estado (aceptados, condicionales, rechazados, en proceso...).
- Lo que pide acción: e-CF en contingencia (con su plazo de 72 horas), rechazados o con error,
  entregas al comprador fallidas, facturas con comprobante electrónico que aún no tienen e-CF y, en una
  contingencia declarada, las facturas de la serie B sin su e-CF de reemplazo (ecf/contingencia.py).
- Los e-CF recibidos de proveedores con la aprobación comercial pendiente.

Las acciones (reenviar, entregar al comprador) usan los métodos de `emision`, con sus permisos.
"""

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, getdate, now_datetime, nowdate

from erpnext_rd.dgii_fiscal.ncf import es_empresa_rd
from erpnext_rd.dgii_reportes.formatos import ROLES
from erpnext_rd.ecf import contingencia
from erpnext_rd.ecf.emision import (
	ACEPTADOS,
	CONTINGENCIA,
	DOCTYPES,
	EMISOR,
	ENVIO,
	INTENTOS_ENTREGA,
	TIPOS_CON_COMPRADOR,
)

ESTADOS = ("Firmado", "En proceso", CONTINGENCIA, "Aceptado", "Aceptado condicional", "Rechazado", "Error")
CON_PROBLEMAS = ("Rechazado", "Error", "Aceptado condicional")
ENTREGA_FALLIDA = ("Error", "No recibido")
DIAS_AVISO_CERTIFICADO = 30
MAXIMO = 50
CAMPOS_ENVIO = [
	"name",
	"encf",
	"tipo_ecf",
	"estado",
	"es_rfce",
	"tipo_documento",
	"documento",
	"fecha_firma",
	"mensajes",
	"intentos",
	"proximo_intento",
	"estado_comprador",
	"intentos_comprador",
	"creation",
]


@frappe.whitelist()
def resumen(company: str, dias: int = 30) -> dict:
	"""Estado de la facturación electrónica de la empresa en los últimos `dias` días."""
	frappe.only_for(ROLES)
	if not es_empresa_rd(company):
		frappe.throw(_("El monitor de e-CF solo aplica a empresas de República Dominicana"))
	frappe.has_permission("Company", doc=company, throw=True)
	dias = min(max(cint(dias) or 30, 1), 366)
	desde = add_days(nowdate(), -dias)

	return {
		"dias": dias,
		"ambiente": frappe.db.get_single_value("Configuracion DGII", "ambiente_ecf") or "TesteCF",
		# Reenviar y entregar piden escribir en el envío (Accounts Manager); los demás solo ven
		"puede_actuar": bool(frappe.has_permission(ENVIO, "write")),
		"emisor": emisor(company),
		"conteo": conteo(company, desde),
		"contingencia": con_plazo(envios(company, {"estado": CONTINGENCIA}, orden="fecha_firma asc")),
		"horas_contingencia": contingencia.horas_envio(),
		"contingencia_declarada": declarada(company),
		"reemplazos": contingencia.pendientes(company),
		"con_problemas": envios(company, {"estado": ("in", CON_PROBLEMAS), "creation": (">=", desde)}),
		"entregas": entregas(company),
		"sin_emitir": sin_emitir(company, desde),
		"recibidos": recibidos(company),
		"ultimos": envios(company, {}, limite=20),
	}


def resumen_panel(company: str) -> dict | None:
	"""Bloque del Panel de cumplimiento: los últimos 30 días y lo que pide acción. None si la empresa no
	tiene emisor e-CF ni envíos (no factura en electrónico)."""
	datos_emisor = emisor(company)
	desde = add_days(nowdate(), -30)
	cifras = conteo(company, desde)
	if not datos_emisor["configurado"] and not frappe.db.exists(ENVIO, {"company": company}):
		return None
	por_estado = cifras["por_estado"]
	en_contingencia = con_plazo(envios(company, {"estado": CONTINGENCIA}, orden="fecha_firma asc"))
	return {
		"emisor": datos_emisor,
		"total": cifras["total"],
		"aceptados": por_estado["Aceptado"] + por_estado["Aceptado condicional"],
		"rechazados": por_estado["Rechazado"] + por_estado["Error"],
		"contingencia": len(en_contingencia),
		"contingencia_vencida": sum(1 for e in en_contingencia if e["vencido"]),
		"contingencia_declarada": declarada(company),
		"reemplazos": len(contingencia.pendientes(company)),
		"sin_emitir": len(sin_emitir(company, desde)),
	}


def con_plazo(lista: list[dict]) -> list[dict]:
	"""Agrega a los e-CF en contingencia (sin conexión) el límite para enviarlos a la DGII."""
	ahora = now_datetime()
	for envio in lista:
		vence = contingencia.vence_envio(envio.get("fecha_firma") or envio.get("creation"))
		envio["vence"] = vence
		envio["vencido"] = bool(vence and vence < ahora)
	return lista


def declarada(company: str) -> dict | None:
	"""Contingencia por imposibilidad de emitir e-CF abierta hoy en el Emisor ECF, con sus días."""
	abierta = contingencia.declarada(company, nowdate())
	if not abierta:
		return None
	return {
		"desde": abierta.contingencia_desde,
		"hasta": abierta.contingencia_hasta,
		"modalidad": abierta.contingencia_modalidad,
		"dias": date_diff(nowdate(), abierta.contingencia_desde) + 1,
		"maximo": contingencia.dias_maximos(),
	}


def emisor(company: str) -> dict:
	datos = frappe.db.get_value(
		EMISOR, company, ["habilitado", "envio_automatico", "vigente_hasta", "titular"], as_dict=True
	)
	if not datos:
		return {"configurado": False}
	vence = getdate(datos.vigente_hasta) if datos.vigente_hasta else None
	restan = date_diff(vence, nowdate()) if vence else None
	if restan is None:
		certificado = "sin_fecha"
	elif restan < 0:
		certificado = "vencido"
	elif restan <= DIAS_AVISO_CERTIFICADO:
		certificado = "por_vencer"
	else:
		certificado = "vigente"
	return {
		"configurado": True,
		"habilitado": bool(datos.habilitado),
		"envio_automatico": bool(datos.envio_automatico),
		"titular": datos.titular,
		"vigente_hasta": vence,
		"dias_certificado": restan,
		"certificado": certificado,
	}


def conteo(company: str, desde) -> dict:
	"""Envíos del período por estado (todos los estados, aunque estén en cero)."""
	filas = frappe.get_list(
		ENVIO,
		filters={"company": company, "creation": (">=", desde)},
		fields=["estado", {"COUNT": "*", "as": "total"}],
		group_by="estado",
	)
	por_estado = {e: 0 for e in ESTADOS}
	for f in filas:
		por_estado[f.estado] = cint(f.total)
	return {"por_estado": por_estado, "total": sum(por_estado.values())}


def envios(company: str, filtros: dict, orden: str = "creation desc", limite: int = MAXIMO) -> list[dict]:
	return frappe.get_list(
		ENVIO,
		filters={"company": company, **filtros},
		fields=CAMPOS_ENVIO,
		order_by=orden,
		limit=limite,
	)


def entregas(company: str) -> dict:
	"""e-CF aceptados cuya entrega al comprador falló o sigue pendiente."""
	base = {
		"company": company,
		"estado": ("in", ACEPTADOS),
		"es_rfce": 0,
		"tipo_ecf": ("in", TIPOS_CON_COMPRADOR),
	}
	fallidas = envios(company, {**base, "estado_comprador": ("in", ENTREGA_FALLIDA)})
	# Vacío (nunca intentado) o «Pendiente»: «is not set» cubre el NULL y el texto vacío
	pendientes = sum(
		frappe.db.count(ENVIO, {**base, "estado_comprador": valor})
		for valor in (("is", "not set"), "Pendiente")
	)
	return {"fallidas": fallidas, "pendientes": pendientes, "maximo_intentos": INTENTOS_ENTREGA}


def sin_emitir(company: str, desde) -> list[dict]:
	"""Facturas aprobadas con comprobante electrónico (E..) que no tienen e-CF registrado."""
	resultado = []
	for doctype in DOCTYPES:
		if not frappe.get_meta(doctype).has_field("rd_tipo_comprobante"):
			continue
		facturas = frappe.get_list(
			doctype,
			filters={
				"company": company,
				"docstatus": 1,
				"rd_tipo_comprobante": ("like", "E%"),
				"posting_date": (">=", desde),
			},
			fields=["name", "rd_tipo_comprobante", "rd_ncf", "posting_date", "grand_total"],
			order_by="posting_date asc",
			limit=MAXIMO * 4,
		)
		if not facturas:
			continue
		con_envio = set(
			frappe.get_all(
				ENVIO,
				filters={"tipo_documento": doctype, "documento": ("in", [f.name for f in facturas])},
				pluck="documento",
			)
		)
		resultado += [{**f, "doctype": doctype} for f in facturas if f.name not in con_envio]
	return resultado[:MAXIMO]


def recibidos(company: str) -> dict:
	"""e-CF de proveedores con la aprobación comercial pendiente o cuyo envío falló."""
	campos = [
		"name",
		"encf",
		"tipo_ecf",
		"razon_social_emisor",
		"monto_total",
		"fecha_emision",
		"envio_aprobacion",
		"estado_dgii",
	]
	pendientes = frappe.get_list(
		"ECF Recibido",
		filters={"company": company, "estado": "Recibido", "aprobacion": "Pendiente"},
		fields=campos,
		order_by="fecha_emision asc",
		limit=MAXIMO,
	)
	con_error = frappe.get_list(
		"ECF Recibido",
		filters={"company": company, "envio_aprobacion": "Error"},
		fields=campos,
		order_by="modified desc",
		limit=MAXIMO,
	)
	return {"pendientes": pendientes, "con_error": con_error}
