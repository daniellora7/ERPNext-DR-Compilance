// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt
// Sales / POS / Purchase Invoice: filtra los tipos de comprobante válidos.

// Formato de impresión de la empresa (frappe.boot.rd_formatos, ver boot.py): lo usan el botón Imprimir
// y el diálogo de correo, que toman el predeterminado del DocType.
function erpnext_rd_formato_de_empresa(frm) {
	const formatos = frappe.boot.rd_formatos?.[frm.doctype];
	if (!formatos) return;
	frm.meta.default_print_format = formatos.empresas[frm.doc.company] || formatos.defecto;
}

const erpnext_rd_invoice = {
	company(frm) {
		erpnext_rd_formato_de_empresa(frm);
	},

	setup(frm) {
		const filtro = frm.doctype === "Purchase Invoice" ? "aplica_compras" : "aplica_ventas";
		frm.set_query("rd_tipo_comprobante", () => ({ filters: { habilitado: 1, [filtro]: 1 } }));
	},

	refresh(frm) {
		erpnext_rd_formato_de_empresa(frm);

		// e-CF: emitir (generar, firmar y enviar según el emisor) y ver sus envíos
		const electronico = (frm.doc.rd_tipo_comprobante || "").startsWith("E") && frm.doc.rd_ncf;
		if (frm.doctype === "POS Invoice" || frm.doc.docstatus !== 1 || !electronico) return;
		frm.add_custom_button(
			__("Emitir e-CF"),
			() =>
				frappe
					.call({
						method: "erpnext_rd.ecf.emision.emitir",
						args: { doctype: frm.doctype, name: frm.doc.name },
						freeze: true,
						freeze_message: __("Firmando el e-CF..."),
					})
					.then(({ message }) => {
						frm.reload_doc();
						frappe.set_route("Form", "Envio ECF", message);
					}),
			__("e-CF")
		);
		frm.add_custom_button(
			__("Envíos e-CF"),
			() => frappe.set_route("List", "Envio ECF", { tipo_documento: frm.doctype, documento: frm.doc.name }),
			__("e-CF")
		);
	},
};

frappe.ui.form.on("Sales Invoice", erpnext_rd_invoice);
frappe.ui.form.on("POS Invoice", erpnext_rd_invoice);
frappe.ui.form.on("Purchase Invoice", erpnext_rd_invoice);
