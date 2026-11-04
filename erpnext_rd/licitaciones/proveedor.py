"""Perfil de proveedor del Estado (Fase 10.2): RPE, rubros y requisitos para participar.

Los datos del RPE vienen de la API de la DGCP (api_dgcp.py) con el RNC de la empresa. La app no
cambia nada en la DGCP: si un dato está mal, se corrige en el Portal Transaccional.
"""

import re

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, today

from erpnext_rd.licitaciones import api_dgcp

DOCTYPE = "Perfil Proveedor Estado"
ACTIVO = "Activo"
ORIGEN_RPE = "RPE"
ORIGEN_MANUAL = "Manual"
# Familia UNSPSC: 8 dígitos, los 4 últimos en cero (segmento y familia)
FAMILIA_UNSPSC = re.compile(r"^\d{4}0000$")

CUMPLIDO = "Cumplido"
FALTA = "Falta"


def solo_digitos(numero: str | None) -> str:
	return re.sub(r"\D", "", numero or "")


def _fecha(valor: str | None):
	"""Fechas de la API en UTC (2007-10-23T04:00:00Z): la medianoche de RD es las 04:00 Z."""
	return getdate(valor[:10]) if valor else None


def _si(valor) -> int:
	return 1 if str(valor or "").strip().lower() in ("si", "sí") else 0


def datos_rpe(fila: dict) -> dict:
	"""Campos del perfil a partir de una fila de /proveedores."""
	return {
		"rpe": str(fila.get("rpe") or ""),
		"razon_social_rpe": (fila.get("razon_social") or "").strip(),
		"estado_rpe": fila.get("estado"),
		"fecha_registro_rpe": _fecha(fila.get("fecha_registro_rpe")),
		"provee": (fila.get("provee") or "").replace(",", ", "),
		"es_mipyme": _si(fila.get("es_mipyme")),
		"clasificacion_mipyme": fila.get("clasificacion_empresarial") or fila.get("clasificacion"),
		"certificacion_micm": _si(fila.get("certificacion_micm")),
		"vencimiento_micm": _fecha(fila.get("fecha_vencimiento_certificacion_micm")),
		"constancia_rpe": fila.get("url_certificacion"),
	}


def aplicar_rpe(doc, fila: dict, rubros: list[dict]):
	"""Pone en el perfil los datos del RPE. Los rubros del RPE se reemplazan; los manuales se quedan."""
	doc.update(datos_rpe(fila))
	doc.ultima_consulta_rpe = now_datetime()
	manuales = [r for r in doc.rubros if r.origen != ORIGEN_RPE]
	familias_rpe = {
		str(r.get("familia_unspsc") or "").strip(): (r.get("descripcion") or "").strip() for r in rubros
	}
	doc.set("rubros", [])
	for familia, descripcion in sorted(familias_rpe.items()):
		if familia:
			doc.append(
				"rubros", {"familia_unspsc": familia, "descripcion": descripcion, "origen": ORIGEN_RPE}
			)
	for r in manuales:
		if r.familia_unspsc not in familias_rpe:
			doc.append(
				"rubros",
				{"familia_unspsc": r.familia_unspsc, "descripcion": r.descripcion, "origen": ORIGEN_MANUAL},
			)


def actualizar_rpe(company: str):
	"""Consulta el RPE con el RNC de la empresa y guarda el perfil. Devuelve el documento."""
	doc = frappe.get_doc(DOCTYPE, company)
	rnc = solo_digitos(frappe.db.get_value("Company", company, "tax_id"))
	if not rnc:
		frappe.throw(_("La empresa {0} no tiene RNC («Tax ID»).").format(company))
	fila = api_dgcp.proveedor(rnc)
	if not fila:
		frappe.throw(
			_("El RNC {0} no está inscrito en el Registro de Proveedores del Estado.").format(rnc),
			title=_("Sin RPE"),
		)
	aplicar_rpe(doc, fila, api_dgcp.rubros(fila["rpe"]) if fila.get("rpe") else [])
	doc.save()
	return doc


