// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt
// Vista de impresión: las facturas abren con el formato de su empresa (frappe.boot.rd_formatos, ver
// boot.py). Si el usuario eligió otro formato a mano, se respeta.
// Los formatos para papel preimpreso (cheques) abren sin membrete: el membrete correría las posiciones.

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

(() => {
	const SIN_MEMBRETE = new Set(["Cheque RD"]);
	const vista = frappe.ui.form.PrintView.prototype;
	const quitar_membrete = (view) => {
		if (SIN_MEMBRETE.has(view.print_format_selector.val())) view.letterhead_selector.val("");
	};

	const refrescar = vista.refresh_print_format;
	vista.refresh_print_format = function () {
		quitar_membrete(this);
		return refrescar.call(this);
	};

	const membrete_por_defecto = vista.set_default_letterhead;
	vista.set_default_letterhead = function () {
		return Promise.resolve(membrete_por_defecto.call(this)).then(() => quitar_membrete(this));
	};
})();

// Documentos de empresas que no son de RD: el selector no ofrece los formatos de la app
// (frappe.boot.rd_formatos_app y frappe.boot.empresas_rd, ver boot.py)
(() => {
	const vista = frappe.ui.form.PrintView.prototype;
	const original = vista.setup_sidebar;

	vista.setup_sidebar = function () {
		original.call(this);
		const consulta = this.print_format_field.df.get_query;
		this.print_format_field.df.get_query = () => {
			const filtro = consulta();
			const empresa = this.frm.doc?.company;
			if (empresa && !(frappe.boot.empresas_rd || []).includes(empresa)) {
				filtro.filters.name = ["not in", frappe.boot.rd_formatos_app || []];
			}
			return filtro;
		};
	};
})();
