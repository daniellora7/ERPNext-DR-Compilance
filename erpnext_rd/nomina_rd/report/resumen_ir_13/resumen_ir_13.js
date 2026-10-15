// Resumen IR-13: suma de los IR-3 del año, para compararlo con el Excel de la DGII antes de aceptarlo.
// Vence el 15 de marzo: hasta marzo se propone el año anterior.
const anio_ir13 = () => {
	const hoy = frappe.datetime.str_to_obj(frappe.datetime.get_today());
	return hoy.getMonth() <= 2 ? hoy.getFullYear() - 1 : hoy.getFullYear();
};

frappe.query_reports["Resumen IR-13"] = {
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
			default: anio_ir13(),
		},
		{
			fieldname: "vista",
			label: __("Ver"),
			fieldtype: "Select",
			options: ["Por empleado", "Por mes"],
			default: "Por empleado",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "_avisos" && data._avisos) {
			value = `<span style="color: var(--ink-amber-8)">${value}</span>`;
		}
		if (column.fieldname === "diferencia" && Math.abs(data.diferencia || 0) > 1) {
			value = `<span style="color: var(--ink-red-6)">${value}</span>`;
		}
		return value;
	},

	onload(report) {
		report.page.add_inner_button(__("Resumen IR-3 del mes"), () => {
			const f = report.get_values() || {};
			frappe.set_route("query-report", "Resumen IR-3", { company: f.company, anio: f.anio });
		});
	},
};
