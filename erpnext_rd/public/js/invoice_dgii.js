// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt
// Sales / POS / Purchase Invoice: filtra los tipos de comprobante válidos.

const erpnext_rd_invoice = {
	setup(frm) {
		const filtro = frm.doctype === "Purchase Invoice" ? "aplica_compras" : "aplica_ventas";
		frm.set_query("rd_tipo_comprobante", () => ({ filters: { habilitado: 1, [filtro]: 1 } }));
	},
};

frappe.ui.form.on("Sales Invoice", erpnext_rd_invoice);
frappe.ui.form.on("POS Invoice", erpnext_rd_invoice);
frappe.ui.form.on("Purchase Invoice", erpnext_rd_invoice);
