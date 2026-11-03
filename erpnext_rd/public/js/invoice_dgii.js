// Copyright (c) 2026, ERPNext RD
// License: GNU General Public License v3. See license.txt
// Sales / POS / Purchase Invoice: filtra los tipos de comprobante válidos.

// Formato de impresión de la empresa (frappe.boot.rd_formatos, ver boot.py): lo usan el botón Imprimir
// y el diálogo de correo, que toman el predeterminado del DocType.
function erpnext_rd_formato_de_empresa(frm) {
	const formatos = frappe.boot.rd_formatos?.[frm.doctype];
	if (!formatos) return;
	frm.meta.default_print_format = formatos.empresas[frm.doc.company] || formatos.defecto;
}

const erpnext_rd_invoice = {
	company(frm) {
		erpnext_rd_formato_de_empresa(frm);
	},

	setup(frm) {
		const filtro = frm.doctype === "Purchase Invoice" ? "aplica_compras" : "aplica_ventas";
		frm.set_query("rd_tipo_comprobante", () => ({ filters: { habilitado: 1, [filtro]: 1 } }));
	},

	refresh(frm) {
		erpnext_rd_formato_de_empresa(frm);

		// Compras: volver a consultar el NCF del proveedor en la DGII (ver consulta_ncf.py)
		if (frm.doctype === "Purchase Invoice" && !frm.is_new() && frm.doc.rd_ncf && frm.doc.docstatus < 2) {
			frm.add_custom_button(
				__("Verificar NCF en la DGII"),
				() =>
					frappe
						.call({
							method: "erpnext_rd.dgii_fiscal.consulta_ncf.verificar_factura",
							args: { name: frm.doc.name },
							freeze: true,
							freeze_message: __("Consultando la DGII..."),
						})
						.then(({ message }) => {
							frm.reload_doc();
							frappe.show_alert({
								message: __("NCF en la DGII: {0}", [__(message.estado)]),
								indicator: message.estado === "Válido" ? "green" : "orange",
							});
						}),
				__("DGII")
			);
		}

		// e-CF: emitir (generar, firmar y enviar según el emisor) y ver sus envíos
		const electronico = (frm.doc.rd_tipo_comprobante || "").startsWith("E") && frm.doc.rd_ncf;
		if (frm.doctype === "POS Invoice" || frm.doc.docstatus !== 1 || !electronico) return;
		frm.add_custom_button(
			__("Emitir e-CF"),
			() =>
				frappe
					.call({
						method: "erpnext_rd.ecf.emision.emitir",
						args: { doctype: frm.doctype, name: frm.doc.name },
						freeze: true,
						freeze_message: __("Firmando el e-CF..."),
					})
					.then(({ message }) => {
						frm.reload_doc();
						frappe.set_route("Form", "Envio ECF", message);
					}),
			__("e-CF")
		);
		frm.add_custom_button(
			__("Envíos e-CF"),
			() => frappe.set_route("List", "Envio ECF", { tipo_documento: frm.doctype, documento: frm.doc.name }),
			__("e-CF")
		);
	},
};

frappe.ui.form.on("Sales Invoice", erpnext_rd_invoice);
frappe.ui.form.on("POS Invoice", erpnext_rd_invoice);
frappe.ui.form.on("Purchase Invoice", erpnext_rd_invoice);

// ISC (dgii_fiscal/isc.py): base de cada línea de la fila «ISC por artículo», igual que en el servidor.
// Servicios: tasa sobre el neto. Bienes: ISC por unidad de inventario por la cantidad.
erpnext.taxable_base_resolvers = erpnext.taxable_base_resolvers || {};
erpnext.taxable_base_resolvers["ISC por artículo"] = (calc, item) => {
	if (flt(item.rd_isc_tasa)) return (flt(item.net_amount) * flt(item.rd_isc_tasa)) / 100;
	return flt(item.rd_isc_unitario) * flt(item.qty) * (flt(item.conversion_factor) || 1);
};

// Al elegir el artículo, su ISC por unidad (la fila del ISC se agrega al guardar)
const erpnext_rd_isc_linea = {
	item_code(frm, cdt, cdn) {
		const row = locals[cdt][cdn];
		if (!row.item_code || !frm.doc.company) return;
		frappe
			.call({
				method: "erpnext_rd.dgii_fiscal.isc.isc_de_articulo",
				args: { company: frm.doc.company, item_code: row.item_code, fecha: frm.doc.posting_date },
			})
			.then(({ message }) => {
				const tasa_cambio = flt(frm.doc.conversion_rate) || 1;
				frappe.model.set_value(cdt, cdn, {
					rd_isc_categoria: message?.categoria || "",
					rd_isc_tasa: message?.tasa || 0,
					rd_isc_unitario: message ? flt(message.unitario) / tasa_cambio : 0,
				});
				frm.cscript.calculate_taxes_and_totals?.();
			});
	},
};

frappe.ui.form.on("Sales Invoice Item", erpnext_rd_isc_linea);
frappe.ui.form.on("POS Invoice Item", erpnext_rd_isc_linea);
