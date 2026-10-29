// Captura de compra (e-CF impreso o en PDF): verificar en la DGII, crear la factura de compra o descartar
frappe.ui.form.on("Captura Compra", {
	refresh(frm) {
		const api = "erpnext_rd.captura_compras.api.";
		const llamar = (metodo, args = {}, mensaje) =>
			frappe.call({
				method: api + metodo,
				args: { name: frm.doc.name, ...args },
				freeze: true,
				freeze_message: mensaje,
			});

		if (frm.doc.avisos) {
			frm.dashboard.set_headline_alert(
				frappe.utils.escape_html(frm.doc.avisos).replace(/\n/g, "<br>"),
				"orange"
			);
		}
		if (frm.is_new()) return;

		if (frm.doc.url_timbre) {
			frm.add_custom_button(__("Ver en la DGII"), () => window.open(frm.doc.url_timbre, "_blank"));
		}
		const abierta = !["Factura creada", "Duplicada", "Descartada"].includes(frm.doc.estado);
		if (abierta && frm.doc.encf && frm.doc.codigo_seguridad) {
			frm.add_custom_button(__("Verificar en la DGII"), () =>
				llamar("verificar", {}, __("Consultando la DGII...")).then(() => frm.reload_doc())
			);
		}
		if (abierta && frm.doc.estado === "Lista") {
			frm.add_custom_button(
				__("Crear factura de compra"),
				() =>
					llamar("crear_factura", {}, __("Creando la factura de compra en borrador...")).then(
						({ message }) => message && frappe.set_route("Form", "Purchase Invoice", message)
					),
				__("Factura de compra")
			);
		}
		if (abierta) {
			frm.add_custom_button(
				__("Descartar"),
				() =>
					frappe.prompt(
						{ fieldname: "motivo", fieldtype: "Small Text", label: __("Motivo") },
						({ motivo }) => llamar("descartar", { motivo }).then(() => frm.reload_doc()),
						__("Descartar captura"),
						__("Descartar")
					),
				__("Factura de compra")
			);
		}
	},
});
