// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt

frappe.ui.form.on("Perfil Proveedor Estado", {
	setup(frm) {
		frm.set_query("company", () => ({ filters: { country: "Dominican Republic" } }));
	},

	refresh(frm) {
		frm.get_field("requisitos_html").$wrapper.empty();
		if (frm.is_new()) return;
		if (frm.perm[0]?.write) {
			frm.add_custom_button(__("Consultar el RPE"), () =>
				frappe
					.call({
						method: "erpnext_rd.licitaciones.proveedor.consultar_rpe",
						args: { company: frm.doc.company },
						freeze: true,
						freeze_message: __("Consultando la DGCP..."),
					})
					.then(({ message }) => {
						frm.reload_doc();
						frappe.show_alert({
							message: __("RPE {0}: {1}. Rubros: {2}.", [message.rpe, __(message.estado), message.rubros]),
							indicator: message.estado === "Activo" ? "green" : "orange",
						});
					})
			);
		}
		// El RPE se busca por el RNC de la empresa: si la razón social no se parece, el RNC puede estar mal
		const normal = (t) =>
			(t || "")
				.normalize("NFD")
				.replace(/[̀-ͯ]/g, "")
				.toUpperCase()
				.replace(/\b(S\.?R\.?L|S\.?A\.?S?|E\.?I\.?R\.?L)\b/g, "")
				.replace(/[^A-Z0-9]/g, "");
		const rpe = normal(frm.doc.razon_social_rpe);
		const empresa = normal(frm.doc.company);
		if (rpe && empresa && !rpe.includes(empresa) && !empresa.includes(rpe)) {
			frm.set_intro(
				__("El RNC de la empresa está inscrito en el RPE como «{0}». Si no es esta empresa, corrija su RNC («Tax ID»).", [
					frappe.utils.escape_html(frm.doc.razon_social_rpe),
				]),
				"orange"
			);
		}
		frappe
			.call({ method: "erpnext_rd.licitaciones.proveedor.requisitos", args: { company: frm.doc.company } })
			.then(({ message }) =>
				frappe.require("/assets/erpnext_rd/js/requisitos.js", () =>
					erpnext_rd_tabla_requisitos(frm.get_field("requisitos_html").$wrapper, message || [])
				)
			);
	},
});
