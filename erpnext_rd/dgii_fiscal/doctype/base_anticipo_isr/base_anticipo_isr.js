// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Base Anticipo ISR", {
	setup(frm) {
		frm.set_query("company", () => ({ filters: { country: "Dominican Republic" } }));
	},
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Anticipos del año"), () =>
			frappe.set_route("query-report", "Anticipos ISR DGII", {
				company: frm.doc.company,
				anio: frm.doc.ejercicio + 1,
			})
		);
	},
});
