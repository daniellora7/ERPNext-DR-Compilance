# Copyright (c) 2026, ERPNext RD
# License: GNU General Public License v3. See license.txt

"""Operaciones con partes relacionadas del ejercicio, por contraparte: apoyo para la DIOR (Fase 8.3)."""

import frappe
from frappe import _
from frappe.utils import add_days, getdate

from erpnext_rd.dgii_reportes import dior
from erpnext_rd.rd_compliance import perfil


def periodo(filters) -> tuple:
	"""Fechas del filtro o, sin ellas, el último ejercicio cerrado de la empresa."""
	if filters.get("desde") and filters.get("hasta"):
		return getdate(filters.desde), getdate(filters.hasta)
	actual_desde, _actual_hasta = perfil.periodo_fiscal(filters.company)
	return perfil.periodo_fiscal(filters.company, add_days(actual_desde, -1))


def execute(filters=None):
	filters = frappe._dict(filters or {})
	if not filters.company:
		return columnas(), []
	desde, hasta = periodo(filters)
	filas = dior.operaciones(filters.company, desde, hasta)
	mensaje = _(
		"Ejercicio del {0} al {1}. La DIOR se presenta en la Oficina Virtual a más tardar el {2}, también si "
		"no hubo operaciones. Los asientos (préstamos, anticipos y otras operaciones que no son facturas) "
		"van con sus cargos y abonos: clasifíquelos en la DIOR. El estudio de precios de transferencia se "
		"hace aparte."
	).format(
		frappe.format(desde, "Date"),
		frappe.format(hasta, "Date"),
		frappe.format(dior.fecha_limite(hasta), "Date"),
	)
	return columnas(), [dict(f) for f in filas], mensaje


def columnas() -> list[dict]:
	return [
		{"fieldname": "tipo", "label": _("Operación"), "fieldtype": "Data", "width": 90},
		{
			"fieldname": "contraparte",
			"label": _("Contraparte"),
			"fieldtype": "Dynamic Link",
			"options": "parte",
			"width": 200,
		},
		{"fieldname": "nombre", "label": _("Nombre"), "fieldtype": "Data", "width": 220},
		{"fieldname": "identificacion", "label": _("RNC / ID"), "fieldtype": "Data", "width": 120},
		{"fieldname": "pais", "label": _("País"), "fieldtype": "Data", "width": 120},
		{"fieldname": "vinculacion", "label": _("Vinculación"), "fieldtype": "Data", "width": 180},
		{"fieldname": "documentos", "label": _("Documentos"), "fieldtype": "Int", "width": 100},
		{"fieldname": "monto", "label": _("Monto sin ITBIS"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "cargos", "label": _("Cargos (asientos)"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "abonos", "label": _("Abonos (asientos)"), "fieldtype": "Currency", "width": 140},
		{"fieldname": "parte", "label": _("Tipo de parte"), "fieldtype": "Data", "hidden": 1},
	]
