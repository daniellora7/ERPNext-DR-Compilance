# Cambios

Versiones con [versionado semántico](https://semver.org/lang/es/). La rama `version-16` sigue a Frappe v16; cada versión lleva un tag `vX.Y.Z` desde `main`, que publica la imagen en GHCR.

## Sin publicar

## v0.5.5 (2026-10-29)

Captura de compras, etapa 3 (sin OCR): facturas en papel sin QR.

### Nuevo
- **Facturas en papel sin QR** (Escanear facturas): si la foto no tiene QR, se escriben el proveedor, el NCF, la fecha y el total. El proveedor se busca por nombre o RNC entre los proveedores y en el padrón de la DGII; al elegirlo se precargan su tipo de gasto (606) y la serie de su NCF. El NCF se verifica en la DGII: si está vencido o no es del proveedor, la captura queda en revisión.
- Las capturas con NCF B01, B14 y B15 se convierten en factura de compra.

### Mejoras
- La búsqueda en el padrón RNC por razón social usa un índice (de 5 s a milisegundos).
- Búsqueda por palabras sueltas en el padrón (índice FULLTEXT en la razón social y el nombre comercial): «ochoa ferret» encuentra «FERRETERIA OCHOA S A». Se usa cuando la búsqueda por el inicio del nombre no llena la lista.

## v0.5.4 (2026-10-28)

Captura de compras, etapa 2: facturas electrónicas entregadas impresas o en PDF.

### Nuevo
- **Escanear facturas** (`/rd-compliance/escanear`): pantalla para el celular que se instala en la pantalla de inicio. Lee el QR del e-CF con la cámara o de una foto, o el PDF de la factura; el usuario escribe el ITBIS si no se pudo leer. Sin conexión, las capturas quedan guardadas en el celular y se envían al volver.
- **Captura de compra**: los datos del QR, verificados con la DGII (estado del e-CF) con el certificado de la empresa. Revisa que la factura sea a nombre de la empresa y que no esté repetida. Botones **Verificar en la DGII**, **Crear factura de compra** (borrador) y **Descartar**.
- Del PDF generado por el sistema del proveedor se leen el e-NCF, los RNC, el código de seguridad, el ITBIS y el total.
- Rol **Captura Compras RD** para quien solo escanea (ve solo sus capturas).
- Si después llega el XML del mismo e-CF, se enlaza con la captura y avisa si el total difiere.
- La factura de compra guarda el código de seguridad y la fecha de firma del e-CF.

## v0.5.3 (2026-10-28)

Captura de compras, etapa 1: los e-CF de los proveedores pasan a Factura de Compra en borrador.

### Nuevo
- Módulo **Captura Compras**. El *e-CF recibido* guarda el detalle y los totales del XML (ITBIS por tasa, exento, retenciones).
- Botón **Crear factura de compra** (o automático al recibir, según la *Configuración de captura de compras* de cada empresa): busca o crea el proveedor desde el padrón, toma el artículo del proveedor (código en *Item Supplier*), una *Regla de gasto por proveedor* o el artículo genérico, y pone el ITBIS y las retenciones del XML. La factura queda siempre en borrador; si algo no cuadra, el e-CF queda en «Requiere revisión» con el motivo.
- Notas de crédito E34 como devolución de la factura original. E32, E33 y E46 se registran a mano.
- **Cargar XML** en la lista de e-CF recibidos, para los proveedores que lo envían por correo (mismas validaciones, sin acuse).
- Opción para aprobar comercialmente el e-CF (ACECF) al validar la factura. Al cancelar o borrar la factura, el e-CF queda otra vez sin factura.

## v0.5.2 (2026-10-22)

Revisión con las skills oficiales de Frappe (`frappe/skills`) y sus reglas de Semgrep.

### Seguridad
- El NCF de una factura de venta o POS siempre sale de la secuencia: uno enviado por la API ya no se conserva.
- La utilidad contable de la bonificación solo la ve quien puede crear la bonificación; leer la empresa ya no basta.
- Los métodos que escriben o envían a la DGII (e-CF, anulaciones, aprobaciones, IR-2, regalías, perfil tributario, padrón, tasa) solo aceptan POST, así Frappe exige el token CSRF.

### Mejoras
- La app se llama **RD Compliance**.
- Reservar un NCF ya no bloquea las secuencias de otros tipos ni de otras empresas (índice en *Secuencia NCF*; el patch lo crea en sitios existentes).
- Las extensiones de Gratuity, Leave Encashment y Overtime Slip se combinan con las de Frappe HR (`extend_doctype_class`) en vez de reemplazarlas.
- Textos del Panel RD Compliance traducibles.
- Imagen Docker con Frappe Builder v1.36.0.

### Interno
- Consultas con `frappe.qb` en vez de SQL; `install.py` y otros archivos grandes partidos por responsabilidad.

## v0.5.1 (2026-10-22)

Corrige la 0.5.0, que no se publicó en el registro del Marketplace.

- En un sitio nuevo, la primera empresa de RD no preparaba los formatos de impresión, los componentes de nómina, los feriados ni las formas de pago: Frappe v16 no detecta el país de una empresa al crearla. Los sitios con empresas de RD antes de la 0.5.0 no se ven afectados; si se creó una con la 0.5.0, `bench migrate` completa lo que falte.
- Pruebas de alcance estables en un sitio nuevo.

## v0.5.0 (2026-10-22)

Para Frappe v16.52, ERPNext v16.51 y Frappe HR v16.51 (opcional).

### Alcance por empresa
- La app aplica según el país de cada empresa, no el del sitio. En documentos de empresas de otros países no se ven los campos de RD ni se ofrecen los formatos de impresión de la app.
- A quien solo trabaja con empresas de otros países se le ocultan los módulos de la app (RD Compliance, Nómina RD).
- Sin empresas de RD, la instalación no crea ni cambia registros de ERPNext ni de Frappe HR; lo hace la primera empresa de RD que se cree.

### Fiscal (RD Compliance)
- La configuración fiscal y de e-CF la edita solo el System Manager; contabilidad la ve.
- La empresa muestra su perfil tributario («SRL · Régimen Ordinario»).
- Tipo de sociedad en el perfil (SRL, SA, SAS, EIRL y demás formas de la Ley 479-08), pedido en el asistente.

### Idioma
- Nuevo idioma Español (República Dominicana) con los términos de RD: «RNC / Cédula» en vez de «Tax ID», conduce, feriado, forma de pago, preaviso… Se activa al instalar en el sitio y en los usuarios cuyas empresas son todas de RD.

### Nómina RD (con Frappe HR)
- Se bloquea el recibo con el ISR de Frappe HR en una empresa de RD, para no descontarlo dos veces.
- El subsidio de la SISALRIL se enlaza con la licencia del empleado.
- Frappe HR sigue siendo opcional también para el validador del Marketplace.

## v0.4.0 (2026-10-21)

Para Frappe v16.52, ERPNext v16.51 y Frappe HR v16.51 (opcional). Primera versión para el Marketplace de Frappe.

### Fiscal (RD Compliance)
- Tasa del dólar del Banco Central registrada cada día como tipo de cambio USD → DOP (compra, venta o compra en ventas y venta en compras).
- Recordatorios por correo de los vencimientos: IR-17, 606-609, IT-1 y, con nómina, TSS, IR-3, regalía e IR-13; los lunes, las secuencias NCF en alerta. Apagados por defecto.
- Formato *Cheque RD* del *Payment Entry*, con comprobante de pago, editable en el constructor y con las posiciones del cheque ajustables por banco.
- Consulta del NCF del proveedor en la DGII al guardar la factura de compra (no corresponde al RNC, vencido) y aviso de proveedores no activos en el padrón. Opción para impedir validar con un NCF no válido.
- Proporcionalidad del ITBIS (art. 349): proveedores y compras con ITBIS sujeto a proporcionalidad, columna del 606 y porcentaje no admitido en el resumen del IT-1.
- Anticipos del ISR (art. 314): base anual con los datos del IR-2, cuota mensual, reporte del año y recordatorio.
- Cuadre fiscal del IR-2: ajuste por inflación (anexo D-2) con los multiplicadores de la DGII, depreciación fiscal por categoría del art. 287 (anexos D y D-1) frente a la contable, ajustes del anexo G y liquidación estimada del impuesto. Categoría fiscal en las categorías de activo. Reparaciones de edificaciones por encima del 10% capitalizadas y formato de impresión del cuadre.
- Recordatorio del IR-2, 120 días después del cierre del año fiscal.
- Anexos A-1 (balance general) y B-1 (estado de resultados) del IR-2 por casilla, con la casilla en cada cuenta (asignada en el catálogo DGII). El cuadre toma de ahí el beneficio antes del ISR.
- Perfil tributario por empresa: régimen, tamaño, cierre fiscal, actividades con tratamiento especial, incentivos y situación con el e-CF, con asistente desde la empresa y lista de requisitos con su estado. Los emisores electrónicos venden con la serie E y el IR-2 solo aplica a personas jurídicas del régimen ordinario.

### Marketplace de Frappe
- Compatible con el nuevo registro `frappe/marketplace` y Pilot: dependencias de Frappe y ERPNext y el Panel declarados en el `pyproject.toml` y assets precompilados en cada push a `version-16` y `develop`. La imagen Docker y `bench get-app` siguen igual.
- El código pasa las reglas de Semgrep del registro (consultas con `frappe.qb` o parámetros, tipos en los métodos expuestos), y el CI las corre en cada PR.

### Documentación
- Requisitos del nuevo Marketplace de Frappe (registro `frappe/marketplace` y Pilot) en `docs/marketplace.md` y decisión de desplegar con Dokploy.
- Capturas actualizadas, con la del perfil tributario.

### Nómina RD
- Dependientes adicionales del SFS en la ficha del empleado, con el per cápita y el Fonamat descontados en cada recibo.
- Registro de subsidios de la SISALRIL (enfermedad común, maternidad y lactancia) con el monto estimado y el seguimiento del reembolso.

## v0.3.0 (primera versión)

Para Frappe v16.52, ERPNext v16.51 y Frappe HR v16.51 (opcional).

### Fiscal (RD Compliance)
- Tipos de comprobante B01–B17 y E31–E47 y secuencias NCF sin duplicados, en ventas, compras y POS.
- Validación de RNC y cédula, y padrón RNC de la DGII actualizado cada día.
- Catálogo de cuentas DGII (NIIF PYMES) con plantillas de ITBIS y retenciones (Ley 30-26).
- Formatos de impresión *Factura Fiscal RD* y *Recibo POS RD*, editables en el constructor. Cada empresa puede elegir su formato de factura; las de otros países usan el estándar.
- Las devoluciones creadas desde la factura toman solas la nota de crédito (B04/E34).
- Formatos 606, 607, 608 y 609 con su TXT, y resúmenes del IT-1 y el IR-17.
- Panel de cumplimiento con plazos, montos y secuencias. Respeta la apariencia «Ancho completo» del escritorio.

### e-CF
- XML guiado por los XSD oficiales (E31–E47 y RFCE), firma XMLDSig y servicios de la DGII: token, recepción, RFCE y consultas.
- Contingencia: el envío se reintenta solo, cada vez más espaciado, si la DGII no responde.
- Entrega de los e-CF aceptados al comprador si es receptor electrónico.
- Recepción de e-CF de proveedores (servicios `/fe/...`) con acuse de recibo y aprobación o rechazo comercial.
- Anulación de rangos de e-NCF (ANECF).
- Set de pruebas de la certificación (CerteCF).

### Nómina RD (con Frappe HR)
- AFP, SFS, ISR y aportes del empleador en el recibo, con topes de la TSS y escalas del ISR 2026 y 2027.
- Preaviso, cesantía, regalía (proporcional y de diciembre), vacaciones, bonificación anual y feriados RD.
- Horas extras con los recargos de ley, incluido el nocturno (art. 204).
- La cuenta *Nómina por Pagar* del catálogo DGII queda lista para validar la nómina de Frappe HR.
- Archivos de la TSS (AM, NV, RT), resúmenes IR-3 e IR-13, y planillas DGT-3 y DGT-4 para el SIRLA.
- Volante de pago RD y datos RD del empleado.

### Despliegue
- Respaldo diario automático de la base y los archivos, con limpieza de los viejos.
- Guías de despliegue en Dokploy y de respaldo y restauración.

### Idioma
- Nombres del dock en el idioma del usuario.
- Frappe HR completo en español, con 90 traducciones erradas de su catálogo oficial corregidas.
