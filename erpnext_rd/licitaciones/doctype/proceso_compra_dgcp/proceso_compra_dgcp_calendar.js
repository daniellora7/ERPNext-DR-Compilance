// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt
// Calendario de fechas límite: de la publicación al cierre de la recepción de ofertas.

frappe.views.calendar["Proceso Compra DGCP"] = {
	field_map: {
		start: "fecha_publicacion",
		end: "fecha_fin_recepcion_ofertas",
		id: "name",
		title: "titulo",
		allDay: "all_day",
	},
	filters: [{ fieldtype: "Data", fieldname: "estado_proceso", label: __("Estado en la DGCP") }],
	get_events_method: "frappe.desk.calendar.get_events",
};
