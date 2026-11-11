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
		erpnext_rd_ofertas_proceso(frm);
		const cierre = frm.doc.fecha_fin_recepcion_ofertas;
		if (cierre && frm.doc.estado_proceso === "Proceso publicado" && frappe.datetime.str_to_obj(cierre) > new Date()) {
			frm.set_intro(__("Recibe ofertas hasta el {0}.", [frappe.datetime.str_to_user(cierre)]), "blue");
		}
	},
});

// Fase 10.5: la oferta de cada empresa es una oportunidad de ERPNext
function erpnext_rd_ofertas_proceso(frm) {
	if (!frappe.model.can_create("Opportunity")) return;
	frappe.db
		.get_list("Opportunity", {
			filters: { rd_proceso_dgcp: frm.doc.name },
			fields: ["name", "company", "rd_estado_oferta"],
		})
		.then((ofertas) => {
			for (const o of ofertas) {
				frm.add_custom_button(
					__("Oferta de {0} ({1})", [o.company, __(o.rd_estado_oferta || "")]),
					() => frappe.set_route("Form", "Opportunity", o.name),
					__("Ofertas")
				);
			}
			const con_oferta = new Set(ofertas.map((o) => o.company));
			const empresas = (frm.doc.empresas || []).map((e) => e.company).filter((c) => !con_oferta.has(c));
			if (empresas.length || !frm.doc.empresas?.length) {
				frm.add_custom_button(__("Crear oferta"), () => erpnext_rd_crear_oferta(frm, empresas), __("Ofertas"));
			}
		});
}

function erpnext_rd_crear_oferta(frm, empresas) {
	const crear = (company) =>
		frappe
			.call({
				method: "erpnext_rd.licitaciones.ofertas.crear_oportunidad",
				args: { codigo_proceso: frm.doc.name, company },
				freeze: true,
			})
			.then(({ message }) => frappe.set_route("Form", "Opportunity", message));
	if (empresas.length === 1) return crear(empresas[0]);
	const campo = empresas.length
		? { fieldtype: "Select", options: empresas.join("\n"), default: empresas[0] }
		: { fieldtype: "Link", options: "Company" };
	frappe.prompt(
		[{ fieldname: "company", label: __("Empresa"), reqd: 1, ...campo }],
		({ company }) => crear(company),
		__("Crear oferta"),
		__("Crear")
	);
}

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
