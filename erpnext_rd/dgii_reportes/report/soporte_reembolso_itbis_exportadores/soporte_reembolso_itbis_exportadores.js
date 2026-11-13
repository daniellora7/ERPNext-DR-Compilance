// Soporte para la solicitud de compensación o reembolso del ITBIS de los exportadores (Fase 8.4).
frappe.query_reports["Soporte Reembolso ITBIS Exportadores"] = {
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
			default: new Date().getFullYear(),
		},
		{
			fieldname: "saldo_favor_inicial",
			label: __("Saldo a favor de diciembre del año anterior"),
			fieldtype: "Currency",
			description: __("El del último IT-1 presentado del año anterior"),
		},
	],
};
