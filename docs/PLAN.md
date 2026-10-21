# Plan: ERPNext v16.51 + HRMS + localización República Dominicana, desplegado en Dokploy

## Contexto
El usuario quiere un ERPNext propio, versionado en GitHub y desplegado en Dokploy, con:
- ERPNext v16.51.1 (frappe v16.52.0, HRMS v16.51.0) + Frappe HR (HRMS) para RH y nómina.
- Una app propia de localización RD: NCF / e-CF emitidos **directamente** ante la DGII, reportes 606/607/608/IT-1, validación RNC/Cédula, nómina RD (TSS/AFP/SFS/ISR/INFOTEP/regalía).
- Base para seguir agregando funcionalidades después.

Proyecto en `D:\Code Projects 2\ERPNext`. Git 2.56 y Docker 29.8 instalados.

**Una sola instancia, una sola base de datos:** un único sitio Frappe (p. ej. `erp.tudominio.com`) = una única base MariaDB 11.x. ERPNext, HRMS y `erpnext_rd` se instalan los tres en ese mismo sitio (`bench --site <sitio> install-app ...`), así que comparten tablas, usuarios, permisos, compañías, empleados, clientes y contabilidad. Si hay varias empresas, se manejan como varias *Company* dentro del mismo sitio. MariaDB se usa porque es la base de datos oficial y probada de ERPNext/HRMS.

**Principio clave:** no hacer fork de ERPNext/Frappe. Toda la personalización vive en una app propia (`erpnext_rd`) instalada sobre ERPNext/HRMS oficiales. Así puedes actualizar a 16.51, 16.52… sin conflictos de merge.

## Estado actual (actualizado 2026-10-18)

