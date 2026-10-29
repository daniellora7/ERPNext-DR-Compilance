<!-- Proveedor de la factura sin QR: se busca por nombre o RNC entre los proveedores y en el padrón de la
     DGII. Un RNC o una cédula completos que no aparecen (o sin conexión) se pueden usar igual. -->
<template>
	<Combobox
		v-model="rnc"
		v-model:query="busqueda"
		:options="opciones"
		:filterable="false"
		:loading="buscando"
		:label="__('Proveedor')"
		:placeholder="__('Nombre o RNC')"
		:empty-text="__('Escriba al menos 3 letras del nombre o del RNC.')"
	/>
</template>

<script setup>
import { computed, ref, watch } from "vue"
import { Combobox } from "frappe-ui"

import { api } from "@/captura"
import { __ } from "@/translation"

const rnc = defineModel({ type: String, default: null })
const emit = defineEmits(["elegir"])

const busqueda = ref("")
const encontrados = ref([])
const elegido = ref(null)
const buscando = ref(false)
let pedido = 0
let espera = null

/** El número escrito, si lo escrito es solo un RNC o una cédula (con guiones o espacios). */
const numero = (texto) => (/^[\d\s-]+$/.test(texto || "") ? texto.replace(/\D/g, "") : "")

const lista = computed(() => {
	const filas = [...encontrados.value]
	if (elegido.value && !filas.some((e) => e.rnc === elegido.value.rnc)) filas.unshift(elegido.value)
	return filas
})

const opciones = computed(() => [
	...lista.value.map((e) => ({ label: e.razon_social || e.rnc, value: e.rnc, description: detalle(e) })),
	{
		type: "custom",
		key: "rnc",
		label: __("Usar el RNC {0}", [numero(busqueda.value)]),
		condition: ({ query }) =>
			[9, 11].includes(numero(query).length) && !lista.value.some((e) => e.rnc === numero(query)),
		onClick: ({ query }) => {
			elegido.value = { rnc: numero(query) }
			rnc.value = elegido.value.rnc
		},
	},
])

function detalle(emisor) {
	const partes = [emisor.rnc]
	if (emisor.proveedor) partes.push(__("Proveedor"))
	if (emisor.estado && emisor.estado !== "ACTIVO") partes.push(emisor.estado)
	return partes.join(" · ")
}

watch(busqueda, (texto) => {
	clearTimeout(espera)
	if ((texto || "").trim().length < 3 || texto === elegido.value?.razon_social) return
	espera = setTimeout(() => buscar(texto), 250)
})

watch(rnc, (valor) => {
	elegido.value = valor ? lista.value.find((e) => e.rnc === valor) || { rnc: valor } : null
	emit("elegir", elegido.value)
})

async function buscar(texto) {
	const id = ++pedido
	buscando.value = true
	try {
		const filas = await api.get("buscar_emisor", { texto })
		if (id === pedido) encontrados.value = filas
	} catch {
		// Sin conexión: queda la opción de usar el RNC escrito
		if (id === pedido) encontrados.value = []
	} finally {
		if (id === pedido) buscando.value = false
	}
}
</script>
