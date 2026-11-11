# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

"""Ofertas al Estado (Fase 10.5): oportunidades de procesos de compra con sus pendientes."""

import frappe
from frappe import _

from erpnext_rd.licitaciones import ofertas


def execute(filters=None):
	filters = frappe._dict(filters or {})
	return columnas(), datos(filters)


def columnas() -> list[dict]:
	return [
		{
			"fieldname": "oportunidad",
			"label": _("Oportunidad"),
			"fieldtype": "Link",
			"options": "Opportunity",
			"width": 150,
		},
		{
			"fieldname": "proceso",
			"label": _("Proceso"),
			"fieldtype": "Link",
			"options": "Proceso Compra DGCP",
			"width": 190,
		},
		{"fieldname": "titulo", "label": _("Objeto"), "fieldtype": "Data", "width": 260},
		{"fieldname": "institucion", "label": _("Institución"), "fieldtype": "Data", "width": 200},
		{"fieldname": "estado", "label": _("Estado de la oferta"), "fieldtype": "Data", "width": 130},
		{"fieldname": "cierre", "label": _("Recibe ofertas hasta"), "fieldtype": "Datetime", "width": 160},
		{
			"fieldname": "monto",
			"label": _("Monto de la oferta"),
			"fieldtype": "Currency",
			"options": "moneda",
			"width": 140,
		},
		{
			"fieldname": "moneda",
			"label": _("Moneda"),
			"fieldtype": "Link",
			"options": "Currency",
			"width": 70,
		},
		{
			"fieldname": "documentos_pendientes",
			"label": _("Documentos pendientes"),
			"fieldtype": "Int",
			"width": 110,
		},
		{
			"fieldname": "garantias_por_gestionar",
			"label": _("Garantías por gestionar"),
			"fieldtype": "Int",
			"width": 110,
		},
	]


def datos(filters) -> list[dict]:
	condiciones = {"rd_proceso_dgcp": ("is", "set")}
	if filters.company:
		condiciones["company"] = filters.company
	if filters.estado:
		condiciones["rd_estado_oferta"] = filters.estado
	elif not filters.incluir_cerradas:
		condiciones["rd_estado_oferta"] = ("in", ofertas.ABIERTAS)
	filas = frappe.get_list(
		"Opportunity",
		filters=condiciones,
		fields=[
			"name",
			"rd_proceso_dgcp",
			"title",
			"customer_name",
			"rd_estado_oferta",
			"rd_cierre_ofertas",
			"rd_monto_oferta",
			"opportunity_amount",
			"currency",
		],
		order_by="rd_cierre_ofertas asc",
	)
	nombres = [f.name for f in filas] or [""]
	pendientes = _contar("Documento Oferta Estado", nombres, {"obligatorio": 1, "estado": ofertas.PENDIENTE})
	por_gestionar = _contar("Garantia Oferta Estado", nombres, {"estado": "Por gestionar"})
	return [
		{
			"oportunidad": f.name,
			"proceso": f.rd_proceso_dgcp,
			"titulo": f.title,
			"institucion": f.customer_name,
			"estado": _(f.rd_estado_oferta) if f.rd_estado_oferta else None,
			"cierre": f.rd_cierre_ofertas,
			"monto": f.rd_monto_oferta or f.opportunity_amount,
			"moneda": f.currency,
			"documentos_pendientes": pendientes.get(f.name, 0),
			"garantias_por_gestionar": por_gestionar.get(f.name, 0),
		}
		for f in filas
	]


def _contar(doctype: str, padres: list[str], filtros: dict) -> dict[str, int]:
	filas = frappe.get_all(
		doctype,
		filters={"parenttype": "Opportunity", "parent": ("in", padres), **filtros},
		fields=["parent", {"COUNT": "*", "as": "cantidad"}],
		group_by="parent",
	)
	return {f.parent: f.cantidad for f in filas}
