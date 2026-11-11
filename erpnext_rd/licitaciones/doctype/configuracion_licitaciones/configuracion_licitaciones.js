// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Configuracion Licitaciones", {
	refresh(frm) {
		frm.add_custom_button(__("Descargar ahora"), () =>
			frappe
				.call({ method: "erpnext_rd.licitaciones.procesos.sincronizar_ahora" })
				.then(({ message }) => frappe.show_alert({ message, indicator: "blue" }))
		);
		frm.add_custom_button(__("Procesos de compra"), () => frappe.set_route("List", "Proceso Compra DGCP"));
	},
});
