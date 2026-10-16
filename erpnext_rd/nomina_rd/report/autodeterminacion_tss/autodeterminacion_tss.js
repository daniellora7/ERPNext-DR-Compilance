// Archivo de autodeterminación mensual (AM) de la TSS. El botón descarga el TXT para el SUIR Plus
// (Gestión de archivos). Se envía desde el día siguiente al tercer día hábil del mes hasta el tercer
// día hábil del mes siguiente: los primeros días del mes se propone el mes anterior.
const periodo_tss = () => {
	const hoy = frappe.datetime.str_to_obj(frappe.datetime.get_today());
	const fecha = hoy.getDate() <= 5 ? frappe.datetime.str_to_obj(frappe.datetime.add_months(frappe.datetime.get_today(), -1)) : hoy;
	return { anio: fecha.getFullYear(), mes: String(fecha.getMonth() + 1) };
};

frappe.query_reports["Autodeterminacion TSS"] = {
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
			default: periodo_tss().anio,
		},
		{
			fieldname: "mes",
			label: __("Mes"),
			fieldtype: "Select",
			reqd: 1,
			options: ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
			default: periodo_tss().mes,
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
		report.page.add_inner_button(__("Descargar archivo TSS"), () => {
			const f = report.get_values();
			if (!f) return;
			const params = new URLSearchParams({ company: f.company, anio: f.anio, mes: f.mes });
			window.open(`/api/method/erpnext_rd.nomina_rd.tss.descargar_txt?${params}`);
		});
		// Rectificativa del IR-3: después de pagar la TSS, solo recalcula el ISR del período
		report.page.add_inner_button(
			__("Rectificativa IR-3 (RT)"),
			() => {
				const f = report.get_values();
				if (!f) return;
				frappe.confirm(
					__(
						"La rectificativa se envía después de pagar la notificación de la TSS y solo recalcula la liquidación del ISR (IR-3) del período. Cada envío sustituye al anterior: lleva a todos los trabajadores. ¿Descargarla?"
					),
					() => {
						const params = new URLSearchParams({ company: f.company, anio: f.anio, mes: f.mes, proceso: "RT" });
						window.open(`/api/method/erpnext_rd.nomina_rd.tss.descargar_txt?${params}`);
					}
				);
			},
			__("Otros archivos")
		);
		report.page.add_inner_button(
			__("Novedades del período (NV)"),
			() => {
				const f = report.get_values() || {};
				frappe.set_route("query-report", "Novedades TSS", { company: f.company, anio: f.anio, mes: f.mes });
			},
			__("Otros archivos")
		);
	},
};
