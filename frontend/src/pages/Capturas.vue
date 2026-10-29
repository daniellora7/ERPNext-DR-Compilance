<!-- Mis capturas: las facturas que envió el usuario, con su estado (y las que esperan conexión). -->
<template>
	<PageHeader>
		<PageHeaderTitle :title="__('Mis capturas')" />
		<Button icon="lucide-refresh-cw" :tooltip="__('Actualizar')" :loading="cargando" @click="cargar" />
	</PageHeader>

	<div class="mx-auto w-full max-w-md px-4 py-4">
		<Alert v-if="error" theme="amber" :title="__('Sin conexión')" :description="error" />
		<ul class="divide-y divide-outline-gray-1">
			<li v-for="p in pendientes" :key="p.id_cliente" class="flex items-center justify-between gap-3 py-3">
				<div class="min-w-0">
					<p class="truncate text-base font-medium text-ink-gray-8">
						{{ nombreCaptura(p) }}
					</p>
					<p class="text-sm text-ink-gray-5">{{ __("Guardada en el celular") }}</p>
				</div>
				<Badge theme="gray" :label="__('Sin enviar')" />
			</li>
			<li v-for="c in capturas" :key="c.name" class="flex items-center justify-between gap-3 py-3">
				<div class="min-w-0">
					<p class="truncate text-base font-medium text-ink-gray-8">
						{{ c.razon_social_emisor || c.rnc_emisor || c.name }}
					</p>
					<p class="text-sm text-ink-gray-5 tabular-nums">
						{{ c.encf || "—" }} · {{ c.monto_total ? formatoMoneda(c.monto_total) : "" }}
					</p>
				</div>
				<Badge :theme="TEMAS[c.estado] || 'gray'" :label="__(c.estado)" />
			</li>
		</ul>
		<p v-if="!cargando && !capturas.length && !pendientes.length" class="py-8 text-center text-ink-gray-5">
			{{ __("Todavía no ha enviado facturas.") }}
		</p>
	</div>
</template>

<script setup>
import { onMounted, ref } from "vue"
import { Alert, Badge, Button, PageHeader, PageHeaderTitle } from "frappe-ui"

import { actualizarPendientes, api, nombreCaptura, pendientes } from "@/captura"
import { __ } from "@/translation"
import { formatoMoneda } from "@/utils"

const TEMAS = {
	Pendiente: "gray",
	"Requiere revisión": "amber",
	Lista: "blue",
	"Factura creada": "green",
	Duplicada: "gray",
	Descartada: "red",
}

const capturas = ref([])
const cargando = ref(false)
const error = ref(null)

async function cargar() {
	cargando.value = true
	error.value = null
	await actualizarPendientes()
	try {
		capturas.value = await api.get("mis_capturas", { limit: 30 })
	} catch (e) {
		error.value = e.message
	} finally {
		cargando.value = false
	}
}

onMounted(cargar)
</script>
