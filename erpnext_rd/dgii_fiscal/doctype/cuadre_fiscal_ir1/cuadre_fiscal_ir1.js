// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Cuadre Fiscal IR1", {
	setup(frm) {
		frm.set_query("company", () => ({ filters: { country: "Dominican Republic" } }));
	},

	refresh(frm) {
		if (frm.doc.avisos) {
			frm.dashboard.set_headline_alert(
				frappe.utils.escape_html(frm.doc.avisos).replace(/\n/g, "<br>"),
				"orange"
			);
		}
		if (frm.is_new()) return;
		if (frm.doc.docstatus === 0) {
			frm.add_custom_button(__("Traer datos de la contabilidad"), () =>
				frappe.confirm(
					__("Se vuelven a tomar los ingresos, el beneficio y los anticipos. ¿Continuar?"),
					() =>
						frappe
							.call({
								method: "erpnext_rd.dgii_reportes.ir1.traer_datos",
								args: { name: frm.doc.name },
								freeze: true,
							})
							.then(() => frm.reload_doc())
				)
			);
		}
		if (frm.doc.docstatus < 2 && frm.doc.impuesto_liquidado) {
			frm.add_custom_button(__("Crear base de anticipos"), () =>
				frappe
					.call({ method: "erpnext_rd.dgii_reportes.ir1.crear_base_anticipos", args: { name: frm.doc.name } })
					.then(({ message }) => frappe.set_route("Form", "Base Anticipo ISR", message))
			);
		}
	},
});
