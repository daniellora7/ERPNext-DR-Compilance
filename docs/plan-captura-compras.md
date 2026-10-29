# Plan: captura de facturas de compra

Objetivo: registrar las facturas de los proveedores como **Factura de Compra en borrador**, con los datos del 606 llenos, para que el contador solo revise y valide. ERPNext genera el asiento contable al validar.

Módulo nuevo `Captura Compras` en `erpnext_rd` (rama `feature/captura-compras`). Se muestra dentro de RD Compliance (`code_only_modules`).

| Etapa | Fuente | Estado |
|---|---|---|
| 1 | e-CF de proveedor electrónico: XML recibido en `/fe/recepcion` o cargado a mano | ✅ v0.5.3 |
| 2 | e-CF entregado impreso o en PDF: QR, verificación DGII y montos | ✅ v0.5.4 |
| 3 | Papel con NCF serie B: foto + OCR local | **Tentativa** |

## Principios

- Todo en DocTypes. No crear tablas ni pantallas fuera del modelo de Frappe.
- Usar lo que ya trae ERPNext antes de crear algo nuevo:
  - **Purchase Invoice** (borrador): documento final. No crear asientos (*Journal Entry*) directos.
  - **Supplier** (`tax_id`) y **Contribuyente DGII** (padrón) para encontrar o crear el proveedor.
  - **Item Supplier** (`supplier_part_no`) para relacionar el código del artículo del proveedor con un *Item*.
  - **Item Default** (cuenta de gasto, centro de costo). El ITBIS va como cargo *Actual* con el monto del XML (decisión de la implementación: cuadra exacto y no depende de *Item Tax Template*).
  - **Assignment Rule** y **Notification** de Frappe para asignar la revisión al contador. Solo configuración, sin código.
  - **File** para adjuntar el XML, el PDF y las fotos a la factura.
- No tocar Frappe ni ERPNext: hooks, Custom Fields por código y patches en `erpnext_rd`.
- Lógica solo si `ncf.es_empresa_rd`.
- El receptor `/fe/recepcion` responde rápido. La conversión a factura va en segundo plano (`frappe.enqueue`, cola `short`).
- Semgrep del Marketplace: `frappe.qb` / `frappe.get_all`, métodos whitelisted con tipos y `methods=["POST"]`.
- Terceros solo GPL-3, LGPL-3 o MIT.

## Lo que ya existe y se reutiliza

| Pieza | Dónde |
|---|---|
| Receptor e-CF (semilla, certificado, recepción, aprobación) | `ecf/receptor.py` |
| Validación, acuse ARECF y registro *ECF Recibido* | `ecf/recepcion.py` |
| Aprobación comercial ACECF y su envío | `ecf/recepcion.py` (`aprobar`, `enviar_aprobacion`) |
| Enlace *ECF Recibido* ↔ *Purchase Invoice* al validar | `ecf/recepcion.py` (`vincular_factura`) |
| Consulta de estado de un e-CF en la DGII (con token) | `ecf/cliente.py` (`consultar_estado`) |
| Consulta del NCF del proveedor en la DGII (serie B) | `dgii_fiscal/consulta_ncf.py` |
| Campos 606 de la compra (`rd_ncf`, `rd_tipo_comprobante`, `rd_tipo_bienes_servicios`, `rd_codigo_seguridad`, `rd_fecha_firma`, retenciones…) | `campos.py` |
| Padrón RNC | `padron_rnc` |
| Panel frappe-ui en `/rd-compliance` | `frontend/`, `www/rd_compliance.py` |

---

## Etapa 1 — e-CF de proveedor electrónico (XML)

Resultado: cada e-CF que llega por `/fe/recepcion` (o que el usuario sube en XML) crea una Factura de Compra en borrador completa, sin escribir nada a mano.

### 1.1 DocTypes

**ECF Recibido** (existe, se amplía):
- Tabla hija nueva **ECF Recibido Detalle**: número de línea, código del artículo del proveedor, descripción, cantidad, unidad, precio, descuento, monto, indicador de facturación (ITBIS 18 %, 16 %, 0 %, exento), *Item* resuelto y cuenta de gasto resuelta.
- Totales del XML: monto gravado por tasa (I1, I2, I3), monto exento, ITBIS por tasa, ITBIS retenido, ISR retenido, otros impuestos, moneda y tasa de cambio.
- `estado_conversion`: Pendiente, Borrador creado, Requiere revisión, Error, Ignorado.
- `mensajes_conversion` (Small Text): por qué requiere revisión (artículo no encontrado, total no cuadra…).
- `origen`: Recepción electrónica o Carga manual.
- Botones: **Crear factura de compra**, **Reintentar**, **Ignorar**.

