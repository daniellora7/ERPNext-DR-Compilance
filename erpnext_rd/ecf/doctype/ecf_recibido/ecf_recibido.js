// e-CF recibido: aprobación o rechazo comercial (ACECF), reenvío si falló y factura de compra
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
		const compras = "erpnext_rd.captura_compras.convertir.";
		const sin_factura = frm.doc.estado === "Recibido" && !frm.doc.factura_compra;
		if (sin_factura && frm.doc.estado_conversion !== "Ignorado") {
			const etiqueta = frm.doc.estado_conversion === "Error" ? __("Reintentar") : __("Crear factura de compra");
			frm.add_custom_button(etiqueta, () =>
				frappe
					.call({
						method: compras + "crear_factura",
						args: { name: frm.doc.name },
						freeze: true,
						freeze_message: __("Creando la factura de compra en borrador..."),
					})
					.then(({ message }) => message && frappe.set_route("Form", "Purchase Invoice", message)),
				__("Factura de compra")
			);
			frm.add_custom_button(
				__("Ignorar"),
				() =>
					frappe.confirm(__("¿No registrar este e-CF como compra?"), () =>
						frappe
							.call({ method: compras + "ignorar", args: { name: frm.doc.name } })
							.then(() => frm.reload_doc())
					),
				__("Factura de compra")
			);
		}
		if (frm.doc.estado_conversion === "Requiere revisión" || frm.doc.estado_conversion === "Error") {
			frm.dashboard.set_headline_alert(
				frappe.utils.escape_html(frm.doc.mensajes_conversion || "").replace(/
/g, "<br>"),
				"orange"
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