@frappe.whitelist(methods=["POST"])
def consultar_rpe(company: str) -> dict:
	"""Botón «Consultar el RPE» del perfil."""
	frappe.has_permission(DOCTYPE, "write", company, throw=True)
	try:
		doc = actualizar_rpe(company)
	except (api_dgcp.ErrorAPIDGCP, OSError) as e:
		frappe.throw(_("No se pudo consultar la API de la DGCP: {0}").format(str(e)))
	return {"rpe": doc.rpe, "estado": doc.estado_rpe, "rubros": len(doc.rubros)}


def actualizar_perfiles():
	"""Tarea semanal: actualiza el RPE de los perfiles activos. Un error no detiene a los demás."""
	for company in frappe.get_all(DOCTYPE, filters={"habilitado": 1}, pluck="company"):
		try:
			actualizar_rpe(company)
			frappe.db.commit()  # nosemgrep: frappe-manual-commit
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=_("RPE de {0}").format(company))


def _resultado(nombre: str, ok: bool, detalle: str = "", obligatorio: bool = True) -> dict:
	return {
		"requisito": nombre,
		"estado": CUMPLIDO if ok else FALTA,
		"detalle": detalle,
		"obligatorio": obligatorio,
		"ruta": None,
	}


def _vigente(nombre: str, hasta, obligatorio: bool) -> dict:
	if not hasta:
		return _resultado(nombre, False, _("Indique hasta cuándo vale."), obligatorio)
	vence = getdate(hasta)
	if vence < getdate(today()):
		return _resultado(
			nombre, False, _("Venció el {0}.").format(frappe.format(vence, "Date")), obligatorio
		)
	return _resultado(
		nombre, True, _("Vigente hasta el {0}.").format(frappe.format(vence, "Date")), obligatorio
	)


def evaluar(doc) -> list[dict]:
	"""Requisitos del perfil con su estado (la misma tabla que el perfil tributario)."""
	lista = []
	if not doc.rpe:
		lista.append(_resultado(_("Inscrito en el RPE"), False, _("Use «Consultar el RPE».")))
	else:
		lista.append(_resultado(_("Inscrito en el RPE"), True, _("RPE {0}").format(doc.rpe)))
		lista.append(
			_resultado(
				_("RPE activo"),
				doc.estado_rpe == ACTIVO,
				_("Estado en la DGCP: {0}.").format(doc.estado_rpe or _("sin dato"))
				+ ("" if doc.estado_rpe == ACTIVO else " " + _("Actualícelo en el Portal Transaccional.")),
			)
		)
	lista.append(
		_resultado(
			_("Rubros"),
			bool(doc.rubros),
			_("{0} familias UNSPSC.").format(len(doc.rubros)) if doc.rubros else _("Agregue al menos uno."),
		)
	)
	lista.append(_vigente(_("Al día con la DGII"), doc.dgii_al_dia_hasta, obligatorio=False))
	lista.append(_vigente(_("Al día con la TSS"), doc.tss_al_dia_hasta, obligatorio=False))
	if doc.certificacion_micm:
		lista.append(_vigente(_("Certificación MIPYME del MICM"), doc.vencimiento_micm, obligatorio=False))
	return lista


@frappe.whitelist()
def requisitos(company: str) -> list[dict]:
	frappe.has_permission(DOCTYPE, "read", company, throw=True)
	return evaluar(frappe.get_doc(DOCTYPE, company))


def vencimientos(company: str) -> list[dict]:
	"""Para los recordatorios por correo: las certificaciones del perfil con su fecha de vencimiento."""
	if not frappe.db.exists(DOCTYPE, {"company": company, "habilitado": 1}):
		return []
	doc = frappe.get_cached_doc(DOCTYPE, company)
	fechas = (
		(_("Certificación de la DGII para proveedores del Estado"), doc.dgii_al_dia_hasta),
		(_("Certificación de la TSS para proveedores del Estado"), doc.tss_al_dia_hasta),
		(_("Certificación MIPYME del MICM"), doc.vencimiento_micm if doc.certificacion_micm else None),
	)
	return [{"obligacion": nombre, "vence": getdate(fecha)} for nombre, fecha in fechas if fecha]
