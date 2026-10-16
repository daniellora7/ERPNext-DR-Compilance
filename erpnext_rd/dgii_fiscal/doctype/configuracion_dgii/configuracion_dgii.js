// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Configuracion DGII", {
	refresh(frm) {
		frm.add_custom_button(__("Actualizar padrón RNC"), () => {
			frappe.call("erpnext_rd.padron_rnc.padron.encolar_sincronizacion").then(({ message }) =>
				frappe.msgprint(message)
			);
		});
		boton_tasa_dolar(frm);
		frm.add_custom_button(__("Vista previa de recordatorios"), () => {
			frappe.call("erpnext_rd.rd_compliance.recordatorios.vista_previa").then(({ message }) =>
				frappe.msgprint({ title: __("Recordatorios de hoy"), message, wide: true })
			);
		});
	},
});

function boton_tasa_dolar(frm) {
	frm.add_custom_button(__("Actualizar tasa del dólar"), () => {
		frappe
			.call({
				method: "erpnext_rd.dgii_fiscal.tasa_bcrd.actualizar_ahora",
				freeze: true,
				freeze_message: __("Consultando el Banco Central..."),
			})
			.then(({ message }) => {
				frappe.msgprint(message);
				frm.reload_doc();
			});
	});
}
