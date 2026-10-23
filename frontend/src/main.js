import { createApp } from "vue"
import { setConfig, frappeRequest, useColorScheme } from "frappe-ui"

import App from "./App.vue"
import router from "./router"
import traducciones from "./translation"
import { embebido } from "./utils"
import "./index.css"

setConfig("resourceFetcher", frappeRequest)

// Mismo tema que el usuario eligió en el escritorio (Light / Dark / Automatic), aplicado antes de
// montar la app para que no parpadee. `desk_theme` lo envía www/rd_compliance.py.
const { setColorScheme } = useColorScheme()
setColorScheme({ Dark: "dark", Light: "light" }[window.desk_theme] || "system")

// Ancho completo o compacto, según la apariencia que el usuario eligió en el escritorio. Frappe la guarda
// en localStorage (mismo sitio) y la aplica como la clase full-width del <body> del escritorio.
const aplicarAncho = (completo) => {
	document.documentElement.dataset.ancho = completo ? "completo" : "compacto"
}
try {
	aplicarAncho(JSON.parse(localStorage.container_fullwidth || "false"))
} catch {
	aplicarAncho(false)
}

if (embebido) {
	const escritorio = window.top

	// Dentro del escritorio sigue a su <body> también cuando el usuario cambia la opción con el panel abierto
	const cuerpo = escritorio.document.body
	const seguirAncho = () => aplicarAncho(cuerpo.classList.contains("full-width"))
	seguirAncho()
	new MutationObserver(seguirAncho).observe(cuerpo, { attributes: true, attributeFilter: ["class"] })

	// El tema sigue al del escritorio también cuando el usuario lo cambia con el panel abierto
	const raiz = escritorio.document.documentElement
	const seguirTema = () => raiz.dataset.theme && setColorScheme(raiz.dataset.theme)
	seguirTema()
	new MutationObserver(seguirTema).observe(raiz, { attributes: true, attributeFilter: ["data-theme"] })

	// Los enlaces al escritorio navegan el escritorio en la misma ventana, como sus propios enlaces
	// (frappe/router.js); Ctrl/Cmd + clic sigue abriendo una pestaña nueva.
	document.addEventListener(
		"click",
		(e) => {
			const a = e.target.closest?.("a[href]")
			if (!a || e.ctrlKey || e.metaKey || e.shiftKey || a.hostname !== location.hostname) return
			if (!a.pathname.startsWith("/desk")) return
			e.preventDefault()
			escritorio.frappe.route_options = Object.fromEntries(new URLSearchParams(a.search))
			escritorio.frappe.set_route(a.pathname)
		},
		true,
	)
}

createApp(App).use(router).use(traducciones).mount("#app")
