app_name = "erpnext_rd"
app_title = "ERPNext RD"
app_publisher = "ERPNext RD"
app_description = "Localizacion Republica Dominicana para ERPNext: NCF, e-CF DGII, reportes 606/607/608 y nomina RD"
app_email = "daniellorap.ing@gmail.com"
app_license = "gpl-3.0"

# Apps
# ------------------

required_apps = ["erpnext", "hrms"]

# Includes in <head>
# ------------------

# app_include_css = "/assets/erpnext_rd/css/erpnext_rd.css"
# app_include_js = "/assets/erpnext_rd/js/erpnext_rd.js"

# Navegación: un solo módulo "RD Compliance" en el dock de ERPNext (dock/erpnext_rd, mount_on =
# erpnext), con su sidebar de secciones en rd_compliance/sidebar. Los módulos de código le ceden
# su navegación, así todo lo suyo abre dentro de RD Compliance.
app_include_icons = ["/assets/erpnext_rd/icons/erpnext-rd-icons.svg"]
code_only_modules = {
	"DGII Fiscal": ["RD Compliance"],
	"DGII Reportes": ["RD Compliance"],
	"Padron RNC": ["RD Compliance"],
	"ECF": ["RD Compliance"],
	"Nomina RD": ["RD Compliance"],
	"ERPNext RD": ["RD Compliance"],
}

# Instalación
# ------------

after_install = "erpnext_rd.install.after_install"
after_migrate = "erpnext_rd.install.after_migrate"

# JS por DocType
# --------------

doctype_js = {
	"Customer": "public/js/party_rnc.js",
	"Supplier": "public/js/party_rnc.js",
	"Sales Invoice": "public/js/invoice_dgii.js",
	"POS Invoice": "public/js/invoice_dgii.js",
	"Purchase Invoice": "public/js/invoice_dgii.js",
}

# Document Events
# ---------------

doc_events = {
	"Company": {
		"validate": "erpnext_rd.dgii_fiscal.identificacion.validar_party",
		"on_update": "erpnext_rd.dgii_fiscal.catalogo_cuentas.al_actualizar_empresa",
	},
	"Customer": {
		"validate": "erpnext_rd.dgii_fiscal.identificacion.validar_party",
	},
	"Supplier": {
		"validate": "erpnext_rd.dgii_fiscal.identificacion.validar_party",
	},
	"Sales Invoice": {
		"validate": "erpnext_rd.dgii_fiscal.ncf.validar_venta",
		"before_submit": "erpnext_rd.dgii_fiscal.ncf.asignar_ncf_venta",
		"before_cancel": "erpnext_rd.dgii_fiscal.ncf.antes_de_cancelar_venta",
	},
	"POS Invoice": {
		"validate": "erpnext_rd.dgii_fiscal.ncf.validar_venta",
		"before_submit": "erpnext_rd.dgii_fiscal.ncf.asignar_ncf_venta",
		"before_cancel": "erpnext_rd.dgii_fiscal.ncf.antes_de_cancelar_venta",
	},
	"Purchase Invoice": {
		"validate": "erpnext_rd.dgii_fiscal.ncf.validar_compra",
		"before_submit": "erpnext_rd.dgii_fiscal.ncf.antes_de_validar_compra",
		"before_cancel": "erpnext_rd.dgii_fiscal.ncf.antes_de_cancelar_compra",
	},
}

# Jinja (formatos de impresión)
# -----------------------------

jinja = {
	"methods": ["erpnext_rd.dgii_fiscal.impresion.rd_datos_fiscales"],
}

# Scheduled Tasks
# ---------------

scheduler_events = {
	"weekly_long": ["erpnext_rd.padron_rnc.padron.sincronizar_padron"],
}
