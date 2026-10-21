// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Subsidio SISALRIL", {
	setup(frm) {
		frm.set_query("licencia", () => ({
			filters: { employee: frm.doc.employee, docstatus: ["!=", 2] },
		}));
	},
	onload(frm) {
		// La licencia es una Leave Application de Frappe HR (opcional): sin él no se muestra
		frm.toggle_display("licencia", !!(frappe.boot.versions && frappe.boot.versions.hrms));
	},
	licencia(frm) {
		if (!frm.doc.licencia) return;
		frappe.db
			.get_value("Leave Application", frm.doc.licencia, ["from_date", "to_date"])
			.then(({ message }) => {
				if (!message) return;
				frm.set_value({ desde: message.from_date, hasta: message.to_date });
			});
	},
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Tomar salario de la nómina"), () =>
			frappe
				.call({
					method: "erpnext_rd.nomina_rd.subsidios.salario_desde_nomina",
					args: { name: frm.doc.name },
					freeze: true,
				})
				.then(() => frm.reload_doc())
		);
	},
});
