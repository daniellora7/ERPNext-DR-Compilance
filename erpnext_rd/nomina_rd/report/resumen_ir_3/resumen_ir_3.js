// Resumen IR-3: lo que la DGII va a liquidar de retenciones de asalariados, para compararlo con el
// IR-4 antes de presentar. Vence el día 10 del mes siguiente: hasta ese día se propone el mes anterior.
const periodo_ir3 = () => {
	const hoy = frappe.datetime.str_to_obj(frappe.datetime.get_today());
	const fecha = hoy.getDate() <= 10 ? frappe.datetime.str_to_obj(frappe.datetime.add_months(frappe.datetime.get_today(), -1)) : hoy;
	return { anio: fecha.getFullYear(), mes: String(fecha.getMonth() + 1) };
};

frappe.query_reports["Resumen IR-3"] = {
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
			default: periodo_ir3().anio,
		},
		{
			fieldname: "mes",
			label: __("Mes"),
			fieldtype: "Select",
			reqd: 1,
			options: ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
			default: periodo_ir3().mes,
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
		report.page.add_inner_button(__("Archivo de autodeterminación TSS"), () => {
			const f = report.get_values();
			frappe.set_route("query-report", "Autodeterminacion TSS", f || {});
		});
	},
};
