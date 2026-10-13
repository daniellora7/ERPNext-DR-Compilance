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

# Fixtures
# --------
# Custom Fields / Property Setters exportados con `bench --site <sitio> export-fixtures --app erpnext_rd`

# fixtures = [
# 	{"dt": "Custom Field", "filters": [["module", "in", ["DGII Fiscal", "ECF", "Nomina RD"]]]},
# 	{"dt": "Property Setter", "filters": [["module", "in", ["DGII Fiscal", "ECF", "Nomina RD"]]]},
# ]

# Document Events
# ---------------

# doc_events = {
# 	"Sales Invoice": {
# 		"validate": "erpnext_rd.dgii_fiscal.ncf.validate_invoice",
# 		"on_submit": "erpnext_rd.dgii_fiscal.ncf.assign_ncf",
# 	},
# }

# Scheduled Tasks
# ---------------

# scheduler_events = {
# 	"daily": ["erpnext_rd.padron_rnc.sync.sync_padron"],
# 	"cron": {"*/10 * * * *": ["erpnext_rd.ecf.tasks.consultar_estados"]},
# }

# Testing
# -------

# before_tests = "erpnext_rd.install.before_tests"
