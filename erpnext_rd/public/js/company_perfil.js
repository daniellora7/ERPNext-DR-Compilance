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
					const enlace = estado.puede_configurar
						? `<a href="#" data-rd-perfil style="margin-left: 8px; text-decoration: underline">${__("Configurar perfil tributario")}</a>`
						: "";
					frm.dashboard.set_headline_alert(
						`${__("Esta empresa no tiene perfil tributario: la app la trata como persona jurídica del régimen ordinario.")}
						${enlace}`,
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
				if (!estado.existe && !estado.puede_configurar) return;
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
					label: __("Tamaño de la empresa"),
					fieldtype: "Select",
					options: [
						"",
						"Micro (hasta 10 empleados)",
						"Pequeña (11 a 50 empleados)",
						"Mediana (51 a 150 empleados)",
						"Grande (más de 150 empleados)",
					],
					reqd: 1,
					description: __(
						"Por cantidad de trabajadores y ventas brutas anuales (Ley 488-08 de mipymes). Si no coinciden, consulte la clasificación del MICM."
					),
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
			actividades: true,
			campos: [
				{
					fieldname: "ninguna_actividad",
					label: __("No aplica: la empresa no realiza ninguna de estas actividades"),
					fieldtype: "Check",
					onchange: () => {
						if (dialogo.get_value("ninguna_actividad")) ACTIVIDADES.forEach((a) => dialogo.set_value(a, 0));
					},
				},
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
					options: ["No aplica", "Banca", "Seguros", "Pensiones (AFP)", "Otro sector regulado"],
					default: "No aplica",
					reqd: 1,
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

	const ACTIVIDADES = [
		"isc_alcohol",
		"isc_tabaco",
		"isc_combustibles",
		"isc_telecomunicaciones",
		"isc_seguros",
		"propina_legal",
		"partes_relacionadas",
		"exportador",
		"agente_retencion",
	];
	pasos[1].campos
		.filter((c) => ACTIVIDADES.includes(c.fieldname))
		.forEach((c) => {
			c.onchange = () => {
				if (dialogo.get_value(c.fieldname)) dialogo.set_value("ninguna_actividad", 0);
			};
		});

	let paso = 0;
	const dialogo = new frappe.ui.Dialog({
		title: __("Perfil tributario de {0}", [company]),
		fields: pasos.flatMap((p) => p.campos),
		size: "large",
	});
	// Borde visible de las listas y campos también en el tema oscuro (solo tokens)
	dialogo.$wrapper.addClass("rd-perfil-asistente");
	frappe.dom.set_style(
		`.rd-perfil-asistente .form-control:not(:focus) { box-shadow: inset 0 0 0 1px var(--outline-gray-3); }`,
		"rd-perfil-asistente"
	);

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
		if (pasos[paso].actividades && !dialogo.get_value("ninguna_actividad") && !ACTIVIDADES.some((a) => dialogo.get_value(a))) {
			frappe.msgprint(__("Marque las actividades que realiza la empresa o «No aplica»."));
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
