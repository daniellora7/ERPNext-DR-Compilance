// Regalía pascual de diciembre: la duodécima parte de los salarios del año de cada empleado activo y el
// Gratuity (regla Regalía RD) que la paga. "Crear regalías" crea en borrador los que faltan.
const anio_regalia = () => {
	const hoy = frappe.datetime.str_to_obj(frappe.datetime.get_today());
	// En enero todavía se revisa la del año anterior
	return hoy.getMonth() === 0 ? hoy.getFullYear() - 1 : hoy.getFullYear();
};

const crear_regalias = (report) => {
	const f = report.get_values();
	if (!f) return;
	const d = new frappe.ui.Dialog({
		title: __("Crear regalías {0}", [f.anio]),
		fields: [
			{
				fieldname: "pay_via_salary_slip",
				label: __("Pagar en el recibo de nómina"),
				fieldtype: "Check",
				default: 1,
			},
			{
				fieldname: "payroll_date",
				label: __("Fecha de pago"),
				fieldtype: "Date",
				reqd: 1,
				default: `${f.anio}-12-15`,
				description: __("Debe caer en el período de la nómina de diciembre en que se pagará (límite: 20 de diciembre)."),
			},
			{
				fieldname: "salary_component",
				label: __("Componente de nómina"),
				fieldtype: "Link",
				options: "Salary Component",
				default: "Regalía Pascual",
				depends_on: "pay_via_salary_slip",
				mandatory_depends_on: "pay_via_salary_slip",
				get_query: () => ({ filters: { type: "Earning", disabled: 0 } }),
			},
			{
				fieldname: "expense_account",
				label: __("Cuenta de gasto"),
				fieldtype: "Link",
				options: "Account",
				depends_on: "eval:!doc.pay_via_salary_slip",
				description: __("Vacía: la cuenta 6105 Regalía Pascual del catálogo DGII."),
				get_query: () => ({ filters: { company: f.company, is_group: 0, root_type: "Expense" } }),
			},
			{
				fieldname: "payable_account",
				label: __("Cuenta por pagar"),
				fieldtype: "Link",
				options: "Account",
				depends_on: "eval:!doc.pay_via_salary_slip",
				mandatory_depends_on: "eval:!doc.pay_via_salary_slip",
				get_query: () => ({ filters: { company: f.company, is_group: 0, root_type: "Liability" } }),
			},
			{
				fieldname: "mode_of_payment",
				label: __("Modo de pago"),
				fieldtype: "Link",
				options: "Mode of Payment",
				depends_on: "eval:!doc.pay_via_salary_slip",
				mandatory_depends_on: "eval:!doc.pay_via_salary_slip",
			},
		],
		primary_action_label: __("Crear en borrador"),
		primary_action(valores) {
			d.hide();
			frappe.call({
				method: "erpnext_rd.nomina_rd.regalia.crear_regalias",
				args: { company: f.company, anio: f.anio, ...valores },
				freeze: true,
				freeze_message: __("Calculando las regalías..."),
				callback: ({ message }) => {
					report.refresh();
					const n = message.creadas.length;
					if (!n) {
						frappe.msgprint(__("Todos los empleados activos ya tienen su regalía del año."));
						return;
					}
					frappe.msgprint({
						title: __("Regalías creadas"),
						indicator: "green",
						message: __(
							"Se crearon {0} Gratuity en borrador. Revíselos y apruébelos desde la lista (selección en bloque → Aprobar).",
							[n]
						),
						primary_action: {
							label: __("Abrir la lista"),
							action: () =>
								frappe.set_route("List", "Gratuity", { name: ["in", message.creadas] }),
						},
					});
				},
			});
		},
	});
	d.show();
};

frappe.query_reports["Regalia Pascual"] = {
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
			default: anio_regalia(),
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "_avisos" && data._avisos) {
			value = `<span style="color: var(--ink-amber-8)">${value}</span>`;
		}
		return value;
	},

	onload(report) {
		report.page.add_inner_button(__("Crear regalías"), () => crear_regalias(report));
	},
};
