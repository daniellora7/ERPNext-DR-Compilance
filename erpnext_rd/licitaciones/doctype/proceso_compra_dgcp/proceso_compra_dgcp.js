// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Proceso Compra DGCP", {
	refresh(frm) {
		if (frm.doc.url) {
			frm.add_custom_button(__("Abrir en el Portal Transaccional"), () => window.open(frm.doc.url, "_blank", "noopener"));
		}
		frm.add_custom_button(__("Documentos"), () =>
			frappe
				.call({
					method: "erpnext_rd.licitaciones.procesos.documentos",
					args: { codigo_proceso: frm.doc.name },
					freeze: true,
					freeze_message: __("Consultando la DGCP..."),
				})
				.then(({ message }) => erpnext_rd_documentos_proceso(message || []))
		);
		const cierre = frm.doc.fecha_fin_recepcion_ofertas;
		if (cierre && frm.doc.estado_proceso === "Proceso publicado" && frappe.datetime.str_to_obj(cierre) > new Date()) {
			frm.set_intro(__("Recibe ofertas hasta el {0}.", [frappe.datetime.str_to_user(cierre)]), "blue");
		}
	},
});

function erpnext_rd_documentos_proceso(documentos) {
	const e = frappe.utils.escape_html;
	const celda = "padding: 6px 8px; border-bottom: 1px solid var(--outline-gray-1); vertical-align: top";
	const filas = documentos
		.map(
			(d) => `<tr>
				<td style="${celda}"><a href="${e(d.url || "#")}" target="_blank" rel="noopener" style="color: var(--ink-gray-8); text-decoration: underline">${e(d.nombre || "")}</a></td>
				<td style="${celda}; color: var(--ink-gray-5)">${e(d.tipo || "")}</td>
				<td style="${celda}; color: var(--ink-gray-5); white-space: nowrap">${d.fecha ? frappe.datetime.str_to_user(d.fecha) : ""}</td>
			</tr>`
		)
		.join("");
	const dialogo = new frappe.ui.Dialog({ title: __("Documentos del proceso"), size: "large" });
	dialogo.$body.html(
		documentos.length
			? `<table style="width: 100%; border-collapse: collapse"><tbody>${filas}</tbody></table>`
			: `<p style="color: var(--ink-gray-5)">${__("El proceso no tiene documentos publicados.")}</p>`
	);
	dialogo.show();
}
