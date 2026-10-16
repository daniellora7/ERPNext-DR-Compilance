// Anexos A-1 y B-1 del IR-2: saldos por casilla según la «Casilla del IR-2» de cada cuenta.
frappe.query_reports["Estados Financieros IR-2 DGII"] = (() => {
	const anio = frappe.datetime.str_to_obj(frappe.datetime.get_today()).getFullYear() - 1;
	return {
		filters: [
			{
				fieldname: "company",
				label: __("Empresa"),
				fieldtype: "Link",
				options: "Company",
				reqd: 1,
				default: frappe.defaults.get_user_default("Company"),
			},
			{ fieldname: "desde", label: __("Desde"), fieldtype: "Date", reqd: 1, default: `${anio}-01-01` },
			{ fieldname: "hasta", label: __("Hasta (cierre)"), fieldtype: "Date", reqd: 1, default: `${anio}-12-31` },
		],
		formatter(value, row, column, data, default_formatter) {
			value = default_formatter(value, row, column, data);
			if (data && data.negrita) value = `<b>${value}</b>`;
			return value;
		},
		onload(report) {
			report.page.add_inner_button(__("Plan de cuentas"), () => frappe.set_route("Tree", "Account"));
		},
	};
})();