**Configuracion Captura Compras** (nuevo, uno por *Company*, nombre = empresa):
- `crear_borrador_automatico` (Check): convertir al recibir.
- `crear_proveedor` (Check): crear el *Supplier* desde el padrón si no existe.
- `grupo_proveedor`, `item_generico` (*Item* de servicio sin inventario para líneas sin artículo), `cuenta_gasto_defecto`, `centro_costo_defecto`.
- `cuenta_itbis`, `cuenta_itbis_retenido`, `cuenta_isr_retenido`: cuentas de los cargos *Actual* con los montos del XML.
- `tolerancia_redondeo` (Currency, por ejemplo RD$1).
- `aprobar_al_validar` (Check): enviar la aprobación comercial (ACECF) al validar la factura.
- Tabla hija **Regla Gasto Proveedor**: proveedor, texto que contiene la descripción (opcional), *Item*, cuenta de gasto, centro de costo, `rd_tipo_bienes_servicios` (tipo 606). La primera regla que coincide gana.

Se usa una Regla solo cuando el código del proveedor no está en **Item Supplier**. Las reglas sirven sobre todo para gastos (luz, teléfono, combustible).

### 1.2 Conversión (`captura_compras/convertir.py`)

1. Leer el XML guardado (no volver a pedirlo) y llenar la tabla de detalle y los totales.
2. Proveedor: `Supplier.tax_id = RNCEmisor` → si no existe y `crear_proveedor`, crearlo con el nombre del padrón y el tipo de identificación.
3. Cada línea → *Item*:
   1. *Item Supplier* del proveedor con `supplier_part_no` = código del proveedor;
   2. *Regla Gasto Proveedor*;
   3. `item_generico` + `cuenta_gasto_defecto` y marcar **Requiere revisión**.
4. ITBIS y retenciones del XML como cargos *Actual* (si los precios incluyen ITBIS, `IndicadorMontoGravado` = 1, se quita de cada línea).
5. Tipo de documento:

   | e-CF | Factura de Compra |
   |---|---|
   | E31 crédito fiscal, E44 régimen especial, E45 gubernamental | Normal |
   | E33 nota de débito | No se convierte: la factura de compra no tiene nota de débito (a mano) |
   | E34 nota de crédito | `is_return` con `return_against` (buscada por `rd_ncf` = NCF modificado) y `rd_ncf_modificado` |
   | E32 consumo, E46 exportación | No se convierten: el tipo no aplica a compras (a mano) |

6. Encabezado: `supplier`, `company`, `bill_no` y `rd_ncf` = e-NCF, `bill_date` = fecha de emisión, `rd_tipo_comprobante`, `rd_codigo_seguridad`, `rd_fecha_firma`, `rd_tipo_bienes_servicios` (de la regla o del *Item*), moneda y tasa, retenciones si vienen en el XML.
7. Adjuntar el XML a la factura y enlazar `ECF Recibido.factura_compra`.
8. Comprobar el cuadre: total de la factura = `MontoTotal` ± tolerancia, e ITBIS = `TotalITBIS`. Si no cuadra, el borrador se crea igual con un comentario y el estado **Requiere revisión**.
9. Insertar como **borrador** (`docstatus = 0`). Nunca validar automáticamente.
10. Duplicados: si ya hay una *Purchase Invoice* del proveedor con ese `rd_ncf` (no cancelada), enlazarla y no crear otra.

Disparadores:
- `recepcion._registrar` → `frappe.enqueue("…convertir.desde_ecf", name=…)` si `crear_borrador_automatico` y el estado es Recibido.
- Botón **Crear factura de compra** (método whitelisted POST) para los demás casos.

### 1.3 Al validar o cancelar la Factura de Compra

- `on_submit` (amplía `vincular_factura`): si `aprobar_al_validar`, marcar el *ECF Recibido* como Aprobado y enviar el ACECF.
- `on_cancel`: quitar el enlace en *ECF Recibido* y volver al estado Pendiente.
- Rechazo comercial desde *ECF Recibido*: si hay borrador, borrarlo o marcarlo con un comentario (decidir en la implementación).