| Fase | Estado |
|---|---|
| 0 — Entorno y descarga | ✅ Hecho. Versiones verificadas: frappe v16.52.0, erpnext v16.51.1, hrms v16.51.0 (actualizadas el 2026-10-16). Se usa Docker local (imagen propia) en lugar de devcontainer. |
| 1 — Despliegue | 🟡 Repo público en GitHub (https://github.com/daniellora7/ERPNext-DR-Compilance) con CI en cada PR (`ci.yml`: ruff + tests con la misma imagen y compose, también en un sitio sin HRMS, vía `deploy/ci/run-tests.sh`) y `build-image.yml` (imagen a GHCR en `main` y tags `v*`). Local: `deploy/Containerfile` + `deploy/compose.yaml`, sitio `erp.localhost` en http://localhost:8090 con las 4 apps en una sola base MariaDB. Respaldo diario automático (servicio `backup`, `docs/RESPALDOS.md`, restauración probada) y guía de despliegue (`docs/DOKPLOY.md`). **Pendiente (usuario):** servidor Dokploy y dominio. |
| 2 — Base fiscal DGII | 🟡 Implementado en `feature/dgii-fiscal`: tipos de comprobante (21), Secuencia NCF con bloqueo, NCF en ventas/compras, RNC/Cédula, padrón (793 985 registros), 16 tests. NCF en POS (modo Sales Invoice y POS Invoice, tipo por defecto en Perfil de POS), formatos de impresión *Factura Fiscal RD* y *Recibo POS RD* (80 mm) con QR e-CF listo para la Fase 4, 19 tests. **Catálogo de cuentas DGII** (214 cuentas, NIIF PYMES; activos por categoría de depreciación fiscal; gastos agrupados por tipo 606, ingresos por tipo 607; cuentas de impuestos con concepto fiscal; plantillas ITBIS 18%/16%, propina y retenciones; retenciones de ISR a personas físicas al 15% y servicios técnicos al 3% según la Ley 30-26, vigente desde el 1/7/2026), aplicado por empresa solo a las de país República Dominicana sin movimientos, 28 tests. Prueba de punta a punta de un mes completo (`test_punta_a_punta.py`: ventas, nota de crédito, anulada, compras con retenciones, exterior y nómina; formatos y declaraciones cuadran con el mayor y sin avisos). **Pendiente (usuario):** revisar con facturas reales. |
| 3 — Reportes DGII | 🟡 Script Reports *Formato 606/607/608/609 DGII* con descarga del TXT oficial (`DGII_F_<formato>_<RNC>_<AAAAMM>.TXT`), columnas según los instructivos vigentes de la DGII, retenciones informadas en el mes de pago, facturas de consumo < RD$250,000 fuera del TXT con su resumen para la OFV, columna de observaciones. Toda la lógica fiscal (NCF, validación RNC, reportes) aplica solo a empresas con país República Dominicana. Reportes de apoyo *Resumen IT-1 DGII* (ingresos gravados por tasa, exentos, exportaciones, formas de cobro, liquidación del ITBIS con saldo a favor, retenciones por terceros y Norma 08-04, ITBIS retenido a terceros, vencimiento día 20) y *Resumen IR-17 DGII* (ISR retenido a terceros por tipo de retención y pagos al exterior, en el mes de pago, vencimiento día 10), calculados con los mismos registros del 606/607/609. 45 tests. **Pendiente:** pre-validar los TXT con la herramienta de la DGII usando datos reales. |
| UI — Módulo RD Compliance | ✅ Un solo ícono **RD Compliance** en el dock de Frappe v16 (ícono duotono propio con animación) y un sidebar con secciones desplegables: *DGII Fiscal* (Secuencia NCF, Tipo Comprobante Fiscal, Configuración DGII), *DGII Reportes* (606–609) y *Padrón RNC* (Contribuyentes DGII). Los módulos internos se muestran dentro de RD Compliance (`code_only_modules`). e-CF y Nómina RD se agregarán como secciones nuevas de este mismo menú. **Estándar visual frappe-ui** (2026-10-14): el HTML propio de los reportes usa los tokens de color del escritorio v16 (modo oscuro incluido). **Panel RD Compliance** (2026-10-14, piloto): pantalla en `/rd-compliance` hecha con frappe-ui 1.0.2 (`frontend/`) con plazos y montos del 606–609, IT-1 e IR-17 del mes, secuencias NCF por agotarse/vencer/agotadas, registros con observaciones y estado del padrón; se abre dentro del escritorio (página `panel-cumplimiento` del sidebar) en la misma ventana. Base técnica para el monitor de e-CF y el portal de empleados. |
| 4 — e-CF | 🟡 Todo lo que no requiere certificado real: XSD oficiales, XML guiado por el XSD (E31-E47, RFCE), firma XMLDSig verificada con xmlsec1, cliente de los servicios DGII (semilla/token, recepción, RFCE, consultas, anulación, aprobación comercial, directorio), *Emisor ECF* por empresa y registro *Envio ECF*. Contingencia con reenvío automático, entrega al comprador con su acuse, servicios públicos del receptor (`/fe/...`) con *ECF Recibido*, acuse (ARECF) y aprobación comercial (ACECF), anulación de rangos (*Anulacion ENCF*, ANECF) y *Set Pruebas ECF* para CerteCF (2026-10-16). **Pendiente (usuario):** certificado .p12 y alta como emisor; pruebas en TesteCF, set de CerteCF y registrar la URL del receptor en la DGII. |
| Cumplimiento (2026-10-16 al 18) | ✅ Tasa del dólar del BCRD, recordatorios por correo, formato *Cheque RD*, anticipos del ISR, proporcionalidad del ITBIS, NCF del proveedor en la DGII, dependientes adicionales del SFS, subsidios de la SISALRIL, cuadre fiscal del IR-2 (D, D-1, D-2, G, liquidación, formato impreso, recordatorio) y anexos A-1 y B-1. Fusionado en `develop` (PR #10 a #16). Cubre a la **persona jurídica del régimen ordinario**; los demás regímenes e impuestos especiales van en la Fase 8. |
| 8 — Perfil tributario | 🟡 8.1 hecha (`feature/perfil-tributario`): perfil por empresa, asistente, requisitos con su estado, serie E para emisores e IR-2 solo para el régimen ordinario. Siguen 8.2 a 8.9. |
| 5 — Nómina RD | 🟡 Base lista: *Configuración Nómina RD* (tasas y topes TSS 2026, salario mínimo cotizable RD$23,223, escalas anuales ISR 2026 y 2027 por año, todo editable), cálculos de AFP/SFS/SRL/INFOTEP con topes, ISR de asalariados (renta anualizada menos TSS) y regalía pascual. En el recibo de Frappe HR se calculan solos (hook `apply_regional_deductions` + `validate`) los componentes *AFP*, *SFS*, *ISR* y los aportes del empleador, con cuentas del catálogo DGII. Devengos marcan *Cotiza a la TSS*; el ISR usa *Is Tax Applicable* de HR. Nóminas quincenales/semanales prorratean el equivalente mensual. Hechos además: datos RD del empleado, prestaciones (preaviso, cesantía, regalía proporcional), vacaciones, feriados, regalía de diciembre, escalas ISR por año (2027 de la Ley 30-26), archivo de autodeterminación TSS (AM), resúmenes IR-3 e IR-13. Archivo de novedades TSS (NV) y rectificativa IR-3 (RT). Horas extras con recargo nocturno (art. 204). **Pendiente (usuario):** validar los TXT con el validador de la TSS y una nómina real. |

Decisión: el usuario quiere probar todo en Docker local antes de configurar GitHub y Dokploy.

### Próximos pasos (en orden sugerido)
1. **Prueba de punta a punta del usuario** en Dynamics Plastics: facturas reales de venta/compra, NCF, retenciones, y descargar los TXT 606/607 de un mes.
2. **Pre-validar los TXT** con la herramienta de pre-validación de la DGII y corregir lo que marque.
3. **Cierre de Fase 3:** ~~apoyo IT-1 e IR-17~~ (hecho); falta solo la pre-validación con datos reales → tag `v0.3.0`.
4. **Fase 1 pendiente:** desplegar en el servidor Dokploy del usuario siguiendo `docs/DOKPLOY.md` (compose, respaldos y CI ya están).
5. **Fase 4 — e-CF:** el código está completo; falta el certificado `.p12`, el alta como emisor electrónico, las pruebas en TesteCF, el set de CerteCF (*Set Pruebas ECF*) y registrar la URL del sitio como receptor en la DGII.
6. **Fase 5 — Nómina RD (en Frappe HR):** ✅ preaviso, cesantía, regalía proporcional, vacaciones y feriados; ✅ regalía de diciembre en la nómina; ✅ escala ISR 2027 (Ley 30-26); ✅ resumen IR-13. ✅ novedades TSS (NV) y rectificativa (RT). ✅ bonificación anual (art. 223). ✅ horas extras y feriados (arts. 203-205, con el recargo nocturno del art. 204). ✅ volante de pago RD. ✅ planillas DGT-3 / DGT-4 (SIRLA). ✅ datos RD del empleado. ✅ archivo de autodeterminación TSS (AM). ✅ resumen IR-3.
7. ~~Logo de la app~~ y ~~formato de impresión por empresa para las que no son de RD~~ (hechos, 2026-10-16).
9. ✅ `v0.3.0` (primera versión) y `v0.4.0` (2026-10-21, primera para el Marketplace) publicadas: tag desde `main`, `version-16` al día e imagen en GHCR. Falta registrar la app en el Marketplace con `docs/marketplace.md`.
8. **Al subir de versión Frappe HR:** si su `hrms/locale/es.po` ya trae el español completo (en Crowdin quedó al 100 % y aprobado en octubre de 2026; falta que el bot lo sincronice al repo y salga en una versión), borrar de `erpnext_rd/locale/es.po` el bloque «Frappe HR: textos que faltan en su catálogo oficial». Si se queda, tapa las traducciones oficiales (la app se carga después) y mezcla términos (p. ej. *Arrear*: «atrasos» oficial, «retroactivo» nuestro). Ajustar `test_frappe_hr_completo_en_espanol` en `tests/test_navegacion.py` a las traducciones oficiales. La traducción de los nombres del dock (`boot.py`) se mantiene hasta que Frappe los pase por `__()`. El bloque anterior, «Frappe HR: correcciones de su catálogo oficial» (90 traducciones erradas: *Shift Type* «Tipo de Cambio», *Slab* «Losa», *Leave* «vacaciones»…), se mantiene: revisar entrada por entrada si el catálogo oficial ya las corrigió y borrar solo esas.

### Mejoras de cumplimiento (análisis del 2026-10-16) ✅
Lo que se podía hacer sin depender del usuario (fusionado en `develop`, PR #10 a #16):
1. ✅ `feature/tasa-recordatorios-cheque`: tasa del dólar del BCRD, recordatorios por correo de vencimientos y formato *Cheque RD*.
2. ✅ `feature/isr-itbis-ncf-proveedor`: anticipos del ISR (art. 314), proporcionalidad del ITBIS (art. 349) y aviso de NCF/RNC del proveedor no válido (la consulta de NCF de la DGII no tiene captcha). Pendiente: tres cuotas de las pequeñas empresas (Ley 30-26, desde 2027) cuando la DGII publique los criterios.
3. ✅ `feature/sfs-dependientes-subsidios`: dependientes adicionales del SFS (per cápita + Fonamat en el recibo) y registro de subsidios de la SISALRIL (enfermedad común, maternidad, lactancia) con monto estimado y reembolso.
4. ✅ `feature/ir2-apoyo`: *Cuadre Fiscal IR2* con ajuste por inflación (D-2, multiplicadores de la DGII por cierre), depreciación fiscal por categoría (art. 287, anexos D y D-1) frente a la contable, ajustes del anexo G y liquidación. `feature/ir2-recordatorio-formato`: recordatorio del IR-2, reparaciones de edificaciones por encima del 10% y formato imprimible del cuadre. `feature/ir2-anexos-a1-b1`: anexos A-1 y B-1 por casilla desde el catálogo de cuentas. Pendiente: activos de la Ley 392-07 (solo si aplica).

Dependen del usuario: e-CF en producción, pre-validar TXT con datos reales, extractos de los bancos (ejemplos) y cuadre de la factura TSS (ejemplo); ver «Puesta en producción». Los regímenes e impuestos especiales (ISC, DIOR, zonas francas, RST…) pasan a la Fase 8.

### Puesta en producción: lista de verificación
Lo que falta para usar la app con una empresa real. Cada prueba se hace con datos reales de la empresa y se da por buena solo con el resultado indicado.

| Prueba | Qué hace falta del usuario | Se da por buena cuando |
|---|---|---|
| Empresa y catálogo | RNC, cierre fiscal y, cuando exista, el perfil tributario (Fase 8) | El RNC valida, el catálogo DGII está aplicado y el año fiscal de ERPNext coincide con el cierre |
| Secuencias NCF | Rangos autorizados por la DGII (Oficina Virtual) | Cada tipo que se usa tiene secuencia vigente y el panel no avisa |
| Un mes completo | Facturas reales de venta, compra, notas de crédito, anulaciones, retenciones y pagos al exterior | El 606, 607, 608 y 609 cuadran con el mayor y no tienen observaciones |
| TXT de la DGII | Pre-validador de la DGII | Los cuatro TXT pasan el pre-validador sin errores |
| IT-1 e IR-17 | Borrador de la declaración en la Oficina Virtual | Los resúmenes coinciden casilla por casilla con lo que la OFV precarga o con lo que declara el contador |
| e-CF | Certificado .p12, alta como emisor electrónico | Set de TesteCF aceptado, set de CerteCF aprobado, URL del receptor registrada y primer e-CF real aceptado |
| Nómina y TSS | Una nómina real y la factura de la TSS del mes | El archivo AM (y NV si hubo novedades) carga en el SUIR Plus y la factura de la TSS coincide con la autodeterminación |
| IR-3 e IR-13 | Declaración del mes y del año | Coinciden con el resumen de la app |
| SIRLA | Usuario del SIRLA | DGT-3 y DGT-4 cargan sin errores |
| IR-2 | Contador, multiplicador del cierre confirmado (2025: 1.0495), categoría fiscal en las categorías de activo | El contador revisa el cuadre y las casillas de los anexos A-1 y B-1 de un cierre real |
| Usuarios y permisos | Lista de usuarios y sus funciones | Cada usuario ve solo lo que le toca (roles de ERPNext, Frappe HR y Accounts) |
| Servidor | Servidor Dokploy y dominio | Sitio con HTTPS, respaldo diario funcionando y una restauración probada en el servidor (`docs/RESPALDOS.md`) |

## Estructura del repo (GitHub, público: `daniellora7/ERPNext-DR-Compilance`)
```
ERPNext-DR-Compilance/          # la raíz del repo ES la app (así la instala bench get-app / Frappe Cloud)
├── pyproject.toml              # paquete erpnext_rd
├── package.json                # `bench build` compila frontend/ con su script build
├── frontend/                   # Panel RD Compliance (Vue 3 + frappe-ui) en /rd-compliance
├── erpnext_rd/
│   ├── dgii_fiscal/            # módulo: NCF, tipos de comprobante, campos fiscales
│   ├── ecf/                    # módulo: e-CF (XML, firma, envío, consulta, recepción)
│   ├── dgii_reportes/          # módulo: 606, 607, 608, 609, IT-1 helper, IR-17
│   ├── padron_rnc/             # módulo: padrón RNC/Cédula
│   ├── nomina_rd/              # módulo: TSS, ISR, INFOTEP, regalía, IR-3, archivo SUIR (solo con HRMS)
│   ├── rd_compliance/          # menú único RD Compliance
│   └── hooks.py
├── deploy/                     # imagen Docker, compose (local / Dokploy) y CI
├── docs/
├── .github/workflows/          # ci.yml (lint + tests), build-image.yml (GHCR)
├── LICENSE                     # GPL-3.0
└── README.md
```
Ramas: `main` (producción), `develop` (staging), ramas `feature/*` con PR. Versionado semántico con tags `v1.0.0` → cada tag publica imagen `ghcr.io/<usuario>/erpnext-rd:<tag>`.

## Fase 0 — Entorno local y descarga
1. Verificar que el tag `v16.5.x` existe en `frappe/frappe`, `frappe/erpnext` y `frappe/hrms` (HRMS puede tener su propio número; usar el tag de la rama `version-16` compatible). Fijar versiones exactas en `deploy/apps.json`.
2. `git init` del repo, crear repo privado en GitHub.
3. Clonar `frappe/frappe_docker` como referencia (no dentro del repo) y copiar su `.devcontainer` para desarrollar en Docker/WSL2 en Windows.
4. Dentro del devcontainer: `bench init --frappe-branch <tag v16.5>`, `bench get-app erpnext`, `bench get-app hrms`, `bench new-app erpnext_rd`, `bench new-site dev.localhost`, instalar las 3 apps.

## Fase 1 — Despliegue mínimo en Dokploy (antes de programar la localización)
1. `build-image.yml`: usa el Containerfile *layered* de frappe_docker (`images/layered/Containerfile`) con `APPS_JSON_BASE64` generado de `deploy/apps.json`; la app propia se referencia por URL del repo con token (`secrets.GH_PAT`). Publica en GHCR.
2. `deploy/compose.yaml` basado en `pwd.yml` de frappe_docker: servicios `backend`, `frontend` (nginx), `websocket`, `queue-short`, `queue-long`, `scheduler`, `configurator`, `create-site`, `db` (MariaDB 11.x), `redis-cache`, `redis-queue`; volúmenes `sites`, `db-data`, `logs`.
3. En Dokploy: proyecto → servicio **Docker Compose** desde el repo GitHub, ruta `deploy/compose.yaml`, variables (`ERPNEXT_IMAGE_TAG`, `DB_ROOT_PASSWORD`, `SITE_NAME`, `ADMIN_PASSWORD`), dominio en el servicio `frontend` puerto 8080 con HTTPS (Traefik de Dokploy).
4. Backups: `bench backup --with-files` vía cron de Dokploy/scheduler + volumen MariaDB; documentar restauración.
5. Flujo de actualización: nuevo tag → imagen → cambiar `ERPNEXT_IMAGE_TAG` → redeploy → `bench --site all migrate` (servicio one-shot `migrate` en compose).

**Decisión (2026-10-20): Dokploy con la imagen Docker, no [Pilot](https://github.com/frappe/pilot).** Pilot es el gestor de benches que Frappe está construyendo: instala el bench directo en el sistema (`uv`, Node, `systemd`/`supervisor`), configura nginx en el servidor y saca los certificados de Let's Encrypt. Choca con Traefik de Dokploy por los puertos 80/443 y dentro de un contenedor pierde casi todo lo que ofrece; además no tiene ninguna versión publicada. El servidor del usuario va a alojar más servicios que Frappe, así que se sigue con Dokploy y la imagen `erpnext-rd` (frappe_docker), detrás de Traefik. Pilot solo tendría sentido en un servidor dedicado a Frappe; revisarlo cuando tenga una versión estable. Lo que sí se adopta de Pilot es la compatibilidad: la app debe instalarse con su `get-app` para el Marketplace (Fase 7, `docs/marketplace.md`).

## Fase 2 — Base fiscal DGII (módulo `dgii_fiscal` + `padron_rnc`)
- Custom fields (vía fixtures) en Company, Customer, Supplier: tipo de identificación (RNC/Cédula/Pasaporte), RNC.
- DocType **Tipo Comprobante Fiscal** (B01, B02, B04, B11, B13, B14, B15, B16, B17 y E31, E32, E33, E34, E41, E43, E44, E45, E46, E47).
- DocType **Secuencia NCF** (prefijo, rango autorizado, desde/hasta, vencimiento, próximo número) con bloqueo `SELECT … FOR UPDATE` para no duplicar.
- Hooks `doc_events` en Sales/Purchase Invoice: asignar NCF en `on_submit`, validar RNC, NCF modificado en notas de crédito, tipo de ingreso, tipo de gasto (606), ITBIS facturado/retenido, ISR retenido, forma de pago.
- Padrón RNC: DocType **Contribuyente DGII**, job programado que descarga el ZIP del padrón público de la DGII e importa; autocompletar nombre/razón social al escribir RNC; validación de dígito verificador de RNC y Cédula.

## Fase 3 — Reportes DGII (módulo `dgii_reportes`)
Script reports + exportación TXT en el formato oficial:
- **606** (compras), **607** (ventas), **608** (anulados), **609** (pagos al exterior).
- Resumen de apoyo para **IT-1** e **IR-17** (retenciones).
- Validaciones previas (RNC inválido, NCF duplicado, montos negativos) antes de exportar.

## Fase 4 — e-CF directo con DGII (módulo `ecf`)
- DocType **Configuración e-CF**: ambiente (TesteCF / CerteCF / eCF), URLs, certificado `.p12` (archivo privado) + contraseña (campo Password cifrado).
- Generación de XML según XSD oficiales de la DGII por tipo (E31…E47), validación contra XSD con `lxml`.
- Firma XMLDSig (RSA-SHA256) con `signxml`/`cryptography`.
- Autenticación: obtener semilla → firmarla → validar → token Bearer (cacheado en Redis hasta su vencimiento).
- Envío a Recepción, guardar TrackId; job programado de **consulta de estado** (Aceptado / Aceptado condicional / Rechazado) en DocType **Log e-CF**.
- **RFCE** (resumen de facturas de consumo E32 < umbral) y su envío.
- Print format con **código de seguridad** y **QR** con la URL de timbre.
- Endpoints públicos (`@frappe.whitelist(allow_guest=True)` con validación de firma) para **recepción de e-CF** de proveedores y **aprobación comercial**.
- Contingencia: cola de reintentos si la DGII no responde.
- Proceso de certificación DGII: el set de pruebas que exige la DGII se correrá en CerteCF antes de pasar a producción (esto lo gestiona el usuario con la DGII; el código deja herramientas para generarlo).

## Fase 5 — Nómina RD (módulo `nomina_rd`, sobre HRMS)
- **Objetivo: que Frappe HR quede adaptado a la República Dominicana.** Todo lo de nómina y RRHH vive del lado de Frappe HR: entrada *Nómina RD* en su dock (capa del sitio, sin tocar HRMS) con su propio sidebar; ya no es una sección de RD Compliance. ✅ navegación.
- ✅ **Prestaciones**: preaviso (art. 76) y cesantía (art. 80) sobre el *Gratuity* de HRMS (reglas "Preaviso RD" y "Cesantía RD"), tramos editables; la liquidación final de HRMS las incluye.
- ✅ **Regalía proporcional** (art. 220): regla "Regalía RD" del mismo *Gratuity* (salarios ordinarios del año hasta la salida / 12).
- ✅ **Regalía de diciembre** (arts. 219-222): reporte *Regalía pascual* + creación en bloque de los *Gratuity* "Regalía RD" (borrador) pagados en el recibo de diciembre con el componente *Regalía Pascual* (exento de ISR y TSS).
- ✅ **Vacaciones** (arts. 177-182): *Leave Type* "Vacaciones RD", asignación en cada aniversario (14 / 18 días, opcional) y pago al salir con *Leave Encashment* (saldo + proporción del art. 180, salario diario de las prestaciones).
- ✅ **Datos RD del empleado** (*Employee* de ERPNext): tipo de documento (cédula, NSS, pasaporte u otro), cédula revisada (solo avisa), NSS, segundo apellido, AFP y ARS (catálogo *Entidad Seguridad Social RD*), clave de nómina y tipo de ingreso TSS, búsqueda por cédula.
- ✅ **Archivo de autodeterminación TSS (AM)**: reporte *Autodeterminacion TSS* + TXT de ancho fijo (instructivo TSS v6.0) desde los recibos aprobados.
- ✅ **Novedades TSS (NV)**: ingresos, salidas, cambios de salario, vacaciones y licencias del mes, con salario del recibo o estimado; filtro por empleado/tipo porque los envíos se suman.
- ✅ **Rectificativa IR-3 (RT)**: botón del reporte de autodeterminación (después de pagar la TSS).
- ✅ **Resumen IR-3**: lo que liquidará la DGII (escala sobre renta menos AFP/SFS) frente al ISR retenido en los recibos, con fecha límite y aviso de IR-3 en cero.
- ✅ **Resumen IR-13**: suma anual de los IR-3 por empleado o por mes, con fecha límite (15 de marzo, día hábil).
- ✅ **Feriados RD**: *Holiday List* de ERPNext con la librería `holidays` (Ley 139-97), se extiende cada año.
- DocType singleton **Configuración Nómina RD** con tasas y topes editables (AFP empleado/empleador, SFS empleado/empleador, SRL, INFOTEP, topes en salarios mínimos, escala anual ISR) — no se hardcodean porque cambian.
- Salary Components y Salary Structure plantilla; fórmulas que llaman funciones Python de la app para ISR (proyección anual) y topes TSS.
- Regalía pascual (salario 13), vacaciones, cesantía/preaviso (calculadora de prestaciones).
- Exportes: archivo de **autodeterminación TSS/SUIR**, **IR-3** mensual, **IR-13** anual.

## Fase 6 — Funcionalidades futuras
Cada nueva funcionalidad = nuevo módulo en `erpnext_rd` (o nueva app si es independiente), en rama `feature/*`, con PR, CI verde y tag de versión.

## Fase 8 — Perfil tributario por empresa: regímenes e impuestos especiales
Objetivo: que la app sirva a cualquier empresa de RD, no solo a la persona jurídica del régimen ordinario. Cada empresa declara en un **perfil tributario** bajo qué régimen opera, qué impuestos especiales le aplican y qué incentivos tiene; la app activa solo lo que corresponde, pide la configuración que hace falta y no deja operar sin ella cuando es obligatoria.

**Regla de trabajo:** cada rama empieza por leer el texto oficial vigente (Código Tributario y sus reglamentos, Ley 30-26 y sus normas de aplicación, leyes de cada régimen, normas e instructivos de la DGII). Lo que solo aparece en fuentes secundarias no se implementa hasta confirmarlo; las tasas, montos y plazos van en configuración editable, como en el resto de la app.

### 8.1 Perfil tributario (base, primera rama) ✅
- **DocType *Perfil Tributario RD*** (uno por empresa de RD):
  - Tipo de contribuyente: persona jurídica o persona física con negocio.
  - Régimen: ordinario o simplificado (RST).
  - Tamaño según la Ley 488-08 de mipymes, modificada por la Ley 187-17 (micro hasta 10 trabajadores, pequeña de 11 a 50, mediana de 51 a 150, grande más de 150; también por ventas brutas anuales, indexadas cada año por el MICM) y segmento de la DGII si lo asignó.
  - Cierre fiscal (31/3, 30/6, 30/9 o 31/12): crea o revisa el año fiscal de ERPNext.
  - Regímenes especiales e incentivos (tabla): zona franca (Ley 8-90), turismo (Ley 158-01), Proindustria (Ley 392-07), energías renovables (Ley 57-07), cine (Ley 108-10), desarrollo fronterizo (Ley 28-01) u otro; con resolución o certificado, vigencia y qué exenciones otorga (ISR, ITBIS, otros).
  - Actividades con tratamiento especial: ISC (alcohol, tabaco, combustibles, telecomunicaciones, seguros), propina legal, operaciones con partes relacionadas (precios de transferencia / DIOR), exportación, agente de retención designado.
  - Sector regulado (banca, seguros, AFP): fuera del alcance; el perfil lo marca y avisa.
  - Facturación electrónica: fecha desde la que está obligada y estado (no obligada, en certificación, emisor).
- **Asistente:** al crear o abrir una empresa de RD sin perfil, un aviso lleva a un asistente por pasos (diálogo frappe-ui) que lo completa.
- **Requisitos de la empresa:** pantalla con la lista que sale del perfil, cada requisito con su estado (cumplido / falta) y un enlace para resolverlo. Ejemplos: secuencia NCF vigente para cada tipo que usa; año fiscal según el cierre; tasas del ISC y artículos clasificados si vende productos con ISC; B14/E44 para clientes de zona franca; emisor e-CF si está obligada.
- **Exigencia:** lo obligatorio bloquea al validar el documento afectado (p. ej. vender un artículo con ISC sin su tasa); lo que no aplica se oculta (p. ej. el cuadre del IR-2 para una persona física, los anticipos para una microempresa).
- **Obligaciones según el perfil:** el panel de cumplimiento y los recordatorios por correo toman del perfil qué declaraciones tiene la empresa y sus plazos.
- **Arquitectura:** `rd_compliance/perfil.py` con un registro de reglas (condición sobre el perfil → requisito → verificación → enlace) y de obligaciones. Cada módulo especial agrega sus reglas; crecer es sumar reglas, no tocar el núcleo. Sin perfil, la empresa se trata como persona jurídica del régimen ordinario (lo de hoy), así nada se rompe en los sitios existentes.

### 8.2 Impuesto selectivo al consumo (ISC)
- Clasificación ISC en el artículo (alcohol: grados y volumen; tabaco; combustibles; servicios de telecomunicaciones y seguros).
- Tasas ad valorem y montos específicos en configuración editable (la DGII actualiza los específicos de alcohol y tabaco cada trimestre).
- Cálculo en ventas e importaciones con plantillas de impuesto; columnas del ISC en el 606 y 607.
- Resumen de la declaración mensual del ISC (vence el día 20; formulario a confirmar con la DGII) y su recordatorio.

### 8.3 Precios de transferencia (DIOR)
- Marca de parte relacionada en clientes (en proveedores ya existe para el 609), con país y tipo de vinculación.
- Resumen anual de operaciones con relacionados por tipo y contraparte para la DIOR; plazo y umbrales a confirmar.
- Ajuste 1.9 del anexo G del cuadre IR-2 cuando el contribuyente autoimpugna un precio.

### 8.4 Zonas francas y exportadores
- Empresa de zona franca: exenciones según su resolución, compras con los comprobantes que correspondan y ventas al mercado local con su tratamiento.
- Proveedores de zonas francas: clientes marcados como zona franca reciben B14/E44 solos.
- Exportadores: ITBIS de las compras para exportación a compensar o pedir en reembolso, con su soporte.

### 8.5 Impuesto sobre los activos
- Confirmar si sigue vigente y en qué términos tras la Ley 30-26.
- Si aplica: activos imponibles desde el anexo A-1, exentos, liquidación y crédito contra el ISR, en el cuadre del IR-2.

### 8.6 Incentivos en el IR-2
- Desde los incentivos del perfil: exenciones (casilla 3), deducción por inversión de la Ley 392-07 y sus activos (anexo D, sección C), créditos de energías renovables y de cine (casillas 15, 16 y 20).

### 8.7 Régimen simplificado (RST)
- Modalidades (por ingresos o por compras) y límites de la Ley 30-26.
- Su declaración y cuotas, y qué formatos y declaraciones del régimen ordinario no aplican.

### 8.8 Persona física con negocio (IR-1)
- Perfil de persona física: declaración IR-1 (escala de personas físicas) en lugar del IR-2, sus anticipos y la cédula como identificación fiscal.

### 8.9 Sectores regulados
- Banca, seguros y AFP reportan además a sus superintendencias: fuera del alcance. El perfil lo indica y la app avisa qué cubre y qué no.

Orden sugerido: 8.1 (base) → 8.2 → 8.3 → 8.4 → 8.5 → 8.6 → 8.7 → 8.8. Cada una en su rama `feature/*`, con PR contra `develop`, tests y documentación.

## Fase 7 — Publicación en el Marketplace de Frappe (más adelante)
Objetivo: que la app se instale desde el **Marketplace de Frappe** (registro [`frappe/marketplace`](https://github.com/frappe/marketplace), que usan `bench get-app` de Pilot y su panel) y desde Frappe Cloud, como las demás localizaciones (México, Ecuador, Alemania, Kenia). Repo público: https://github.com/daniellora7/ERPNext-DR-Compilance (GPL-3.0). Guía completa en `docs/marketplace.md`.

Lo que exige el nuevo registro (analizado el 2026-10-20) y falta hacer:
- [x] **`pyproject.toml`**: `[tool.bench.frappe-dependencies]` con `frappe` y `erpnext` (`>=16.0.0,<17.0.0`) y `[tool.bench.assets]` con el Panel. Frappe HR no se declara (es opcional). (2026-10-21)
- [x] **Assets precompilados**: `assets.yml` con el workflow de Pilot en `version-16` y `develop` (contra Frappe `version-16`); probado en local con `build-app-assets.sh`. (2026-10-21)
- [x] **Semgrep del registro sin hallazgos** y en el CI (`ci.yml`, mismos criterios que el registro). (2026-10-21)
- [x] **Versiones**: rama `version-16` como canal `stable`, `develop` como `nightly`; subir `__version__` en cada publicación (el validador lo compara con lo publicado). `v0.4.0` es la primera publicable. (2026-10-21)
- [ ] **Publicación**: PR al registro desde el fork del usuario con `gh` (entrada en `apps.json`, `category: "Compliance"`, y `apps/erpnext_rd.json`). El workflow reutilizable `publish-release.yml` del registro no sirve fuera de Frappe (empuja a `frappe/marketplace`); ver `docs/marketplace.md`.

Requisitos a cumplir (tenerlos en cuenta desde ya en todo lo nuevo):
- ✅ **App en la raíz del repo** (2026-10-14): `pyproject.toml` y el paquete `erpnext_rd/` están en la raíz, como los espera `bench get-app`; `deploy/` y `docs/` quedan como carpetas extra.
- **Rama por versión de Frappe**: `version-16` (y luego `version-17`). Ya existe en GitHub (igual a `main`); es la rama `stable` del registro.
- ✅ **Sin acceso a la máquina** (se cumple hoy; mantenerlo): nada de pasos manuales, scripts de shell ni `docker exec`. Todo se configura en `after_install`/`after_migrate`, patches y DocTypes de configuración. Dependencias solo de pip en `pyproject.toml` (y apt en `[deploy.dependencies.apt]` si hiciera falta).
- ✅ **Instalación y desinstalación limpias** (2026-10-14): sitio nuevo, sitio con datos (multiempresa, multipaís con `es_empresa_rd`) y reinstalación probados. `before_uninstall` quita formato por defecto, tareas programadas y Dock; Frappe borra lo que tiene módulo.
- ✅ **HRMS opcional** (2026-10-14): `required_apps = ["frappe/erpnext"]`. Sin HRMS la app instala y pasa los tests (los de recibos de nómina se omiten); si HRMS se instala después, la Nómina RD se activa sola (campos, componentes, menú) y se retira si se desinstala. El CI (`deploy/ci/run-tests.sh`) corre los tests también en un sitio sin HRMS.
- ✅ **Jobs pesados en cola** (2026-10-14): el padrón RNC se descarga solo en la cola `long` al instalar (si está vacío), cada día a las 2:00 a. m. (solo si la DGII publicó un archivo nuevo, con `If-Modified-Since`) y con el botón de Configuración DGII. Medido (2026-10-16): descarga 46 s (zip de 23 MB), importación de 793 985 registros en 3 min 16 s, memoria pico del proceso 154 MB; cabe en la cola `long` de cualquier plan.
- ✅ **Ficha del Marketplace** (2026-10-16): logo, capturas, descripción (`docs/marketplace.md`), guía de uso (`docs/GUIA-DE-USO.md`), soporte por issues de GitHub con plantillas, CI verde y `CHANGELOG.md`. Falta crear el tag y la rama al publicar.
- **Secretos**: el certificado `.p12` y su clave se suben por la UI (campos Attach privado + Password), nunca en el repo.

## Código existente a aprovechar (investigado 2026-10-12)
No existe una app de ERPNext que cubra todo (e-CF + reportes + nómina RD). Tomaremos piezas como base o referencia:

| Repo | Uso en nuestro plan | Licencia / estado |
|---|---|---|
| [LewisMojica/dgii-compliance](https://github.com/LewisMojica/dgii-compliance) (Frappe) | **Base o referencia principal de la Fase 2**: secuencias NCF, asignación a facturas, reportes DGII. Revisar su modelo de DocTypes y su compatibilidad con v16 antes de copiar o adaptar | GPL-3.0, 84 commits, 3 estrellas, sin releases → poco maduro, auditar |
| [odoo-dominicana/l10n-dominicana](https://github.com/odoo-dominicana/l10n-dominicana) (Odoo, `l10n_do_accounting`) | Referencia de reglas de negocio: tipos de comprobante, validaciones, norma 06-18, NCF modificado | LGPL-3, la localización RD más madura (110 estrellas) |
| [angelpimentell/python-dgii-signer](https://github.com/angelpimentell/python-dgii-signer) (Python) | Referencia para la firma XML con .p12 (Fase 4) | **Sin licencia visible** → no copiar código, solo estudiarlo |
| [dev-fcastro/dgii-ecf](https://github.com/dev-fcastro/dgii-ecf) (.NET) | Referencia completa del flujo e-CF: semilla/token, firma (XML-DSig enveloped, C14N inclusivo, RSA-SHA256), recepción, aprobación comercial, anulaciones, consultas | Solo como referencia de protocolo |
| [victors1681/dgii-ecf](https://github.com/victors1681/dgii-ecf), [ithesk/firmadgii](https://github.com/ithesk/firmadgii) (Node) | Referencia de autenticación y RFCE (< RD$250,000) | Referencia |
| [Ruben890/RNC_DGII_DB](https://github.com/Ruben890/RNC_DGII_DB) (Python) | Lógica de descarga e importación del padrón RNC (Fase 2) | Revisar licencia |
| [CarlsRemy/DGII-UTILS](https://github.com/CarlsRemy/DGII-UTILS), [franklinmdev/dgii-ts](https://github.com/franklinmdev/dgii-ts) | Algoritmos de validación de RNC, cédula, NCF y e-NCF, para portarlos a Python | Revisar licencia |
| [alexander0205/vera PR #69](https://github.com/alexander0205/vera/pull/69) | Referencia de cálculo de nómina RD (AFP, SFS, ISR, INFOTEP, SRL, topes) con tasas 2026 | Otro stack; verificar tasas con TSS/DGII |
| Instructivo oficial DGII "Firmado de e-CF" + XSD oficiales | **Fuente de verdad** para la firma y el XML | Oficial |

Evaluación (2026-10-12): `dgii-compliance` es v15, sin bloqueo de secuencia (NCF duplicables), solo B01/B02/B14/B15 y con errores de sintaxis → **no se adopta**; se escribió `dgii_fiscal` propio tomando ideas (URL del padrón, excluir facturas POS consolidadas).

Reglas: solo se copia código con licencia compatible (GPL-3/LGPL-3/MIT); lo que no tenga licencia se usa únicamente como referencia. Primer paso de la Fase 2: clonar `dgii-compliance` en el devcontainer, instalarlo en v16 y decidir entre **adoptarlo como base del módulo `dgii_fiscal`** o reescribirlo tomando sus ideas.

## Archivos críticos a crear
- `apps/erpnext_rd/erpnext_rd/hooks.py` — doc_events, scheduler_events, fixtures.
- `deploy/apps.json`, `deploy/compose.yaml`, `.github/workflows/build-image.yml`.
- `apps/erpnext_rd/erpnext_rd/ecf/firma.py`, `ecf/dgii_client.py`, `ecf/xml_builder.py`.
- `apps/erpnext_rd/erpnext_rd/dgii_fiscal/ncf.py`.
- `apps/erpnext_rd/erpnext_rd/nomina_rd/calculos.py`.

Reutilizar: frappe_docker (`images/layered/Containerfile`, `pwd.yml`, `.devcontainer`), Salary Structure/Payroll Entry de HRMS, Script Report y Print Format de Frappe, `frappe.enqueue`/scheduler para jobs.

## Verificación
- Local: `bench --site dev.localhost run-tests --app erpnext_rd` (tests de NCF, dígito verificador RNC, cálculo ISR/TSS con casos conocidos, XML válido contra XSD, firma verificable).
- CI en GitHub Actions corre esos tests en cada PR.
- Fase 1: abrir el dominio de Dokploy, login, crear compañía RD, confirmar que ERPNext + HRMS + erpnext_rd aparecen en *Installed Apps* del mismo sitio (`bench --site <sitio> list-apps`) y que existe una sola base de datos en MariaDB.
- Fase 3: comparar TXT 606/607 generados con el validador/herramienta de la DGII.
- Fase 4: enviar e-CF de prueba en **TesteCF** y verificar estado "Aceptado"; luego completar set de CerteCF.
- Fase 5: nómina de prueba con empleados cuyos montos se cotejan contra la calculadora de la TSS/DGII.

## Orden de ejecución propuesto
Empezar por Fase 0 + Fase 1 (ERPNext 16.50 + HRMS corriendo primero en Docker local, luego en Dokploy con el repo y CI/CD listos), luego 2 → 3 → 4 → 5 de forma incremental, con un tag por fase.

## Requisitos del usuario (no automatizables por Claude)
- Servidor con Dokploy (mín. 4 GB RAM, 2 vCPU recomendados), dominio apuntando a él.
- Cuenta GitHub + PAT para GHCR/repos privados (lo configuras tú en Secrets).
- Certificado digital de firma (.p12) emitido por entidad autorizada y alta como emisor electrónico ante la DGII.
