// Bonificación (art. 223): reparto de la participación en los beneficios y su pago en la nómina.
frappe.ui.form.on("Bonificacion RD", {
	setup(frm) {
		frm.set_query("componente", () => ({ filters: { type: "Earning", disabled: 0 } }));
	},

	onload(frm) {
		if (frm.is_new() && !frm.doc.porcentaje) {
			frappe.db
				.get_single_value("Configuracion Nomina RD", "bonificacion_porcentaje")
				.then((valor) => frm.set_value("porcentaje", valor || 10));
		}
	},

	refresh(frm) {
		if (frm.doc.docstatus !== 0) return;
		frm.add_custom_button(__("Calcular reparto"), () => {
			frm.call("calcular").then(() => frm.dirty());
		});
		frm.add_custom_button(
			__("Traer utilidad de la contabilidad"),
			() => {
				if (!frm.doc.company || !frm.doc.desde) {
					frappe.msgprint(__("Indique la empresa y el ejercicio fiscal."));
					return;
				}
				frappe
					.call("erpnext_rd.nomina_rd.bonificacion.utilidad_contable", {
						company: frm.doc.company,
						desde: frm.doc.desde,
						hasta: frm.doc.hasta,
					})
					.then(({ message }) => {
						frm.set_value("utilidad_neta", message);
						frappe.msgprint({
							title: __("Utilidad según la contabilidad"),
							indicator: "orange",
							message: __(
								"Son los ingresos menos los gastos del ejercicio. Ajústela si incluye el ISR o bonificaciones de directores y gerentes, que no se descuentan para este cálculo."
							),
						});
					});
			},
			__("Utilidad")
		);
	},

	ejercicio(frm) {
		if (frm.doc.empleados?.length) frm.clear_table("empleados");
	},

	utilidad_neta: (frm) => frm.trigger("recalcular"),
	porcentaje: (frm) => frm.trigger("recalcular"),

	recalcular(frm) {
		// El reparto definitivo lo hace el servidor al guardar; aquí solo se muestra el monto a repartir
		frm.set_value("fondo", flt(Math.max(frm.doc.utilidad_neta || 0, 0) * (frm.doc.porcentaje || 0) / 100, 2));
	},
});
