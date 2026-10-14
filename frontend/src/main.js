import { createApp } from "vue"
import { setConfig, frappeRequest, useColorScheme } from "frappe-ui"

import App from "./App.vue"
import router from "./router"
import "./index.css"

setConfig("resourceFetcher", frappeRequest)

// Mismo tema que el usuario eligió en el escritorio (Light / Dark / Automatic), aplicado antes de
// montar la app para que no parpadee. `desk_theme` lo envía www/rd_compliance.py.
useColorScheme().setColorScheme({ Dark: "dark", Light: "light" }[window.desk_theme] || "system")

createApp(App).use(router).mount("#app")
