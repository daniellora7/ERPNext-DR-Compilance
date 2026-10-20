// Anticipos del ISR (art. 314): cuota de cada mes según la Base Anticipo ISR vigente.
frappe.query_reports["Anticipos ISR DGII"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Empresa"),
			fieldtype: "Link",
			options: "Company",
			reqd: 1,
			default: frappe.defaults.get_user_default("Company"),
		},
		{ fieldname: "anio", label: __("Año"), fieldtype: "Int", reqd: 1, default: frappe.datetime.str_to_obj(frappe.datetime.get_today()).getFullYear() },
	],
	onload(report) {
		report.page.add_inner_button(__("Bases de anticipos"), () => frappe.set_route("List", "Base Anticipo ISR"));
	},
};