### 1.4 Carga manual de XML

Para los proveedores que envían el XML por correo:
- Botón **Cargar XML** en la lista de *ECF Recibido* (y en el panel): pasa por las mismas validaciones (firma, XSD, RNC del comprador, duplicado) sin enviar el ARECF, con `origen = Carga manual`.
- Tentativo: leer los adjuntos `.xml` de una *Email Account* de Frappe (cuenta tipo `facturas@empresa`) con el mismo proceso.

### 1.5 Interfaz

- Sección **Compras recibidas** en el sidebar de RD Compliance: *ECF Recibido*, *Configuracion Captura Compras*.
- Panel RD Compliance: tarjeta con los e-CF recibidos sin factura, los que requieren revisión y las aprobaciones comerciales pendientes. **Pendiente**: va con la PWA en v0.5.4 (mismo build del frontend).
- Configurar (documentado, sin código) una *Assignment Rule* sobre *Purchase Invoice* en borrador para el rol del contador.

### 1.6 Pruebas (`tests/test_captura_compras.py`)

XML de prueba firmados con el certificado de prueba que ya usan `test_ecf_intercambio.py`:
- E31 con artículo conocido (Item Supplier), con regla de gasto y sin nada (genérico + revisión).
- Tasas mixtas 18 %/16 %/exento: ITBIS igual al del XML.
- E34 contra una factura existente → devolución enlazada.
- Duplicado, proveedor nuevo desde el padrón, total que no cuadra.
- Validar → ACECF; cancelar → enlace quitado.
- Empresa no RD: no se hace nada.

---

## Etapa 2 — e-CF impreso o en PDF (QR)

> **Hecho en v0.5.4**, con estos cambios frente al plan:
> - El QR no se lee en el servidor (sin `pyzbar` ni `libzbar0` en la imagen): el celular lo lee de la cámara o de la foto con `qr-scanner`. Del PDF se lee el texto (e-NCF, RNC, código de seguridad, fecha de firma, ITBIS y total), que la DGII exige en la representación impresa.
> - API más simple: `crear` recibe el QR, el archivo (subido antes con `upload_file`) y el ITBIS en una sola llamada, con un id del celular para que los reintentos sin conexión no dupliquen. `adjuntar` no hace falta.
> - Service worker escrito a mano y servido en `/rd-compliance-sw.js` (no `vite-plugin-pwa`). Ver `docs/NOTAS-TECNICAS.md`.
> - Las notas de crédito (E34) impresas se registran a mano: el QR no trae el NCF modificado.
> - Pendiente: probar la instalación en un Android y un iPhone reales con HTTPS.

Resultado: desde el celular se fotografía el QR (o se sube el PDF) y queda una captura verificada con la DGII, con el ITBIS leído del PDF o escrito por el usuario, lista para pasar a factura.

### 2.1 DocType **Captura Compra** (nuevo)

Serie `CAP-.YYYY.-.#####`. Campos:
- `company`, `origen` (QR con cámara, PDF, Foto), `estado` (Pendiente, Requiere revisión, Lista, Factura creada, Duplicada, Descartada).
- Adjuntos: `archivo` (foto o PDF) y `url_timbre` (texto del QR).
- Datos del QR: `rnc_emisor`, `rnc_comprador`, `encf`, `tipo_ecf`, `fecha_emision`, `monto_total`, `fecha_firma`, `codigo_seguridad`.
- Verificación: `estado_dgii` (Sin verificar, Aceptado, Aceptado condicional, Rechazado, No encontrado), `verificado_en`.
- Montos: `monto_gravado`, `total_itbis`, `monto_exento`, `fuente_montos` (XML, texto del PDF, Manual).
- Clasificación: `proveedor`, `rd_tipo_bienes_servicios`, `item` o cuenta de gasto (sugeridos por *Regla Gasto Proveedor*).
- Enlaces: `ecf_recibido` (si después llega el XML), `factura_compra`.
- `observaciones`.

Permisos: rol nuevo **Captura Compras RD** (crear y leer lo propio, para empleados que solo escanean); *Accounts User* y *Accounts Manager* (todo).

### 2.2 Proceso (`captura_compras/qr.py`)

