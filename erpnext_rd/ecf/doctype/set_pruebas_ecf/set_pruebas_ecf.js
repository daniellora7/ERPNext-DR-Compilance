// Set de pruebas CerteCF: firmar los e-CF del archivo de la DGII, enviarlos y ver sus envíos
frappe.ui.form.on("Set Pruebas ECF", {
	refresh(frm) {
		if (frm.is_new()) return;
		frm.add_custom_button(__("Firmar los e-CF"), () =>
			frappe
				.call({
					method: "erpnext_rd.ecf.certificacion.generar",
					args: { name: frm.doc.name },
					freeze: true,
					freeze_message: __("Firmando los e-CF del set..."),
				})
				.then(() => frm.reload_doc())
		);
		if (frm.doc.generados) {
			frm.add_custom_button(__("Enviar a la DGII"), () =>
				frappe
					.call({
						method: "erpnext_rd.ecf.certificacion.enviar",
						args: { name: frm.doc.name },
						freeze: true,
						freeze_message: __("Enviando los e-CF del set..."),
					})
					.then(() => frm.reload_doc())
			);
			frm.add_custom_button(__("Ver envíos"), () =>
				frappe.set_route("List", "Envio ECF", { tipo_documento: frm.doctype, documento: frm.doc.name })
			);
		}
	},
});
