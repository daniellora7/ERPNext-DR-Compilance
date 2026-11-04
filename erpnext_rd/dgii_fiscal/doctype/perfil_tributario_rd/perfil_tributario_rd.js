// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Perfil Tributario RD", {
	setup(frm) {
		frm.set_query("company", () => ({ filters: { country: "Dominican Republic" } }));
	},

	refresh(frm) {
		frm.get_field("requisitos_html").$wrapper.empty();
		if (frm.is_new()) return;
		frm.add_custom_button(__("Crear año fiscal"), () =>
			frappe
				.call({ method: "erpnext_rd.rd_compliance.perfil.crear_anio_fiscal", args: { company: frm.doc.company } })
				.then(({ message }) => {
					frappe.show_alert({ message: __("Año fiscal {0}", [message]), indicator: "green" });
					frm.trigger("mostrar_requisitos");
				})
		);
		frm.trigger("mostrar_requisitos");
	},

	mostrar_requisitos(frm) {
		frappe
			.call({ method: "erpnext_rd.rd_compliance.perfil.requisitos", args: { company: frm.doc.company } })
			.then(({ message }) =>
				frappe.require("/assets/erpnext_rd/js/requisitos.js", () =>
					erpnext_rd_tabla_requisitos(frm.get_field("requisitos_html").$wrapper, message || [])
				)
			);
	},
});
