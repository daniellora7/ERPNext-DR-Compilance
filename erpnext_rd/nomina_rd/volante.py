"""Volante de pago RD: formato de impresión del recibo de nómina (Salary Slip de Frappe HR).

Muestra lo que el empleado necesita ver en RD: empresa y RNC, documento (cédula, NSS o pasaporte), NSS,
AFP y ARS, ingresos y descuentos de ley (AFP, SFS, ISR, INFOTEP), neto a pagar y, como información,
los aportes del empleador a la TSS e INFOTEP. El formato se crea por código (`crear_formato`) solo si
Frappe HR está instalado, porque un archivo de formato no se podría sincronizar sin el DocType.
"""

import frappe
from frappe.utils import cint, flt, formatdate

from erpnext_rd.dgii_reportes.datos import rnc_empresa
from erpnext_rd.nomina_rd import hrms_instalado

FORMATO = "Volante de pago RD"
DOCTYPE = "Salary Slip"
PLANTILLA = '{% include "erpnext_rd/templates/print/volante_pago_rd.html" %}'
TIPOS_DOCUMENTO = {"C": "Cédula", "N": "NSS", "P": "Pasaporte"}


def _cedula(numero: str) -> str:
	return f"{numero[:3]}-{numero[3:10]}-{numero[10:]}" if len(numero) == 11 and numero.isdigit() else numero


def _filas(doc, tabla: str) -> list[frappe._dict]:
	return [
		frappe._dict(concepto=fila.salary_component, monto=flt(fila.amount))
		for fila in doc.get(tabla) or []
		if flt(fila.amount)
		and not cint(fila.get("statistical_component"))
		and not cint(fila.get("do_not_include_in_total"))
	]


def rd_datos_volante(doc) -> frappe._dict:
	"""Datos del volante (método Jinja registrado en hooks.py)."""
	from erpnext_rd.nomina_rd import tss

	emp = (
		frappe.db.get_value(
			"Employee",
			doc.employee,
			[
				"employee_name",
				"designation",
				"department",
				"date_of_joining",
				"rd_tipo_documento",
				"rd_cedula",
				"rd_nss",
				"rd_numero_documento",
				"passport_number",
				"rd_afp",
				"rd_ars",
			],
			as_dict=True,
		)
		or frappe._dict()
	)
	tipo, numero, _avisos = tss.documento(emp)
	aportes = _filas(doc, "employer_contributions") if doc.meta.has_field("employer_contributions") else []
	return frappe._dict(
		empresa=doc.company,
		rnc=rnc_empresa(doc.company) or "",
		periodo=f"{formatdate(doc.start_date)} - {formatdate(doc.end_date)}",
		fecha=formatdate(doc.posting_date),
		empleado=emp.employee_name or doc.employee_name,
		tipo_documento=TIPOS_DOCUMENTO.get(tipo, "Documento"),
		documento=_cedula(numero) if tipo == "C" else numero,
		nss=emp.rd_nss if tipo != "N" else "",
		cargo=emp.designation or "",
		departamento=(emp.department or "").rsplit(" - ", 1)[0],
		ingreso=formatdate(emp.date_of_joining) if emp.date_of_joining else "",
		afp=emp.rd_afp or "",
		ars=emp.rd_ars or "",
		dias=f"{flt(doc.payment_days):g} / {flt(doc.total_working_days):g}",
		ingresos=_filas(doc, "earnings"),
		descuentos=_filas(doc, "deductions"),
		aportes=aportes,
		total_aportes=sum(f.monto for f in aportes),
	)


def crear_formato():
	"""Crea el formato si Frappe HR está instalado y lo deja por defecto si el recibo no tiene otro."""
	if not hrms_instalado():
		return
	if not frappe.db.exists("Print Format", FORMATO):
		frappe.get_doc(
			{
				"doctype": "Print Format",
				"name": FORMATO,
				"doc_type": DOCTYPE,
				"module": "Nomina RD",
				"standard": "No",
				"custom_format": 1,
				"print_format_type": "Jinja",
				"default_print_language": "es",
				"font_size": 11,
				"margin_top": 12,
				"margin_bottom": 12,
				"margin_left": 12,
				"margin_right": 12,
				"html": PLANTILLA,
			}
		).insert(ignore_permissions=True)
	if not frappe.db.get_value(
		"Property Setter", {"doc_type": DOCTYPE, "property": "default_print_format"}, "value"
	):
		from frappe.custom.doctype.property_setter.property_setter import make_property_setter

		make_property_setter(
			DOCTYPE,
			None,
			"default_print_format",
			FORMATO,
			"Data",
			for_doctype=True,
			validate_fields_for_doctype=False,
		)


def quitar_formato():
	"""Al desinstalar Frappe HR (o la app): el formato y su uso por defecto."""
	frappe.db.delete("Property Setter", {"property": "default_print_format", "value": FORMATO})
	if frappe.db.exists("Print Format", FORMATO):
		frappe.delete_doc("Print Format", FORMATO, force=True, ignore_permissions=True)