1. **Leer el QR**: en el celular, con [`qr-scanner`](https://github.com/nimiq/qr-scanner) (MIT). En el servidor, como respaldo para PDF o foto, con `pyzbar` (MIT) + `libzbar0` (LGPL) en la imagen Docker.
2. **Interpretar la URL**: `ecf.dgii.gov.do/…/ConsultaTimbre` (completa) o `fc.dgii.gov.do/…/ConsultaTimbreFC` (consumo < RD$250,000: solo emisor, e-NCF, total y código). Rechazar cualquier otro dominio.
3. **Validar**:
   - `rnc_comprador` = RNC de una *Company* (si no, la factura no es de la empresa y no sirve para el 606);
   - RNC con dígito verificador;
   - formato del e-NCF;
   - duplicado contra *Captura Compra*, *ECF Recibido* y *Purchase Invoice* (`rd_ncf`).
4. **Verificar con la DGII**: `cliente.consultar_estado(encf, rnc_comprador, codigo_seguridad)` con el *Emisor ECF* de la empresa. Si la empresa no es emisora, guardar la URL del timbre como enlace para que el usuario la abra. No hacer *scraping* de la página.
5. **Montos**:
   - PDF con texto (generado por el sistema del proveedor): leer el texto con `pdfminer.six` (MIT) y buscar ITBIS, subtotal y total con reglas. El total debe ser igual al del QR.
   - Si no hay texto o no cuadra: el usuario escribe el ITBIS en el celular. Se sugiere `total × 18/118` solo como ayuda, marcada como sugerencia.
6. **Proveedor y clasificación**: igual que en la Etapa 1 (padrón, *Regla Gasto Proveedor*).
7. **Crear la Factura de Compra en borrador** con el mismo `convertir.py` de la Etapa 1 (una línea con el *Item* o la cuenta de la regla), adjuntando la foto o el PDF.
8. Si después llega el XML del mismo e-NCF por `/fe/recepcion`: enlazar *Captura Compra* ↔ *ECF Recibido* y avisar si los montos difieren. El XML manda.

### 2.3 Pantalla para escanear desde el celular (PWA)

Ruta nueva en el frontend existente: `/rd-compliance/escanear`, con frappe-ui y tokens CSS (claro y oscuro).

**Instalable en la pantalla de inicio:**
- `manifest.webmanifest`: nombre «Escanear facturas», `start_url: /rd-compliance/escanear`, `scope: /rd-compliance/`, `display: standalone`, íconos 192 y 512 (variantes del ícono de RD Compliance) y `theme_color` según el token de superficie.
- *Service worker* con `vite-plugin-pwa` (MIT). Debe servirse desde `/rd-compliance/` para controlar ese alcance (o con la cabecera `Service-Worker-Allowed`). Seguir cómo lo resuelve la PWA de Frappe HR (`/hrms`) antes de decidir.
- Android (Chrome): botón **Instalar** con el evento `beforeinstallprompt`.
- iOS (Safari): instrucciones en pantalla («Compartir → Agregar a inicio»), porque iOS no tiene el evento.
- Requiere **HTTPS** (en `localhost` funciona sin él).

**Flujo en la pantalla:**
1. Elegir empresa (si el usuario tiene varias).
2. **Escanear QR** (vista de la cámara con `qr-scanner`) o **Tomar foto / Subir PDF** (`<input type="file" accept="image/*,application/pdf" capture="environment">`).
3. Ver los datos leídos, el estado de la DGII y, si hace falta, escribir el ITBIS y elegir el tipo de gasto.
4. **Enviar** → *Captura Compra* creada → mensaje con el estado.
5. Lista **Mis capturas** con su estado.

**Sin conexión** (por los apagones): guardar las capturas en IndexedDB y enviarlas al volver la conexión. Comprimir las fotos en el celular (máximo 2000 px, JPEG) antes de enviarlas.

**API** (whitelisted, POST, con tipos, en `captura_compras/api.py`):
- `crear_desde_qr(company: str, url_timbre: str) -> dict`
- `adjuntar(name: str)` (el archivo va por `upload_file` de Frappe, ligado al documento)
- `completar(name: str, total_itbis: float, rd_tipo_bienes_servicios: str | None = None) -> dict`
- `mis_capturas(limit: int = 20) -> list`

**En el escritorio**: lista de *Captura Compra* con filtros por estado y el botón **Crear factura de compra**. El sidebar de RD Compliance agrega **Escanear facturas** (abre la PWA) y **Capturas**.

### 2.4 Pruebas

- URLs reales de QR (completa y FC), dominios falsos, parámetros mal codificados.
- RNC del comprador ajeno, duplicados contra los tres DocTypes.
- Consulta DGII simulada (Aceptado, Rechazado, sin servicio).
- PDF con texto: ITBIS leído y cuadre con el total del QR.
- Captura → Factura de Compra en borrador con la foto adjunta; llegada posterior del XML → enlace.
- Frontend: probar la instalación en Android y en iOS reales, y el modo sin conexión.

---

## Etapa 3 — Papel con NCF serie B

**Decisión (2026-10-28): sin OCR.** Las facturas en papel serán entre el 5 % y el 15 % de las compras, y menos del 5 % del monto, y bajan a medida que los proveedores pasan a e-CF. El OCR solo ahorraría escribir unos 5 datos por factura, falla con papel térmico y Tesseract (Apache-2.0) no está en la lista de licencias.

**Hecho en su lugar (versión mínima):** si la foto no tiene QR, el celular pide los datos y ayuda a llenarlos:
- Proveedor por nombre o RNC (`api.buscar_emisor`): primero los proveedores registrados y luego el padrón de la DGII (por el inicio de la razón social, con índice). Un RNC o una cédula completos que no aparecen se pueden usar igual.
- Al elegirlo (`api.emisor`): estado en el padrón y, si ya es proveedor, el tipo de gasto (606) y la serie de su última factura de compra.
- NCF, fecha y total escritos a mano; el ITBIS sugiere el 18 % del total.
- El NCF se verifica en segundo plano con la consulta pública de NCF (`qr.verificar_ncf`): «Válido», «Vencido» o «No corresponde al RNC». Con los dos últimos la captura queda en revisión y no se convierte.
- Se convierten B01, B14 y B15 (además de E31, E44 y E45).

Volver a evaluar el OCR si las capturas «foto sin QR» pasan del 15 % o de unas 50 al mes.

Idea original (descartada por ahora):
- La misma *Captura Compra* con `origen = Foto` y sin QR.
- OCR local con **Tesseract** (sin IA generativa y sin enviar datos fuera del servidor). **Licencia Apache-2.0**: no está en la lista permitida (GPL-3, LGPL-3, MIT). Decidir antes de empezar si se acepta como dependencia instalada sin copiar código, o buscar otra opción.
- Reglas RD sobre el texto: RNC (9 dígitos con verificador) o cédula (11), NCF `B` + 10 dígitos, ITBIS y total junto a sus palabras, subtotal + ITBIS = total.
- DocType **Plantilla Lectura Proveedor** (expresiones por campo para cada proveedor frecuente), con la idea de `invoice2data` (MIT).
- Validar el NCF con la consulta que ya existe (`dgii_fiscal/consulta_ncf.py`).
- Campo `texto_ocr` y confianza por campo. Siempre **Requiere revisión**.
- Referencia de código: [`vampiiluk/invoice_parser`](https://github.com/vampiiluk/invoice_parser) (MIT, v16) y [`Monogramm/erpnext_ocr`](https://github.com/Monogramm/erpnext_ocr) (MIT).

---

## Orden de trabajo

| Paso | Contenido | Versión |
|---|---|---|
| 1 | Etapa 1: DocTypes, `convertir.py`, hooks, carga manual, panel, pruebas | `v0.5.3` |
| 2 | Etapa 2 backend: *Captura Compra*, QR, verificación DGII, PDF con texto, pruebas | `v0.5.4` |
| 3 | Etapa 2 PWA: `/rd-compliance/escanear`, manifest, service worker, sin conexión, prueba en Android e iOS | `v0.5.4` |
| 4 | Etapa 3 mínima: datos escritos a mano con búsqueda del proveedor y consulta de NCF, sin OCR | — |

Cada paso con commit, CI verde (ruff, tests y Semgrep) y actualización de `docs/NOTAS-TECNICAS.md`, `docs/PLAN.md` y `locale/es.po`.

## Pendiente del usuario

- Para recibir XML en producción: certificado `.p12`, alta como emisor y receptor electrónico, y registrar en la DGII las URLs `/fe/...` del dominio con HTTPS (Fase 4).
- Para la PWA en el celular: dominio con HTTPS.
- Facturas reales de proveedores (XML y PDF) para probar, sin crear documentos en Dynamics Plastics sin permiso.
