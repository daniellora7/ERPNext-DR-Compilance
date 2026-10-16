// Anulación de e-NCF: solo secuencias electrónicas de la empresa; reenvío a la DGII si falló
frappe.ui.form.on("Anulacion ENCF", {
	setup(frm) {
		frm.set_query("secuencia", "rangos", () => ({
			filters: { company: frm.doc.company, tipo_comprobante: ["like", "E%"] },
		}));
	},
	refresh(frm) {
		if (frm.doc.docstatus === 1 && ["Firmado", "Enviado", "Error"].includes(frm.doc.estado)) {
			frm.add_custom_button(__("Enviar a la DGII"), () =>
				frm.call({ method: "enviar_dgii", doc: frm.doc, freeze: true }).then(() => frm.reload_doc())
			);
		}
	},
});

frappe.ui.form.on("Anulacion ENCF Rango", {
	// Propone anular desde el siguiente número sin usar hasta el final de la secuencia
	secuencia(frm, cdt, cdn) {
		const fila = locals[cdt][cdn];
		if (!fila.secuencia) return;
		frappe.db.get_value("Secuencia NCF", fila.secuencia, ["siguiente", "hasta"]).then(({ message }) => {
			if (!message) return;
			frappe.model.set_value(cdt, cdn, { desde: message.siguiente, hasta: message.hasta });
		});
	},
});
