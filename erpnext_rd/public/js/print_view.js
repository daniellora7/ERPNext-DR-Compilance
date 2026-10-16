// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt
// Vista de impresión: las facturas abren con el formato de su empresa (frappe.boot.rd_formatos, ver
// boot.py). Si el usuario eligió otro formato a mano, se respeta.

(() => {
	const vista = frappe.ui.form.PrintView.prototype;
	const original = vista.set_default_print_format;

	vista.set_default_print_format = function () {
		const formatos = frappe.boot.rd_formatos?.[this.frm.doctype];
		const formato = formatos?.empresas[this.frm.doc?.company];
		if (!formato) return original.call(this);

		const actual = this.print_format_selector.val();
		const automaticos = new Set([formatos.defecto, "Standard", ...Object.values(formatos.empresas)]);
		if (actual && !automaticos.has(actual)) return original.call(this);
		this.set_print_format_value(formato);
	};
})();
