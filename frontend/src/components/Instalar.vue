<!-- Instalar la pantalla de escanear en el celular. Android (Chrome) avisa con beforeinstallprompt;
     iOS (Safari) no tiene ese evento, así que se explica cómo agregarla desde el menú Compartir.
     Ya instalada (display-mode: standalone) no se muestra. -->
<template>
	<template v-if="!instalada">
		<Button v-if="aviso" :label="__('Instalar')" icon-left="lucide-download" @click="instalar" />
		<Button v-else-if="ios" :label="__('Instalar')" icon-left="lucide-share" @click="ayuda = true" />
		<Dialog v-model:open="ayuda" :title="__('Instalar en el iPhone')">
			<ol class="list-decimal space-y-2 pl-5 text-p-base text-ink-gray-7">
				<li>{{ __("Toque Compartir en la barra de Safari.") }}</li>
				<li>{{ __("Elija «Agregar a inicio».") }}</li>
				<li>{{ __("Abra «Escanear facturas» desde la pantalla de inicio.") }}</li>
			</ol>
		</Dialog>
	</template>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue"
import { Button, Dialog } from "frappe-ui"

import { __ } from "@/translation"

const instalada = ref(
	window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true,
)
const ios = /iphone|ipad|ipod/i.test(navigator.userAgent)
const aviso = ref(null)
const ayuda = ref(false)

const guardarAviso = (evento) => {
	evento.preventDefault()
	aviso.value = evento
}
const alInstalar = () => {
	instalada.value = true
	aviso.value = null
}

onMounted(() => {
	window.addEventListener("beforeinstallprompt", guardarAviso)
	window.addEventListener("appinstalled", alInstalar)
})
onBeforeUnmount(() => {
	window.removeEventListener("beforeinstallprompt", guardarAviso)
	window.removeEventListener("appinstalled", alInstalar)
})

async function instalar() {
	await aviso.value.prompt()
	aviso.value = null
}
</script>
