// Formato de envío 608 DGII. Período mensual; el botón descarga el TXT para la Oficina Virtual.
frappe.query_reports["Formato 608 DGII"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Empresa"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "anio",
			label: __("Año"),
			fieldtype: "Int",
			reqd: 1,
			default: frappe.datetime.str_to_obj(frappe.datetime.add_months(frappe.datetime.get_today(), -1)).getFullYear(),
		},
		{
			fieldname: "mes",
			label: __("Mes"),
			fieldtype: "Select",
			reqd: 1,
			options: ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
			default: String(frappe.datetime.str_to_obj(frappe.datetime.add_months(frappe.datetime.get_today(), -1)).getMonth() + 1),
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "_avisos" && data && data._avisos) {
			value = `<span style="color: var(--ink-amber-8)">${value}</span>`;
		}
		return value;
	},

	onload(report) {
		report.page.add_inner_button(__("Descargar TXT DGII"), () => {
			const f = report.get_values();
			if (!f) return;
			const params = new URLSearchParams({ formato: "608", company: f.company, anio: f.anio, mes: f.mes });
			window.open(`/api/method/erpnext_rd.dgii_reportes.formatos.descargar_txt?${params}`);
		});
	},
};
