// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt

frappe.listview_settings["Proceso Compra DGCP"] = {
	add_fields: ["estado_proceso", "fecha_fin_recepcion_ofertas"],
	get_indicator(doc) {
		const color = {
			"Proceso publicado": "blue",
			"Sobres abiertos o aperturados": "orange",
			"Proceso con etapa cerrada": "orange",
			"Proceso adjudicado y celebrado": "green",
			"Proceso desierto": "gray",
			Cancelado: "red",
		}[doc.estado_proceso];
		return [__(doc.estado_proceso || "Sin estado"), color || "gray", `estado_proceso,=,${doc.estado_proceso}`];
	},
	onload(listview) {
		if (!frappe.user.has_role(["System Manager", "Sales Manager"])) return;
		listview.page.add_inner_button(__("Descargar de la DGCP"), () =>
			frappe
				.call({ method: "erpnext_rd.licitaciones.procesos.sincronizar_ahora" })
				.then(({ message }) => frappe.show_alert({ message, indicator: "blue" }))
		);
	},
};
