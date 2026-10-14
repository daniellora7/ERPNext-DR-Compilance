// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt
// Customer / Supplier: autocompleta el nombre desde el padrón DGII al escribir el RNC o la Cédula.

const erpnext_rd_party = {
	tax_id(frm) {
		const numero = (frm.doc.tax_id || "").replace(/\D/g, "");
		if (![9, 11].includes(numero.length)) return;

		frappe.call({
			method: "erpnext_rd.padron_rnc.padron.consultar_rnc",
			args: { numero },
			callback({ message: c }) {
				if (!c) {
					frappe.show_alert({ message: __("No encontrado en el padrón DGII"), indicator: "orange" });
					return;
				}
				const campo = frm.doctype === "Customer" ? "customer_name" : "supplier_name";
				if (frm.is_new() && !frm.doc[campo]) frm.set_value(campo, c.razon_social);
				frm.set_value("rd_tipo_identificacion", numero.length === 9 ? "RNC" : "Cédula");
				frappe.show_alert({
					message: __("{0} — {1} ({2})", [c.razon_social, c.estado, c.regimen_pago]),
					indicator: c.estado === "ACTIVO" ? "green" : "red",
				});
			},
		});
	},
	setup(frm) {
		const filtro = frm.doctype === "Customer" ? "aplica_ventas" : "aplica_compras";
		frm.set_query("rd_tipo_comprobante", () => ({ filters: { habilitado: 1, [filtro]: 1 } }));
	},
};

frappe.ui.form.on("Customer", erpnext_rd_party);
frappe.ui.form.on("Supplier", erpnext_rd_party);
