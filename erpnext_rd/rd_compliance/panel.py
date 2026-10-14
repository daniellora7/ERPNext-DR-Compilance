"""API del Panel RD Compliance (frontend frappe-ui en /rd-compliance).

Solo lee: reúne en una llamada el estado fiscal del período (secuencias NCF, formatos 606-609,
IT-1, IR-17, avisos y padrón) reutilizando los mismos cálculos de los reportes, así los números
del panel cuadran con los TXT.
"""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, flt, getdate, nowdate

from erpnext_rd.dgii_fiscal.ncf import PAIS, es_empresa_rd
from erpnext_rd.dgii_reportes import declaraciones
from erpnext_rd.dgii_reportes.formatos import ROLES, obtener

DIA_VENCE_FORMATOS = 15  # 606, 607, 608 y 609: día 15 del mes siguiente
MAX_AVISOS = 50

# Columna del monto principal de cada formato (None: el 608 no lleva montos)
MONTO_FORMATO = {
	"606": "total_monto_facturado",
	"607": "monto_facturado",
	"608": None,
	"609": "monto_facturado",
}


@frappe.whitelist()
def contexto() -> dict:
	"""Empresas RD a las que el usuario tiene acceso y el período sugerido (el mes anterior)."""
	frappe.only_for(ROLES)
	empresas = frappe.get_list(
		"Company", filters={"country": PAIS}, fields=["name", "company_name", "tax_id"], order_by="name"
	)
	predeterminada = frappe.defaults.get_user_default("Company")
	nombres = [e.name for e in empresas]
	anterior = getdate(add_months(nowdate(), -1))
	return {
		"empresas": empresas,
		"empresa": predeterminada if predeterminada in nombres else (nombres[0] if nombres else None),
		"anio": anterior.year,
		"mes": anterior.month,
		"hrms": "hrms" in frappe.get_installed_apps(),
	}


@frappe.whitelist()
def resumen(company: str, anio: int, mes: int) -> dict:
	"""Estado de cumplimiento de una empresa RD en un período."""
	frappe.only_for(ROLES)
	anio, mes = cint(anio), cint(mes)
	if not es_empresa_rd(company):
		frappe.throw(_("El panel solo aplica a empresas de República Dominicana"))
	frappe.has_permission("Company", doc=company, throw=True)

	filas = {formato: obtener(formato, company, anio, mes) for formato in MONTO_FORMATO}
	it1 = declaraciones.resumen_it1(company, anio, mes, filas_606=filas["606"], filas_607=filas["607"])
	ir17 = declaraciones.resumen_ir17(company, anio, mes, filas_606=filas["606"], filas_609=filas["609"])

	return {
		"periodo": {"anio": anio, "mes": mes},
		"secuencias": secuencias(company),
		"formatos": [_estado_formato(formato, filas[formato], anio, mes) for formato in MONTO_FORMATO],
		"it1": {
			"itbis_facturado": it1.itbis_neto_ventas,
			"itbis_deducible": it1.itbis_deducible,
			"itbis_a_pagar": it1.itbis_a_pagar,
			"itbis_retenido_a_terceros": it1.itbis_retenido_a_terceros,
			"total_a_pagar": it1.total_a_pagar,
			"nuevo_saldo_favor": it1.nuevo_saldo_favor,
			"vence": it1.vence,
		},
		"ir17": {
			"total_isr": ir17.total_isr,
			"total_base": ir17.total_base,
			"grupos": [{"concepto": g.concepto, "base": g.base, "isr": g.isr} for g in ir17.grupos],
			"vence": ir17.vence,
		},
		"avisos": _avisos(filas),
		"padron": _padron(),
	}


def secuencias(company: str) -> list[dict]:
	"""Secuencias NCF por tipo de comprobante con su nivel de alerta según *Configuracion DGII*.

	Muestra las habilitadas; si un tipo ya no tiene ninguna (al agotarse se deshabilitan solas),
	muestra la última que tuvo, para avisar que hay que registrar una nueva."""
	config = frappe.get_cached_doc("Configuracion DGII")
	porcentaje_alerta = flt(config.porcentaje_alerta or 80)
	limite_vence = getdate(add_days(nowdate(), cint(config.dias_alerta_vencimiento or 30)))
	hoy = getdate(nowdate())

	por_tipo = {}
	for s in frappe.get_list(
		"Secuencia NCF",
		filters={"company": company},
		fields=[
			"name",
			"tipo_comprobante",
			"serie",
			"habilitada",
			"desde",
			"hasta",
			"siguiente",
			"fecha_vencimiento",
		],
		order_by="tipo_comprobante, creation desc",
	):
		por_tipo.setdefault(s.tipo_comprobante, []).append(s)

	elegidas = []
	for lista in por_tipo.values():
		habilitadas = [s for s in lista if s.habilitada]
		elegidas += habilitadas or lista[:1]

	resultado = []
	for s in elegidas:
		total = max(cint(s.hasta) - cint(s.desde) + 1, 1)
		disponibles = max(cint(s.hasta) - cint(s.siguiente) + 1, 0)
		usado = round(100 * (total - disponibles) / total, 1)
		vence = getdate(s.fecha_vencimiento) if s.fecha_vencimiento else None

		if not disponibles:
			estado = "agotada"
		elif not s.habilitada:
			estado = "deshabilitada"
		elif vence and vence < hoy:
			estado = "vencida"
		elif usado >= porcentaje_alerta:
			estado = "por_agotarse"
		elif vence and vence <= limite_vence:
			estado = "por_vencer"
		else:
			estado = "ok"

		resultado.append(
			{
				"name": s.name,
				"tipo_comprobante": s.tipo_comprobante,
				"serie": s.serie,
				"total": total,
				"disponibles": disponibles,
				"usado": usado,
				"fecha_vencimiento": vence,
				"estado": estado,
			}
		)
	return resultado


def _estado_formato(formato: str, filas: list[dict], anio: int, mes: int) -> dict:
	en_txt = [f for f in filas if f.get("_en_txt", True)]
	campo = MONTO_FORMATO[formato]
	return {
		"formato": formato,
		"reporte": f"Formato {formato} DGII",
		"registros": len(en_txt),
		"con_avisos": sum(1 for f in filas if f.get("_avisos")),
		"monto": sum(flt(f.get(campo)) for f in en_txt) if campo else None,
		"vence": declaraciones.vencimiento(anio, mes, DIA_VENCE_FORMATOS),
	}


def _avisos(filas: dict[str, list[dict]]) -> dict:
	"""Registros con observaciones (RNC inválido, NCF duplicado, datos faltantes), para corregir
	antes de enviar."""
	lista = [
		{
			"formato": formato,
			"doctype": f.get("_doctype"),
			"documento": f.get("_documento"),
			"aviso": f["_avisos"],
		}
		for formato, registros in filas.items()
		for f in registros
		if f.get("_avisos")
	]
	return {"total": len(lista), "lista": lista[:MAX_AVISOS]}


def _padron() -> dict:
	config = frappe.get_cached_doc("Configuracion DGII")
	ultima = config.padron_ultima_sincronizacion
	# Un Datetime vacío en un Single puede venir como 0001-01-01
	if ultima and getdate(ultima).year < 2000:
		ultima = None
	return {"registros": cint(config.padron_registros), "ultima_sincronizacion": ultima}
