// __() como en el escritorio de Frappe: el texto fuente (en español, como el resto de la app) se busca en las
// traducciones de los .po de erpnext_rd que manda www/rd_compliance.py en window.__messages; si no está, queda igual.
// {0}, {1}... se reemplazan por los valores, en orden.

const mensajes = window.__messages || {}

export function __(texto, valores = [], contexto = null) {
	const traducido = (contexto && mensajes[`${texto}:${contexto}`]) || mensajes[texto] || texto
	return traducido.replace(/\{(\d+)\}/g, (marca, i) => (valores[i] ?? marca))
}

export default {
	install(app) {
		app.config.globalProperties.__ = __
	},
}
