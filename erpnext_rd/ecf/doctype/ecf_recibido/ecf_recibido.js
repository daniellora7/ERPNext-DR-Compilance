// e-CF recibido: aprobación o rechazo comercial (ACECF) y reenvío si falló
frappe.ui.form.on("ECF Recibido", {
	refresh(frm) {
		const decidir = (aprobado, motivo) =>
			frappe
				.call({
					method: "erpnext_rd.ecf.recepcion.aprobar",
					args: { name: frm.doc.name, aprobado, motivo },
					freeze: true,
					freeze_message: __("Firmando y enviando la aprobación comercial..."),
				})
				.then(() => frm.reload_doc());

		if (frm.doc.estado === "Recibido" && frm.doc.aprobacion === "Pendiente") {
			frm.add_custom_button(__("Aprobar"), () =>
				frappe.confirm(__("¿Aprobar comercialmente el e-CF {0}?", [frm.doc.encf]), () => decidir(1))
			);
			frm.add_custom_button(__("Rechazar"), () =>
				frappe.prompt(
					{
						fieldname: "motivo",
						fieldtype: "Small Text",
						label: __("Motivo del rechazo"),
						reqd: 1,
						description: __("Hasta 250 caracteres; lo recibe el emisor."),
					},
					({ motivo }) => decidir(0, motivo),
					__("Rechazar e-CF {0}", [frm.doc.encf]),
					__("Rechazar")
				)
			);
		}
		if (frm.doc.envio_aprobacion === "Error") {
			frm.add_custom_button(__("Reenviar la aprobación"), () =>
				frappe
					.call({
						method: "erpnext_rd.ecf.recepcion.reenviar_aprobacion",
						args: { name: frm.doc.name },
						freeze: true,
					})
					.then(() => frm.reload_doc())
			);
		}
	},
});
