// Ofertas al Estado (Fase 10.5): oportunidades de procesos de compra con sus pendientes.
frappe.query_reports["Ofertas Estado"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Empresa"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "estado",
			label: __("Estado de la oferta"),
			fieldtype: "Select",
			options: ["", "Evaluando", "En preparación", "Presentada", "Ganada", "Perdida", "No presentada", "Desierto o cancelado"],
		},
		{ fieldname: "incluir_cerradas", label: __("Incluir las cerradas"), fieldtype: "Check" },
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		const pendiente = ["documentos_pendientes", "garantias_por_gestionar"].includes(column.fieldname);
		if (pendiente && data && data[column.fieldname] > 0) {
			value = `<span style="color: var(--ink-amber-8)">${value}</span>`;
		}
		return value;
	},
};
