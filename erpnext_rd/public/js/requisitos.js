// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt
// Tabla de requisitos con su estado: la usan el perfil tributario y el perfil de proveedor del Estado.
// Se carga con frappe.require("/assets/erpnext_rd/js/requisitos.js").

const ERPNEXT_RD_COLOR_ESTADO = {
	Cumplido: "green",
	Falta: "red",
	"Pendiente en la app": "orange",
	"Fuera del alcance": "gray",
};

window.erpnext_rd_tabla_requisitos = function ($wrapper, requisitos) {
	const e = frappe.utils.escape_html;
	const celda = "padding: 6px 8px; border-bottom: 1px solid var(--outline-gray-1); vertical-align: top";
	const titulo = "padding: 6px 8px; border-bottom: 1px solid var(--outline-gray-2); text-align: left; font-weight: 500; color: var(--ink-gray-5)";
	const filas = requisitos
		.map((r, i) => {
			const color = r.estado === "Falta" && !r.obligatorio ? "orange" : ERPNEXT_RD_COLOR_ESTADO[r.estado] || "gray";
			const enlace =
				r.ruta && r.estado === "Falta"
					? `<a href="#" data-fila="${i}" style="color: var(--ink-gray-8); text-decoration: underline">${__("Resolver")}</a>`
					: "";
			const recomendado = r.obligatorio ? "" : ` <span style="color: var(--ink-gray-5)">${__("(recomendado)")}</span>`;
			return `<tr>
				<td style="${celda}">${e(r.requisito)}${recomendado}</td>
				<td style="${celda}"><span class="indicator-pill ${color}">${e(__(r.estado))}</span></td>
				<td style="${celda}; color: var(--ink-gray-5)">${e(r.detalle || "")}</td>
				<td style="${celda}; text-align: right">${enlace}</td>
			</tr>`;
		})
		.join("");
	$wrapper.html(`<table style="width: 100%; border-collapse: collapse">
		<thead><tr><th style="${titulo}">${__("Requisito")}</th><th style="${titulo}">${__("Estado")}</th>
		<th style="${titulo}">${__("Detalle")}</th><th style="${titulo}"></th></tr></thead>
		<tbody>${filas}</tbody></table>`);
	$wrapper.find("a[data-fila]").on("click", function (ev) {
		ev.preventDefault();
		frappe.set_route(...requisitos[$(this).data("fila")].ruta);
	});
};
