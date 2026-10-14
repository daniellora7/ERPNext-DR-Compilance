import path from "path"
import { defineConfig } from "vite"
import vue from "@vitejs/plugin-vue"
import frappeui from "frappe-ui/vite"

// Rutas explícitas: así compila igual dentro de un bench, en Frappe Cloud o fuera de un bench
const app = path.resolve(__dirname, "../erpnext_rd")

export default defineConfig({
	plugins: [
		frappeui({
			frontendRoute: "/rd-compliance",
			buildConfig: {
				outDir: path.join(app, "public/frontend"),
				baseUrl: "/assets/erpnext_rd/frontend/",
				indexHtmlPath: path.join(app, "www/rd-compliance.html"),
			},
		}),
		vue(),
	],
	resolve: {
		alias: { "@": path.resolve(__dirname, "src") },
	},
})
