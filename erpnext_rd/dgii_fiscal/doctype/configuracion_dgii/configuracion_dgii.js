// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Configuracion DGII", {
	refresh(frm) {
		frm.add_custom_button(__("Actualizar padrón RNC"), () => {
			frappe.call("erpnext_rd.padron_rnc.padron.encolar_sincronizacion").then(({ message }) =>
				frappe.msgprint(message)
			);
		});
	},
});
