"""Íconos PNG de la PWA «Escanear facturas» (erpnext_rd/public/pwa): recibo verificado sobre verde.

Uso (en el contenedor, con Pillow): python generar_iconos_pwa.py apps/erpnext_rd/erpnext_rd/public/pwa
Dibujo en una cuadrícula de 100 x 100; se dibuja 8 veces más grande y se reduce (bordes suaves)."""

import math
import sys

from PIL import Image, ImageDraw

FONDO = (15, 110, 86)  # verde 600
ESCUDO = (159, 225, 203)  # verde agua 100
MARCA = (4, 52, 44)  # verde 900
BLANCO = (255, 255, 255)
MUESTRAS = 8


def arco(cx, cy, r, desde, hasta, pasos=12):
	return [
		(cx + r * math.cos(math.radians(desde + (hasta - desde) * i / pasos)),
		 cy + r * math.sin(math.radians(desde + (hasta - desde) * i / pasos)))
		for i in range(pasos + 1)
	]


def bezier(p0, p1, p2, p3, pasos=24):
	puntos = []
	for i in range(1, pasos + 1):
		t = i / pasos
		u = 1 - t
		puntos.append(tuple(u**3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t**3 * d for a, b, c, d in zip(p0, p1, p2, p3)))
	return puntos


# Recibo: esquinas de arriba redondeadas, el lado derecho se recoge donde va el escudo y abajo es dentado
RECIBO = (
	arco(28, 24, 4, 180, 270)
	+ arco(62, 24, 4, 270, 360)
	+ [(66, 48), (50, 48)]
	+ [(50 - i * 26 / 6, 80 if i % 2 == 0 else 77) for i in range(7)]
)
RENGLONES = [(31, 30, 26), (31, 39, 18), (31, 48, 12)]
ESCUDO_PUNTOS = (
	[(66, 50), (81, 55.5), (81, 66.5)]
	+ bezier((81, 66.5), (81, 73.5), (75.5, 78), (66, 82))
	+ bezier((66, 82), (56.5, 78), (51, 73.5), (51, 66.5))
	+ [(51, 55.5)]
)
CHEQUE = [(59, 66), (63.5, 70.5), (73, 61)]
CENTRO = (52.5, 51)  # centro del dibujo


def icono(lado: int, redondeado: bool, escala: float) -> Image.Image:
	n = lado * MUESTRAS
	k = n / 100

	def P(x, y):
		# Centra el dibujo y lo escala alrededor del centro del ícono
		return ((50 + (x - CENTRO[0]) * escala) * k, (50 + (y - CENTRO[1]) * escala) * k)

	img = Image.new("RGBA", (n, n), (0, 0, 0, 0))
	d = ImageDraw.Draw(img)
	if redondeado:
		d.rounded_rectangle([0, 0, n - 1, n - 1], radius=22 * k, fill=FONDO)
	else:
		d.rectangle([0, 0, n, n], fill=FONDO)

	d.polygon([P(*p) for p in RECIBO], fill=BLANCO)
	for x, y, ancho in RENGLONES:
		(x0, y0), (x1, y1) = P(x, y), P(x + ancho, y + 4)
		d.rounded_rectangle([x0, y0, x1, y1], radius=(y1 - y0) / 2, fill=FONDO)
	d.polygon([P(*p) for p in ESCUDO_PUNTOS], fill=ESCUDO)

	grosor = 5 * escala * k
	puntos = [P(*p) for p in CHEQUE]
	d.line(puntos, fill=MARCA, width=round(grosor), joint="curve")
	for x, y in (puntos[0], puntos[-1]):
		d.ellipse([x - grosor / 2, y - grosor / 2, x + grosor / 2, y + grosor / 2], fill=MARCA)
	return img.resize((lado, lado), Image.LANCZOS)


destino = sys.argv[1]
# «any»: esquinas redondeadas (escritorio, Android sin máscara)
for lado in (192, 512):
	icono(lado, True, 1.0).save(f"{destino}/icono-{lado}.png", optimize=True)
# «maskable» (Android recorta en círculo u otras formas): fondo completo y dibujo dentro de la zona segura
icono(512, False, 0.8).save(f"{destino}/icono-maskable-512.png", optimize=True)
# iPhone: cuadrado sin transparencia (iOS redondea las esquinas)
icono(180, False, 0.92).convert("RGB").save(f"{destino}/icono-180.png", optimize=True)
