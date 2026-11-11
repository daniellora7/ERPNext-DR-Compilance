// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt

// Oportunidad de un proceso de compra del Estado (Fase 10.5, licitaciones/ofertas.py)
frappe.ui.form.on("Opportunity", {
	refresh(frm) {
		const proceso = frm.doc.rd_proceso_dgcp;
		if (!proceso || frm.is_new()) return;
		frm.add_custom_button(__("Proceso de compra"), () => frappe.set_route("Form", "Proceso Compra DGCP", proceso), __("Licitación"));
		frappe.db.get_value("Proceso Compra DGCP", proceso, "url").then(({ message }) => {
			if (message && message.url) {
				frm.add_custom_button(
					__("Portal Transaccional"),
					() => window.open(message.url, "_blank", "noopener"),
					__("Licitación")
				);
			}
		});
		erpnext_rd_aviso_oferta(frm);
	},
});

function erpnext_rd_aviso_oferta(frm) {
	const doc = frm.doc;
	if (!["Evaluando", "En preparación"].includes(doc.rd_estado_oferta)) return;
	const pendientes = (doc.rd_documentos_oferta || []).filter((d) => d.obligatorio && d.estado === "Pendiente");
	const cierre = doc.rd_cierre_ofertas;
	const partes = [];
	if (cierre) {
		const vencido = frappe.datetime.str_to_obj(cierre) < new Date();
		partes.push(
			vencido
				? __("El proceso dejó de recibir ofertas el {0}.", [frappe.datetime.str_to_user(cierre)])
				: __("Recibe ofertas hasta el {0}.", [frappe.datetime.str_to_user(cierre)])
		);
	}
	if (pendientes.length) {
		partes.push(__("Faltan {0} documentos obligatorios.", [pendientes.length]));
	}
	if (partes.length) frm.set_intro(partes.join(" "), pendientes.length ? "orange" : "blue");
}
