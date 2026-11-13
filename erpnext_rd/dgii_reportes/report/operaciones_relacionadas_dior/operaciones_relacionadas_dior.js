// Operaciones con partes relacionadas del ejercicio: apoyo para la DIOR (Fase 8.3).
frappe.query_reports["Operaciones Relacionadas DIOR"] = {
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
			fieldname: "desde",
			label: __("Desde"),
			fieldtype: "Date",
			description: __("Vacío: el último ejercicio cerrado"),
		},
		{ fieldname: "hasta", label: __("Hasta"), fieldtype: "Date" },
	],
	onload(report) {
		// Hoja de Detalle de la DIOR (versión 6): se copia y se pega en la Oficina Virtual
		report.page.add_inner_button(__("Hoja de Detalle (Excel)"), () => {
			const f = report.get_values();
			if (!f) return;
			const params = new URLSearchParams({ company: f.company, desde: f.desde || "", hasta: f.hasta || "" });
			window.open(`/api/method/erpnext_rd.dgii_reportes.dior.descargar_hoja_detalle?${params}`);
		});
	},
};
