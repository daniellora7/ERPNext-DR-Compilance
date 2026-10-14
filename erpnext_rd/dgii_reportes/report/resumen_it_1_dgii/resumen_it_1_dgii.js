// Resumen de apoyo para el IT-1: montos del período a digitar en la Oficina Virtual.
frappe.query_reports["Resumen IT-1 DGII"] = {
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
		{
			fieldname: "saldo_favor_anterior",
			label: __("Saldo a favor anterior"),
			fieldtype: "Currency",
			default: 0,
		},
		{
			fieldname: "retenciones_tarjetas",
			label: __("Retenciones de tarjetas (Norma 08-04)"),
			fieldtype: "Currency",
			default: 0,
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (data && data.es_titulo && column.fieldname === "concepto") {
			value = `<b>${value}</b>`;
		}
		return value;
	},
};
