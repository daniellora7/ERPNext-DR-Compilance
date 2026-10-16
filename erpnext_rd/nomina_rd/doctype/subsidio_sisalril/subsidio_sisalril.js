// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Subsidio SISALRIL", {
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
