// Resumen de apoyo para la declaración mensual del ISC: ventas del mes por categoría.
frappe.query_reports["Resumen ISC DGII"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Empresa"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "anio", label: __("Año"), fieldtype: "Int", reqd: 1, default: frappe.datetime.str_to_obj(frappe.datetime.add_months(frappe.datetime.get_today(), -1)).getFullYear() },
		{
			fieldname: "mes",
			label: __("Mes"),
			fieldtype: "Select",
			reqd: 1,
			options: ["1", "2", "3", "4", "5", "6", "7", "8", "9", "10", "11", "12"],
			default: String(frappe.datetime.str_to_obj(frappe.datetime.add_months(frappe.datetime.get_today(), -1)).getMonth() + 1),
		},
	],
};
