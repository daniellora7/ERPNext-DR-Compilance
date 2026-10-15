// Archivo de novedades del período (NV) de la TSS: ingresos, salidas, cambios de salario, vacaciones y
// licencias del mes. Los envíos se suman (no se sustituyen): filtrar para no repetir una novedad.
// Se envían hasta el tercer día hábil del mes siguiente: los primeros días se propone el mes anterior.
const periodo_nv = () => {
	const hoy = frappe.datetime.str_to_obj(frappe.datetime.get_today());
	const fecha = hoy.getDate() <= 5 ? frappe.datetime.str_to_obj(frappe.datetime.add_months(frappe.datetime.get_today(), -1)) : hoy;
	return { anio: fecha.getFullYear(), mes: String(fecha.getMonth() + 1) };
};

frappe.query_reports["Novedades TSS"] = {
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
			default: periodo_nv().anio,
		},
		{
			fieldname: "mes",
			label: __("Mes"),
			fieldtype: "Select",
			reqd: 1,
			options: ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
			default: periodo_nv().mes,
		},
		{
			fieldname: "tipo_novedad",
			label: __("Novedad"),
			fieldtype: "Select",
			options: [
				{ value: "", label: __("Todas") },
				{ value: "IN", label: __("Ingreso") },
				{ value: "SA", label: __("Salida") },
				{ value: "AD", label: __("Actualización de datos (salario)") },
				{ value: "VC", label: __("Vacaciones") },
				{ value: "LV", label: __("Licencia voluntaria") },
				{ value: "LM", label: __("Licencia por maternidad") },
				{ value: "LD", label: __("Licencia por discapacidad") },
			],
		},
		{
			fieldname: "employee",
			label: __("Empleado"),
			fieldtype: "Link",
			options: "Employee",
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
		report.page.add_inner_button(__("Descargar archivo de novedades"), () => {
			const f = report.get_values();
			if (!f) return;
			const params = new URLSearchParams({
				company: f.company,
				anio: f.anio,
				mes: f.mes,
				employee: f.employee || "",
				tipo_novedad: f.tipo_novedad || "",
			});
			window.open(`/api/method/erpnext_rd.nomina_rd.novedades.descargar_txt?${params}`);
		});
		report.page.add_inner_button(__("Archivo de autodeterminación TSS"), () => {
			const f = report.get_values() || {};
			frappe.set_route("query-report", "Autodeterminacion TSS", { company: f.company, anio: f.anio, mes: f.mes });
		});
	},
};
