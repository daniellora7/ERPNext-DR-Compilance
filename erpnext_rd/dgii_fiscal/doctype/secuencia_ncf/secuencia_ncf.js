// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Secuencia NCF", {
	setup(frm) {
		frm.set_query("tipo_comprobante", () => ({ filters: { habilitado: 1 } }));
	},
	desde(frm) {
		if (frm.is_new()) frm.set_value("siguiente", frm.doc.desde);
	},
});
