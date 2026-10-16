// Envío e-CF: reenviar a la DGII (firmado sin enviar, con error o en contingencia) y entregar al comprador
frappe.ui.form.on("Envio ECF", {
	refresh(frm) {
		if (["Firmado", "Error", "Contingencia"].includes(frm.doc.estado)) {
			frm.add_custom_button(__("Enviar a la DGII"), () =>
				frappe
					.call({
						method: "erpnext_rd.ecf.emision.reenviar",
						args: { envio: frm.doc.name },
						freeze: true,
						freeze_message: __("Enviando a la DGII..."),
					})
					.then(() => frm.reload_doc())
			);
		}
		const con_comprador = ["E31", "E33", "E34", "E44", "E45"].includes(frm.doc.tipo_ecf);
		if (
			con_comprador &&
			!frm.doc.es_rfce &&
			["Aceptado", "Aceptado condicional"].includes(frm.doc.estado) &&
			frm.doc.estado_comprador !== "Recibido"
		) {
			frm.add_custom_button(__("Entregar al comprador"), () =>
				frappe
					.call({
						method: "erpnext_rd.ecf.emision.entregar",
						args: { envio: frm.doc.name },
						freeze: true,
					})
					.then(() => frm.reload_doc())
			);
		}
	},
});
