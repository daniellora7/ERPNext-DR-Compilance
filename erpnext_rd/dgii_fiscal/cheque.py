"""Cheque RD: formato de impresión del *Payment Entry* para cheques de bancos dominicanos.

Arriba el cheque (fecha, beneficiario, monto en números y en letras) y abajo el talón o comprobante
de pago: facturas pagadas, retenciones, distribución contable y firmas, como el cheque-voucher que
usan las empresas en RD. Cada banco ubica los campos del cheque en otra posición: se ajustan en el
CSS del formato (variables `--rd-cheque-*`), desde el constructor de formatos de Frappe
(`erpnext_rd/formatos.py`).
"""

import re

import frappe
from frappe.utils import flt, fmt_money, formatdate

from erpnext_rd.dgii_reportes.datos import rnc_empresa
from erpnext_rd.formatos import por_documento

FORMATO = "Cheque RD"
DEFINICION = {
	"name": FORMATO,
	"doc_type": "Payment Entry",
	"carpeta": "cheque_rd",
	"margen": 0,
	"bloques": [
		("Cheque (fecha, beneficiario y monto)", "cheque"),
		("Comprobante de pago (talón)", "talon"),
		("Firmas", "firmas"),
	],
}
MONEDAS = {
	"DOP": ("peso", "pesos"),
	"USD": ("dólar", "dólares"),
	"EUR": ("euro", "euros"),
}


def _numero(valor: float) -> str:
	"""Monto con el formato de números del sitio, sin símbolo de moneda."""
	return fmt_money(valor, precision=2, currency=None) if flt(valor) else ""


def monto_en_letras(monto: float, moneda: str = "DOP") -> str:
	"""Como se escribe en un cheque: «MIL DOSCIENTOS TREINTA Y CUATRO PESOS CON 56/100»."""
	from num2words import num2words

	centavos = round(flt(monto) * 100)
	entero, fraccion = divmod(abs(centavos), 100)
	palabras = num2words(entero, lang="es")
	# Apócope del «uno» ante sustantivo: «veintiún mil», «un peso», «treinta y un pesos»
	palabras = re.sub(r"\bveintiuno\b(?= mil\b)", "veintiún", palabras)
	palabras = re.sub(r"\buno\b(?= mil\b)", "un", palabras)
	palabras = re.sub(r"veintiuno$", "veintiún", palabras)
	palabras = re.sub(r"\buno$", "un", palabras)
	if entero and entero % 1_000_000 == 0:
		palabras += " de"
	singular, plural = MONEDAS.get(moneda, ("", moneda))
	nombre = singular if entero == 1 else plural
	return f"{palabras} {nombre} con {fraccion:02d}/100".replace("  ", " ").upper()


def _documento(party_type: str | None, party: str | None) -> str:
	if party_type not in ("Supplier", "Customer", "Employee") or not party:
		return ""
	if party_type == "Employee":
		return frappe.db.get_value("Employee", party, "rd_cedula") or ""
	return frappe.db.get_value(party_type, party, "tax_id") or ""


def _distribucion(doc) -> list[frappe._dict]:
	"""Asiento del pago: del libro mayor si está aprobado; si no, lo que se registrará."""
	if doc.docstatus == 1:
		return [
			frappe._dict(cuenta=g.account, debito=flt(g.debit), credito=flt(g.credit))
			for g in frappe.get_all(
				"GL Entry",
				filters={"voucher_type": doc.doctype, "voucher_no": doc.name, "is_cancelled": 0},
				fields=["account", "sum(debit) as debit", "sum(credit) as credit"],
				group_by="account",
				order_by="sum(debit) desc, account",
			)
		]
	filas = [frappe._dict(cuenta=doc.paid_to, debito=flt(doc.base_paid_amount), credito=0.0)]
	for d in doc.get("deductions") or []:
		filas.append(
			frappe._dict(
				cuenta=d.account,
				debito=max(flt(d.amount), 0.0),
				credito=max(-flt(d.amount), 0.0),
			)
		)
	filas.append(frappe._dict(cuenta=doc.paid_from, debito=0.0, credito=flt(doc.base_paid_amount)))
	return filas


@por_documento
def rd_datos_cheque(doc) -> frappe._dict:
	"""Datos del cheque y su talón (método Jinja registrado en hooks.py)."""
	moneda = doc.get("paid_from_account_currency") or doc.get("paid_to_account_currency") or "DOP"
	monto = flt(doc.paid_amount)
	fecha = doc.reference_date or doc.posting_date
	banco = None
	if doc.get("bank_account"):
		banco = frappe.db.get_value(
			"Bank Account", doc.bank_account, ["bank", "bank_account_no"], as_dict=True
		)
	return frappe._dict(
		empresa=doc.company,
		rnc=rnc_empresa(doc.company) or "",
		fecha=formatdate(fecha, "dd/MM/yyyy"),
		numero=doc.reference_no or "",
		beneficiario=doc.party_name or doc.party or "",
		documento=_documento(doc.party_type, doc.party),
		monto=fmt_money(monto, precision=2, currency=None),
		simbolo="RD$" if moneda == "DOP" else (frappe.db.get_value("Currency", moneda, "symbol") or moneda),
		letras=monto_en_letras(monto, moneda),
		banco=(banco.bank if banco else "") or "",
		cuenta_banco=(banco.bank_account_no if banco else "") or doc.paid_from or "",
		concepto=doc.remarks or "",
		facturas=[
			frappe._dict(
				tipo=r.reference_doctype,
				documento=r.reference_name,
				ncf=_ncf(r.reference_doctype, r.reference_name),
				monto=flt(r.allocated_amount),
			)
			for r in doc.get("references") or []
			if flt(r.allocated_amount)
		],
		retenciones=[
			frappe._dict(cuenta=d.account, monto=flt(d.amount))
			for d in doc.get("deductions") or []
			if flt(d.amount)
		],
		distribucion=_distribucion(doc),
		# Para los montos del talón: c.cifra(monto)
		cifra=_numero,
	)


def _ncf(doctype: str, name: str) -> str:
	if doctype not in ("Purchase Invoice", "Sales Invoice"):
		return ""
	return frappe.db.get_value(doctype, name, "rd_ncf") or ""


def crear_formato():
	from erpnext_rd import formatos

	formatos.asegurar(DEFINICION, formatos.MODULO_FISCAL)
