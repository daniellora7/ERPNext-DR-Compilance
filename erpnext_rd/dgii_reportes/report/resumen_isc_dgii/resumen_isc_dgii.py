"""Resumen de apoyo para la declaración mensual del impuesto selectivo al consumo (ISC)."""

import frappe
from frappe import _
from frappe.utils import flt

from erpnext_rd.dgii_fiscal import isc
from erpnext_rd.dgii_reportes import declaraciones
from erpnext_rd.nomina_rd import feriados


def execute(filters=None):
	filters = frappe._dict(filters or {})
	columnas = [
		{"fieldname": "categoria", "label": _("Categoría"), "fieldtype": "Data", "width": 180},
		{
			"fieldname": "base_especifica",
			"label": _("Base del específico"),
			"fieldtype": "Float",
			"width": 150,
		},
		{"fieldname": "unidad", "label": _("Unidad"), "fieldtype": "Data", "width": 190},
		{
			"fieldname": "base_ad_valorem",
			"label": _("Base ad valorem"),
			"fieldtype": "Currency",
			"width": 160,
		},
		{"fieldname": "especifico", "label": _("ISC específico"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "ad_valorem", "label": _("ISC ad valorem"), "fieldtype": "Currency", "width": 150},
		{"fieldname": "total", "label": _("Total ISC"), "fieldtype": "Currency", "width": 150},
	]
	if not (filters.company and filters.anio and filters.mes):
		return columnas, []

	filas = isc.resumen_mensual(filters.company, filters.anio, filters.mes)
	for f in filas:
		f.categoria = _(f.categoria)
		f.unidad = _(f.unidad) if f.unidad else ""
	vence = feriados.dia_habil(declaraciones.vencimiento(filters.anio, filters.mes, isc.DIA_VENCE))
	resumen = [
		{
			"label": _("ISC a pagar"),
			"value": flt(sum(f.total for f in filas), 2),
			"datatype": "Currency",
			"indicator": "Red",
		},
		{"label": _("Vence"), "value": vence, "datatype": "Date", "indicator": "Blue"},
	]
	mensaje = _(
		"Resumen de apoyo para la declaración del ISC: ventas del mes de los artículos y servicios con ISC "
		"(las notas de crédito restan). Vence el {0} (si es feriado o fin de semana, el siguiente día "
		"hábil). Los combustibles se declaran cada semana. Verifique los montos con su contador antes de "
		"presentar."
	).format(frappe.format(vence, "Date"))
	return columnas, filas, mensaje, None, resumen
