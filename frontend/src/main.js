import { createApp } from "vue"
import { setConfig, frappeRequest } from "frappe-ui"

import App from "./App.vue"
import router from "./router"
import "./index.css"

setConfig("resourceFetcher", frappeRequest)

createApp(App).use(router).mount("#app")
