# Plan: ERPNext v16.51 + HRMS + localización República Dominicana, desplegado en Dokploy

## Contexto
El usuario quiere un ERPNext propio, versionado en GitHub y desplegado en Dokploy, con:
- ERPNext v16.51.1 (frappe v16.52.0, HRMS v16.51.0) + Frappe HR (HRMS) para RH y nómina.
- Una app propia de localización RD: NCF / e-CF emitidos **directamente** ante la DGII, reportes 606/607/608/IT-1, validación RNC/Cédula, nómina RD (TSS/AFP/SFS/ISR/INFOTEP/regalía).
- Base para seguir agregando funcionalidades después.

Proyecto en `D:\Code Projects 2\ERPNext`. Git 2.56 y Docker 29.8 instalados.

**Una sola instancia, una sola base de datos:** un único sitio Frappe (p. ej. `erp.tudominio.com`) = una única base MariaDB 11.x. ERPNext, HRMS y `erpnext_rd` se instalan los tres en ese mismo sitio (`bench --site <sitio> install-app ...`), así que comparten tablas, usuarios, permisos, compañías, empleados, clientes y contabilidad. Si hay varias empresas, se manejan como varias *Company* dentro del mismo sitio. MariaDB se usa porque es la base de datos oficial y probada de ERPNext/HRMS.

**Principio clave:** no hacer fork de ERPNext/Frappe. Toda la personalización vive en una app propia (`erpnext_rd`) instalada sobre ERPNext/HRMS oficiales. Así puedes actualizar a 16.51, 16.52… sin conflictos de merge.

## Estado actual (actualizado 2026-10-16)

