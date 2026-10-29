<template>
	<FrappeUIProvider>
		<!-- Pantallas del celular (escanear facturas): se instalan como app -->
		<MobileShell v-if="$route.meta.movil">
			<RouterView />
			<template #nav>
				<!-- Pestañas propias (no MobileNavItem): en frappe-ui 1.0.2 nunca marca la ruta actual y sus
				     grises se confunden con el fondo en el tema claro. -->
				<MobileNav>
					<RouterLink
						v-for="p in pestanas"
						:key="p.ruta"
						v-slot="{ href, navigate, isExactActive }"
						:to="{ name: p.ruta }"
						custom
					>
						<a
							:href="href"
							:aria-current="isExactActive ? 'page' : undefined"
							class="flex min-h-14 items-center justify-center py-2 transition active:scale-95"
							@click="navigate"
						>
							<span
								class="flex flex-col items-center gap-1 transition-colors"
								:class="isExactActive ? 'text-ink-gray-9' : 'text-ink-gray-6'"
							>
								<span class="size-6" :class="p.icono" aria-hidden="true" />
								<span class="text-xs-medium leading-tighter">{{ p.label }}</span>
							</span>
						</a>
					</RouterLink>
				</MobileNav>
			</template>
		</MobileShell>

		<!-- Dentro del escritorio la navegación la da el sidebar del escritorio -->
		<div v-else-if="embebido" class="h-screen overflow-y-auto">
			<RouterView />
		</div>

		<!-- El shell usa h-full: necesita la altura de la ventana para fijar el sidebar y el encabezado -->
		<DesktopShell v-else class="h-screen">
			<template #sidebar>
				<Sidebar>
					<SidebarHeader title="RD Compliance" subtitle="ERPNext RD">
						<template #prefix>
							<Logo class="size-7" />
						</template>
					</SidebarHeader>

					<div class="flex-1 overflow-y-auto px-2 py-2">
						<SidebarItem :label="__('Panel')" icon="lucide-layout-dashboard" route="/" />

						<SidebarLabel>{{ __("DGII Fiscal") }}</SidebarLabel>
						<SidebarItem
							:label="__('Secuencias NCF')"
							icon="lucide-list-ordered"
							:href="rutaDocumento('Secuencia NCF')"
						/>
						<SidebarItem
							:label="__('Configuración DGII')"
							icon="lucide-settings"
							:href="rutaDocumento('Configuracion DGII')"
						/>

						<SidebarLabel>{{ __("Compras") }}</SidebarLabel>
						<SidebarItem
							:label="__('Escanear facturas')"
							icon="lucide-scan-qr-code"
							:route="{ name: 'Escanear' }"
						/>
						<SidebarItem
							:label="__('Capturas de compras')"
							icon="lucide-scan-line"
							:href="rutaDocumento('Captura Compra')"
						/>

						<SidebarLabel>{{ __("Reportes DGII") }}</SidebarLabel>
						<SidebarItem
							v-for="r in reportes"
							:key="r.reporte"
							:label="r.label"
							icon="lucide-file-text"
							:href="rutaReporte(r.reporte)"
						/>
					</div>

					<div class="px-2 pb-2">
						<SidebarItem :label="__('Ir al escritorio')" icon="lucide-arrow-left" href="/desk" />
					</div>
				</Sidebar>
			</template>

			<RouterView />
		</DesktopShell>
	</FrappeUIProvider>
</template>

<script setup>
import {
	DesktopShell,
	FrappeUIProvider,
	MobileNav,
	MobileShell,
	Sidebar,
	SidebarHeader,
	SidebarItem,
	SidebarLabel,
} from "frappe-ui"

import Logo from "@/components/Logo.vue"
import { __ } from "@/translation"
import { embebido, rutaDocumento, rutaReporte } from "@/utils"

const pestanas = [
	{ label: __("Escanear"), icono: "lucide-scan-qr-code", ruta: "Escanear" },
	{ label: __("Mis capturas"), icono: "lucide-list", ruta: "Capturas" },
]

const reportes = [
	{ label: __("Formato {0}", ["606"]), reporte: "Formato 606 DGII" },
	{ label: __("Formato {0}", ["607"]), reporte: "Formato 607 DGII" },
	{ label: __("Formato {0}", ["608"]), reporte: "Formato 608 DGII" },
	{ label: __("Formato {0}", ["609"]), reporte: "Formato 609 DGII" },
	{ label: __("Resumen IT-1"), reporte: "Resumen IT-1 DGII" },
	{ label: __("Resumen IR-17"), reporte: "Resumen IR-17 DGII" },
]
</script>
