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
};
