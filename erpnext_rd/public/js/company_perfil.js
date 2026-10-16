// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt
// Empresa de RD: aviso del perfil tributario y asistente para completarlo (rd_compliance/perfil.py).

frappe.ui.form.on("Company", {
	refresh(frm) {
		if (frm.is_new() || frm.doc.country !== "Dominican Republic") return;
		frappe
			.call({ method: "erpnext_rd.rd_compliance.perfil.estado_empresa", args: { company: frm.doc.name } })
			.then(({ message: estado }) => {
				if (!estado || !estado.aplica) return;
				if (!estado.existe) {
					frm.dashboard.set_headline_alert(
						`${__("Esta empresa no tiene perfil tributario: la app la trata como persona jurídica del régimen ordinario.")}
						<a href="#" data-rd-perfil style="margin-left: 8px; text-decoration: underline">${__("Configurar perfil tributario")}</a>`,
						"orange"
					);
					// El aviso se dibuja fuera del área de alertas del tablero: se escucha en el formulario
					frm.$wrapper.off("click.rd_perfil").on("click.rd_perfil", "[data-rd-perfil]", (ev) => {
						ev.preventDefault();
						erpnext_rd_asistente_perfil(frm.doc.name);
					});
				} else if (estado.faltan) {
					frm.dashboard.set_headline_alert(
						`${__("{0} requisitos fiscales pendientes.", [estado.faltan])}
						<a style="margin-left: 8px" href="/app/perfil-tributario-rd/${encodeURIComponent(frm.doc.name)}">${__("Ver requisitos")}</a>`,
						"orange"
					);
				}
				frm.add_custom_button(__("Perfil tributario"), () =>
					estado.existe
						? frappe.set_route("Form", "Perfil Tributario RD", frm.doc.name)
						: erpnext_rd_asistente_perfil(frm.doc.name)
				);
			});
	},
});

function erpnext_rd_asistente_perfil(company) {
	const pasos = [
		{
			titulo: __("Contribuyente y régimen"),
			campos: [
				{
					fieldname: "tipo_contribuyente",
					label: __("Tipo de contribuyente"),
					fieldtype: "Select",
					options: ["Persona jurídica", "Persona física con negocio"],
					default: "Persona jurídica",
					reqd: 1,
				},
				{
					fieldname: "regimen",
					label: __("Régimen"),
					fieldtype: "Select",
					options: ["Ordinario", "Simplificado (RST)"],
					default: "Ordinario",
					reqd: 1,
				},
				{
					fieldname: "tamano",
					label: __("Tamaño de la empresa (Ley 30-26)"),
					fieldtype: "Select",
					options: ["", "Micro", "Pequeña", "Mediana", "Grande"],
					reqd: 1,
				},
				{
					fieldname: "cierre_fiscal",
					label: __("Cierre fiscal"),
					fieldtype: "Select",
					options: ["31 de diciembre", "31 de marzo", "30 de junio", "30 de septiembre"],
					default: "31 de diciembre",
					reqd: 1,
				},
			],
		},
		{
			titulo: __("Actividades con tratamiento especial"),
			campos: [
				{ fieldname: "isc_alcohol", label: __("Produce o importa bebidas alcohólicas (ISC)"), fieldtype: "Check" },
				{ fieldname: "isc_tabaco", label: __("Produce o importa productos del tabaco (ISC)"), fieldtype: "Check" },
				{ fieldname: "isc_combustibles", label: __("Vende o importa combustibles (ISC)"), fieldtype: "Check" },
				{ fieldname: "isc_telecomunicaciones", label: __("Presta servicios de telecomunicaciones (ISC)"), fieldtype: "Check" },
				{ fieldname: "isc_seguros", label: __("Vende seguros (ISC)"), fieldtype: "Check" },
				{ fieldname: "propina_legal", label: __("Cobra propina legal (restaurantes y bares)"), fieldtype: "Check" },
				{ fieldname: "partes_relacionadas", label: __("Tiene operaciones con partes relacionadas (DIOR)"), fieldtype: "Check" },
				{ fieldname: "exportador", label: __("Exporta bienes o servicios"), fieldtype: "Check" },
				{ fieldname: "agente_retencion", label: __("Designada agente de retención por la DGII"), fieldtype: "Check" },
				{
					fieldname: "sector_regulado",
					label: __("Sector regulado"),
					fieldtype: "Select",
					options: ["", "Banca", "Seguros", "Pensiones (AFP)", "Otro sector regulado"],
				},
			],
		},
		{
			titulo: __("Facturación electrónica"),
			campos: [
				{
					fieldname: "ecf_estado",
					label: __("Situación con el e-CF"),
					fieldtype: "Select",
					options: ["No obligada aún", "En certificación", "Emisor electrónico"],
					default: "No obligada aún",
					reqd: 1,
				},
				{ fieldname: "ecf_obligada_desde", label: __("Obligada desde"), fieldtype: "Date" },
				{
					fieldname: "nota_incentivos",
					fieldtype: "HTML",
					options: `<p style="color: var(--ink-gray-5)">${__(
						"Los regímenes especiales e incentivos (zona franca, Proindustria, turismo...) se agregan después en el perfil."
					)}</p>`,
				},
			],
		},
	];

	let paso = 0;
	const dialogo = new frappe.ui.Dialog({
		title: __("Perfil tributario de {0}", [company]),
		fields: pasos.flatMap((p) => p.campos),
		size: "large",
	});

	const mostrar = () => {
		pasos.forEach((p, i) => p.campos.forEach((c) => dialogo.get_field(c.fieldname).$wrapper.toggle(i === paso)));
		dialogo.set_title(`${__("Perfil tributario")} · ${pasos[paso].titulo} (${paso + 1}/${pasos.length})`);
		dialogo.set_primary_action(paso < pasos.length - 1 ? __("Siguiente") : __("Guardar"), avanzar);
		dialogo.get_secondary_btn().toggle(paso > 0);
	};

	const avanzar = () => {
		const faltan = pasos[paso].campos.filter((c) => c.reqd && !dialogo.get_value(c.fieldname));
		if (faltan.length) {
			frappe.msgprint(__("Complete: {0}", [faltan.map((c) => c.label).join(", ")]));
			return;
		}
		if (paso < pasos.length - 1) {
			paso += 1;
			mostrar();
			return;
		}
		frappe
			.call({
				method: "erpnext_rd.rd_compliance.perfil.guardar",
				args: { company, valores: dialogo.get_values(true) },
				freeze: true,
			})
			.then(({ message }) => {
				dialogo.hide();
				frappe.set_route("Form", "Perfil Tributario RD", message);
			});
	};

	dialogo.set_secondary_action_label(__("Anterior"));
	dialogo.set_secondary_action(() => {
		paso -= 1;
		mostrar();
	});
	dialogo.show();
	mostrar();
}