| Fase | Estado |
|---|---|
| 0 — Entorno y descarga | ✅ Hecho. Versiones verificadas: frappe v16.52.0, erpnext v16.51.1, hrms v16.51.0 (actualizadas el 2026-10-16). Se usa Docker local (imagen propia) en lugar de devcontainer. |
| 1 — Despliegue | 🟡 Repo público en GitHub (https://github.com/daniellora7/ERPNext-DR-Compilance) con CI en cada PR (`ci.yml`: ruff + tests con la misma imagen y compose, también en un sitio sin HRMS, vía `deploy/ci/run-tests.sh`) y `build-image.yml` (imagen a GHCR en `main` y tags `v*`). Local: `deploy/Containerfile` + `deploy/compose.yaml`, sitio `erp.localhost` en http://localhost:8090 con las 4 apps en una sola base MariaDB. Respaldo diario automático (servicio `backup`, `docs/RESPALDOS.md`, restauración probada) y guía de despliegue (`docs/DOKPLOY.md`). **Pendiente (usuario):** servidor Dokploy y dominio. |
| 2 — Base fiscal DGII | 🟡 Implementado en `feature/dgii-fiscal`: tipos de comprobante (21), Secuencia NCF con bloqueo, NCF en ventas/compras, RNC/Cédula, padrón (793 985 registros), 16 tests. NCF en POS (modo Sales Invoice y POS Invoice, tipo por defecto en Perfil de POS), formatos de impresión *Factura Fiscal RD* y *Recibo POS RD* (80 mm) con QR e-CF listo para la Fase 4, 19 tests. **Catálogo de cuentas DGII** (214 cuentas, NIIF PYMES; activos por categoría de depreciación fiscal; gastos agrupados por tipo 606, ingresos por tipo 607; cuentas de impuestos con concepto fiscal; plantillas ITBIS 18%/16%, propina y retenciones; retenciones de ISR a personas físicas al 15% y servicios técnicos al 3% según la Ley 30-26, vigente desde el 1/7/2026), aplicado por empresa solo a las de país República Dominicana sin movimientos, 28 tests. Prueba de punta a punta de un mes completo (`test_punta_a_punta.py`: ventas, nota de crédito, anulada, compras con retenciones, exterior y nómina; formatos y declaraciones cuadran con el mayor y sin avisos). **Pendiente (usuario):** revisar con facturas reales. |
| 3 — Reportes DGII | 🟡 Script Reports *Formato 606/607/608/609 DGII* con descarga del TXT oficial (`DGII_F_<formato>_<RNC>_<AAAAMM>.TXT`), columnas según los instructivos vigentes de la DGII, retenciones informadas en el mes de pago, facturas de consumo < RD$250,000 fuera del TXT con su resumen para la OFV, columna de observaciones. Toda la lógica fiscal (NCF, validación RNC, reportes) aplica solo a empresas con país República Dominicana. Reportes de apoyo *Resumen IT-1 DGII* (ingresos gravados por tasa, exentos, exportaciones, formas de cobro, liquidación del ITBIS con saldo a favor, retenciones por terceros y Norma 08-04, ITBIS retenido a terceros, vencimiento día 20) y *Resumen IR-17 DGII* (ISR retenido a terceros por tipo de retención y pagos al exterior, en el mes de pago, vencimiento día 10), calculados con los mismos registros del 606/607/609. 45 tests. **Pendiente:** pre-validar los TXT con la herramienta de la DGII usando datos reales. |
| UI — Módulo RD Compliance | ✅ Un solo ícono **RD Compliance** en el dock de Frappe v16 (ícono duotono propio con animación) y un sidebar con secciones desplegables: *DGII Fiscal* (Secuencia NCF, Tipo Comprobante Fiscal, Configuración DGII), *DGII Reportes* (606–609) y *Padrón RNC* (Contribuyentes DGII). Los módulos internos se muestran dentro de RD Compliance (`code_only_modules`). e-CF y Nómina RD se agregarán como secciones nuevas de este mismo menú. **Estándar visual frappe-ui** (2026-10-14): el HTML propio de los reportes usa los tokens de color del escritorio v16 (modo oscuro incluido). **Panel RD Compliance** (2026-10-14, piloto): pantalla en `/rd-compliance` hecha con frappe-ui 1.0.2 (`frontend/`) con plazos y montos del 606–609, IT-1 e IR-17 del mes, secuencias NCF por agotarse/vencer/agotadas, registros con observaciones y estado del padrón; se abre dentro del escritorio (página `panel-cumplimiento` del sidebar) en la misma ventana. Base técnica para el monitor de e-CF y el portal de empleados. |
| 4 — e-CF | 🟡 Todo lo que no requiere certificado real: XSD oficiales, XML guiado por el XSD (E31-E47, RFCE), firma XMLDSig verificada con xmlsec1, cliente de los servicios DGII (semilla/token, recepción, RFCE, consultas, anulación, aprobación comercial, directorio), *Emisor ECF* por empresa y registro *Envio ECF*. Contingencia con reenvío automático, entrega al comprador con su acuse, servicios públicos del receptor (`/fe/...`) con *ECF Recibido*, acuse (ARECF) y aprobación comercial (ACECF), anulación de rangos (*Anulacion ENCF*, ANECF) y *Set Pruebas ECF* para CerteCF (2026-10-16). **Pendiente (usuario):** certificado .p12 y alta como emisor; pruebas en TesteCF, set de CerteCF y registrar la URL del receptor en la DGII. |
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
9. **Publicar `v0.3.0`** (cuando el usuario lo pida): fusionar `develop` en `main`, crear la rama `version-16` y el tag `v0.3.0` desde `main` (el tag publica la imagen en GHCR), y registrar la app en el Marketplace con `docs/marketplace.md`.
8. **Al subir de versión Frappe HR:** si su `hrms/locale/es.po` ya trae el español completo (en Crowdin quedó al 100 % y aprobado en octubre de 2026; falta que el bot lo sincronice al repo y salga en una versión), borrar de `erpnext_rd/locale/es.po` el bloque «Frappe HR: textos que faltan en su catálogo oficial». Si se queda, tapa las traducciones oficiales (la app se carga después) y mezcla términos (p. ej. *Arrear*: «atrasos» oficial, «retroactivo» nuestro). Ajustar `test_frappe_hr_completo_en_espanol` en `tests/test_navegacion.py` a las traducciones oficiales. La traducción de los nombres del dock (`boot.py`) se mantiene hasta que Frappe los pase por `__()`. El bloque anterior, «Frappe HR: correcciones de su catálogo oficial» (90 traducciones erradas: *Shift Type* «Tipo de Cambio», *Slab* «Losa», *Leave* «vacaciones»…), se mantiene: revisar entrada por entrada si el catálogo oficial ya las corrigió y borrar solo esas.

### Mejoras de cumplimiento (análisis del 2026-10-16)
Lo que se puede hacer sin depender del usuario, en tres ramas:
1. ✅ `feature/tasa-recordatorios-cheque`: tasa del dólar del BCRD, recordatorios por correo de vencimientos y formato *Cheque RD*.
2. ✅ `feature/isr-itbis-ncf-proveedor`: anticipos del ISR (art. 314), proporcionalidad del ITBIS (art. 349) y aviso de NCF/RNC del proveedor no válido (la consulta de NCF de la DGII no tiene captcha). Pendiente: tres cuotas de las pequeñas empresas (Ley 30-26, desde 2027) cuando la DGII publique los criterios.
3. Nómina: dependientes adicionales del SFS y subsidios de la SISALRIL.
4. Apoyo al IR-2: depreciación fiscal por categoría (art. 287), ajuste por inflación y cuadre contable-fiscal.

Dependen del usuario: e-CF en producción, pre-validar TXT con datos reales, extractos de los bancos (ejemplos), cuadre de la factura TSS (ejemplo), ISC y DIOR (solo si aplican).

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

## Fase 7 — Publicación en el Marketplace de Frappe Cloud (más adelante)
Objetivo: que la app se instale desde Frappe Cloud como las demás localizaciones (p. ej. México e-Invoice). Repo público: https://github.com/daniellora7/ERPNext-DR-Compilance (GPL-3.0).

Requisitos a cumplir (tenerlos en cuenta desde ya en todo lo nuevo):
- ✅ **App en la raíz del repo** (2026-10-14): `pyproject.toml` y el paquete `erpnext_rd/` están en la raíz, como los espera `bench get-app`; `deploy/` y `docs/` quedan como carpetas extra.
- **Rama por versión de Frappe**: `version-16` (y luego `version-17`), compatible con la versión que ofrezca Frappe Cloud. Se crea desde `main` al publicar `v0.3.0` (`CHANGELOG.md`).
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
