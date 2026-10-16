// Planillas del Ministerio de Trabajo (SIRLA): personal fijo (DGT-3, enero) y cambios del mes (DGT-4).
const periodo_sirla = () => {
	const hoy = frappe.datetime.str_to_obj(frappe.datetime.get_today());
	return { anio: hoy.getFullYear(), mes: String(hoy.getMonth() + 1) };
};

frappe.query_reports["Planillas SIRLA"] = {
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
			fieldname: "formulario",
			label: __("Formulario"),
			fieldtype: "Select",
			reqd: 1,
			options: [
				{ value: "T3", label: __("DGT-3: planilla del personal fijo") },
				{ value: "T4", label: __("DGT-4: cambios del mes") },
			],
			default: "T3",
		},
		{
			fieldname: "anio",
			label: __("Año"),
			fieldtype: "Int",
			reqd: 1,
			default: periodo_sirla().anio,
		},
		{
			fieldname: "mes",
			label: __("Mes"),
			fieldtype: "Select",
			reqd: 1,
			options: ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
			default: periodo_sirla().mes,
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
		report.page.add_inner_button(__("Descargar archivo SIRLA"), () => {
			const f = report.get_values();
			if (!f) return;
			const params = new URLSearchParams({ company: f.company, anio: f.anio, mes: f.mes, formulario: f.formulario });
			window.open(`/api/method/erpnext_rd.nomina_rd.sirla.descargar_txt?${params}`);
		});
	},
};
