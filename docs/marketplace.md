# Publicación en el Marketplace de Frappe

Hay dos vías, y conviene preparar las dos:

1. **Marketplace de Frappe** (registro [`frappe/marketplace`](https://github.com/frappe/marketplace), analizado el 2026-10-20). Es el registro abierto que leen `bench get-app` de [Pilot](https://github.com/frappe/pilot), el nuevo gestor de servidores de Frappe, y la página *Marketplace* de su panel de administración. Una app entra con un PR al registro, y el CI del registro la valida. La sección siguiente es la guía completa.
2. **Frappe Cloud**: la ficha con textos y capturas está más abajo, en «Ficha y textos».

## 1. Marketplace de Frappe (`frappe/marketplace` y Pilot)

### Cómo funciona

- `apps.json`: una entrada con los datos de cada app, que apunta a su archivo de versiones.
- `apps/<app>.json`: las **versiones publicadas** (`releases`). Cada una fija una rama y un commit exacto (SHA de 40 caracteres), con la versión de la app, el rango de Frappe y las dependencias de otras apps del marketplace. Un push a la rama no publica nada: cada versión nueva entra con un PR al registro.
- **Canal:**
  - `stable` es lo normal. Pilot instala la versión `stable` más nueva compatible con la versión de Frappe del bench.
  - `nightly` es solo para una rama de desarrollo que convive con ramas de versión. En nuestro caso, `develop` junto a `version-16`.
- **Una versión por rama:** una rama no puede tener dos versiones con el mismo número. Cada publicación sube `__version__`.
- **CI del registro, en orden; se detiene en el primer fallo:**
  1. **Esquema:**
     - En la entrada: `name`, `title`, `description`, `repo`, `logo_url`, `website`, `documentation`, `category`, `categories` (lista no vacía), `stars` (entero; 0 sirve) y `releases`, que debe ser exactamente `apps/erpnext_rd.json`.
     - En cada versión: `version`, `branch`, `commit`, `frappe_core` y `dependencies` (`{}` sirve, pero la clave tiene que estar).
  2. **Semgrep** con las reglas de `validation/semgrep-rules/`:
     - Los hallazgos *Critical* (ERROR) y *Major* (HIGH), o los marcados `is_blocking`, **bloquean el PR**.
     - Los *Minor* (WARNING) y los *Info* solo se informan.
  3. **Validador de `get-app` de Pilot.** Instala la app en un entorno desechable junto a Frappe de la rama que indica `frappe_core` y revisa:
     - la estructura del repo y la sintaxis;
     - que `hooks.py` apunte a código que existe;
     - las *fixtures* y los enlaces simbólicos;
     - que `required_apps` coincida con `[tool.bench.frappe-dependencies]`;
     - las importaciones, y que las dependencias se puedan resolver junto a las demás apps;
     - que estén publicados los **assets precompilados** del commit.

     Además, rechaza la versión si `version` o `frappe_core` no coinciden con el `pyproject.toml` de ese commit.
- **Informe del CI:** se publica como comentario del PR. Si corriges algo en nuestro repo, comenta `/rereview` en el PR para que vuelva a correr.

### Lo que hay que cambiar en nuestro repo

**1. `pyproject.toml`: declarar Frappe, ERPNext y el SPA.** Sin la tabla `[tool.bench.frappe-dependencies]`, Pilot rechaza la app.

`hooks.py` declara `required_apps = ["frappe/erpnext"]`, así que ERPNext tiene que ir aquí con su rango. Frappe HR **no** va: es opcional, y si se declarara pasaría a ser obligatorio.

`[tool.bench.assets]` hace falta porque el `package.json` raíz tiene script `build` (el Panel RD Compliance en `frontend/`). Sin esa tabla, el workflow de assets de Pilot falla.

```toml
[tool.bench.frappe-dependencies]
frappe = ">=16.0.0,<17.0.0"
erpnext = ">=16.0.0,<17.0.0"

[tool.bench.assets]
build_dir = "./frontend"
out_dir = "./erpnext_rd/public/frontend"
index_html_path = "./erpnext_rd/www/rd-compliance.html"
```

Las bibliotecas que importamos de fuera de Python ya vienen con Frappe o ERPNext: `requests`, `lxml`, `cryptography`, `num2words`, `openpyxl`, `pyqrcode`, `holidays`, `python-dateutil` y `werkzeug`. Si algún día se agrega otra, va en `[project].dependencies` con un **rango**, no fijada (`==`), para no chocar con otras apps del mismo bench.

**2. Workflow de assets precompilados** (`.github/workflows/assets.yml`). Pilot descarga los assets del commit en vez de compilarlos en el servidor, y el validador del registro **exige** que estén publicados. Se suben al release `assets-<rama>` del repo:

```yaml
name: Pre-build assets
on:
  push:
    branches: [version-16, develop]
jobs:
  assets:
    name: Pre-build assets
    uses: frappe/pilot/.github/workflows/app-assets.yml@develop
    with:
      frappe-branch: version-16   # develop también se construye contra Frappe v16
    permissions:
      contents: write
```

La compilación no debe modificar archivos versionados (por ejemplo `frontend/yarn.lock`). Si lo hace, Pilot deja de usar los assets precompilados y compila en el servidor. La salida (`erpnext_rd/public/frontend/` y `erpnext_rd/www/rd-compliance.html`) ya está en `.gitignore`.

Para probarlo antes del push:

```bash
pilot/scripts/build-app-assets.sh <checkout de la app> version-16 <carpeta de salida>
```

Necesita Node.js 24.

**3. Workflow de publicación** (`.github/workflows/publish-marketplace.yml`). Se lanza a mano (*Run workflow*) **después** de que termine el de assets del mismo commit. Lee la versión, `frappe_core` y las dependencias del `pyproject.toml`, agrega la versión a `apps/erpnext_rd.json` y abre el PR en el registro:

```yaml
name: Publicar en el Marketplace de Frappe
on:
  workflow_dispatch:
    inputs:
      branch:
        default: version-16
      channel:
        default: stable
jobs:
  publish:
    uses: frappe/marketplace/.github/workflows/publish-release.yml@main
    with:
      app: erpnext_rd
      branch: ${{ inputs.branch }}
      channel: ${{ inputs.channel }}
    secrets:
      registry_token: ${{ secrets.MARKETPLACE_PR_TOKEN }}
```

`MARKETPLACE_PR_TOKEN` es un token de GitHub del usuario que puede hacer *fork* de `frappe/marketplace`, subir una rama y abrir el PR (PAT *fine-grained* o token de una GitHub App). Va en *Settings → Secrets* del repo; **nunca en el código**.

**4. Rama `version-16` y versión.**
- `version-16` ya existe en GitHub, igual a `main`. Es la rama `stable` que instalarán los benches.
- Antes de cada publicación hay que subir `erpnext_rd/__init__.py` (`__version__`, hoy `0.3.0`), porque el validador compara el número publicado con el del commit.
- `develop` se puede publicar como `nightly`, con su propio número de versión.

**5. Corregir lo que Semgrep bloquea.** Corrí las reglas del registro (Semgrep 1.140) sobre `develop` + `feature/perfil-tributario` el 2026-10-20: **16 hallazgos bloqueantes (Major)** y 21 avisos (Minor). La regla en `NOTAS-TECNICAS.md` («Código que pase el Marketplace») evita que vuelvan a aparecer.

| Regla (bloquea) | Dónde | Corrección |
|---|---|---|
| `frappe-sql-format-injection` (6) | `dgii_fiscal/catalogo_cuentas.py:589`, `dgii_reportes/datos.py:504`, `dgii_reportes/estados_ir2.py:492`, `dgii_reportes/ir2.py:324` y `:368`, `padron_rnc/padron.py:102` | Sin f-strings ni `.format()` dentro de `frappe.db.sql`. Pasar los valores como parámetros (`%(x)s`); las condiciones variables, con `frappe.qb` o con consultas fijas por caso. El `INSERT` por lotes del padrón: armar la sentencia con `frappe.qb` o con `executemany` (`frappe.db.bulk_insert` no hace `ON DUPLICATE KEY UPDATE`). |
| `frappe-format-string-injection` (5) | `ecf/emision.py:180`, `:247`, `:298`; `ecf/recepcion.py:74`, `:259` | `_("…{0}").format(str(error))` en vez de pasar el objeto de la excepción. |
| `frappe-manual-commit` (3) | `padron_rnc/padron.py:119` y `:146`, `www/rd_compliance.py:21` | El padrón hace commit por lote a propósito (800 mil registros en la cola `long`) y el panel, para guardar el token CSRF. Justificarlos con `# nosemgrep: frappe-manual-commit` y el motivo en la línea anterior. El `# nosemgrep: <texto>` que hay hoy en `www/rd_compliance.py` **no surte efecto**: Semgrep lee lo que sigue a los dos puntos como nombre de regla. |
| `frappe-modifying-but-not-committing` (2) | `ecf/doctype/anulacion_encf/anulacion_encf.py:142` (`on_submit`) | Falso positivo: `guardar_xml` ya guarda el campo `xml` y la fecha va en `db_set`. Asignar `xml` dentro del mismo `db_set` para que la regla no lo marque. |

Avisos (no bloquean, pero el revisor de Frappe los comenta):
- `missing-argument-type-hint` (13): los métodos `@frappe.whitelist()` de `dgii_reportes/formatos.py`, `nomina_rd/bonificacion.py`, `novedades.py`, `regalia.py`, `sirla.py`, `tss.py` y `ecf/doctype/anulacion_encf` necesitan tipos en todos sus argumentos (Frappe v16 valida los tipos de los argumentos).
- `frappe-no-functional-code` (4): `map`/`filter` con `lambda` en `datos.py`, `empleado.py`, `sirla.py` y `tss.py`. Usar listas por comprensión.
- `frappe-setuser` (2) en `ecf/receptor.py`: el receptor de e-CF pone `Administrator` porque Frappe exige un usuario para atender al emisor, y vuelve a `Guest` antes de responder. Hay que explicarlo en el PR o buscar una forma sin `set_user`.
- `frappe-security-file-traversal` (2) en `ecf/esquemas.py` y `formatos.py`: leen archivos de la propia app con rutas fijas. Explicarlo en el PR.

Para revisarlo en local con las mismas reglas:

```bash
git clone --depth 1 https://github.com/frappe/marketplace /tmp/marketplace
docker run --rm -v "$PWD:/src:ro" -v /tmp/marketplace/validation/semgrep-rules:/rules:ro semgrep/semgrep:1.140.0 semgrep scan --config /rules --metrics=off /src
```

Conviene agregarlo al CI del repo (`ci.yml`) para que ningún PR lo rompa.

**6. Datos de la entrada.**
- `logo_url`: URL directa a un PNG o SVG cuadrado. Sirve `erpnext_rd/public/images/erpnext_rd_logo.svg` (64 × 64) por su URL *raw* de GitHub en `main`.
- `website`: el repo.
- `documentation`: la guía de uso.

### Borradores de la entrada

`apps.json`, en orden alfabético:

```json
{
  "name": "erpnext_rd",
  "title": "ERPNext RD",
  "description": "Localización de República Dominicana para ERPNext y Frappe HR: NCF y e-CF, reportes DGII, padrón RNC y nómina RD",
  "repo": "https://github.com/daniellora7/ERPNext-DR-Compilance",
  "logo_url": "https://raw.githubusercontent.com/daniellora7/ERPNext-DR-Compilance/main/erpnext_rd/public/images/erpnext_rd_logo.svg",
  "website": "https://github.com/daniellora7/ERPNext-DR-Compilance",
  "documentation": "https://github.com/daniellora7/ERPNext-DR-Compilance/blob/main/docs/GUIA-DE-USO.md",
  "categories": ["Localization", "Compliance", "HR & Payroll"],
  "category": "Compliance",
  "stars": 0,
  "releases": "apps/erpnext_rd.json"
}
```

`apps/erpnext_rd.json`, con la primera versión. Si se usa el workflow de publicación, este archivo se crea en el PR inicial y el workflow agrega las siguientes versiones:

```json
{
  "name": "erpnext_rd",
  "releases": [
    {
      "version": "0.3.0",
      "branch": "version-16",
      "commit": "<SHA completo del commit en version-16>",
      "frappe_core": ">=16.0.0,<17.0.0",
      "dependencies": {"erpnext": ">=16.0.0,<17.0.0"},
      "channel": "stable"
    }
  ]
}
```

ERPNext y Frappe HR ya están en el registro (`erpnext`, `hrms`). Las localizaciones de otros países (México, Ecuador, Alemania, Kenia) usan `category: "Compliance"`.

### Pasos para publicar (cuando el usuario lo pida)

1. Corregir los 16 hallazgos bloqueantes y agregar Semgrep al CI.
2. Agregar las tablas al `pyproject.toml` y los dos workflows. Probar el build de assets en local.
3. Fusionar en `main` y actualizar `version-16`. Subir `__version__` y crear el tag `v0.x.y`.
4. Esperar a que el workflow de assets publique `erpnext_rd-<commit>.tar.gz` en el release `assets-version-16`.
5. Primera vez: fork de `frappe/marketplace`; agregar la entrada a `apps.json` y crear `apps/erpnext_rd.json`; abrir el PR. Las siguientes veces: *Run workflow* en «Publicar en el Marketplace de Frappe».
6. Revisar el comentario del CI en el PR. Corregir lo que bloquee y comentar `/rereview`.

## 2. Ficha y textos (Frappe Cloud y Marketplace de Frappe)

Textos y lista de lo que falta para publicar ERPNext RD. Requisitos técnicos: `docs/PLAN.md`, Fase 7.

### Textos

**Nombre:** ERPNext RD

**Descripción corta:** Localización de República Dominicana para ERPNext y Frappe HR: NCF y e-CF, reportes DGII, padrón RNC y nómina RD.

**Descripción larga:**

ERPNext RD adapta ERPNext y Frappe HR a la República Dominicana sin modificar su código.

- **Comprobantes fiscales:** secuencias NCF sin duplicados en ventas, compras y POS; validación de RNC y cédula con el padrón de la DGII; catálogo de cuentas DGII.
- **Facturación electrónica (e-CF):** XML de los diez tipos y del resumen de consumo según los esquemas oficiales, firma digital con el certificado de la empresa, envío a la DGII con contingencia y entrega al comprador; recepción de e-CF de proveedores con acuse y aprobación comercial; anulación de rangos y set de pruebas para la certificación.
- **Declaraciones DGII:** formatos 606, 607, 608 y 609 con su archivo TXT, y resúmenes del IT-1 e IR-17; anticipos del ISR y cuadre fiscal del IR-2 con depreciación fiscal, ajuste por inflación y anexos A-1 y B-1.
- **Nómina RD (con Frappe HR):** AFP, SFS (con dependientes adicionales), ISR e INFOTEP; prestaciones, vacaciones, regalía y bonificación; subsidios de la SISALRIL; archivos de la TSS (AM, NV, RT), IR-3, IR-13 y planillas del Ministerio de Trabajo.
- **Panel de cumplimiento:** plazos y montos del mes en una pantalla.

Cubre a las personas jurídicas del régimen ordinario; los regímenes e impuestos especiales están en desarrollo. Todas las tasas y escalas se editan en la configuración. Solo actúa en empresas con país República Dominicana, así que convive con empresas de otros países. Frappe HR es opcional.

**Categorías:** Localization, Accounting, HR & Payroll (en el registro de Frappe: `category` = `Compliance`).

**Licencia:** GPL-3.0. **Código:** https://github.com/daniellora7/ERPNext-DR-Compilance

**Documentación:** https://github.com/daniellora7/ERPNext-DR-Compilance/blob/main/docs/GUIA-DE-USO.md

**Soporte:** https://github.com/daniellora7/ERPNext-DR-Compilance/issues (plantillas de error y de sugerencia en `.github/ISSUE_TEMPLATE/`).

### Capturas (tema oscuro, 1440 × 900)

Tomadas en un sitio de demostración con empresas y datos ficticios: un mes registrado con la prueba de punta a punta (`erpnext_rd/tests/test_punta_a_punta.py`).

| Captura | Archivo |
|---|---|
| RD Compliance: panel de cumplimiento con los plazos del mes | `docs/capturas/rd-compliance.png` |
| Factura Fiscal RD (crédito fiscal B01) | `docs/capturas/factura-fiscal-rd.png` |
| Nómina RD: autodeterminación de la TSS | `docs/capturas/nomina-rd.png` |
| Volante de pago RD | `docs/capturas/volante-pago-rd.png` |

![RD Compliance](capturas/rd-compliance.png)

![Factura Fiscal RD](capturas/factura-fiscal-rd.png)

![Nómina RD](capturas/nomina-rd.png)

![Volante de pago RD](capturas/volante-pago-rd.png)

Opcionales para más adelante: formato 606 y envío e-CF aceptado (con el certificado real).

### Pendiente (ficha)

- [x] Rama `version-16` (Frappe Cloud y el registro instalan por rama): ya existe en GitHub.
- [ ] Tag `v0.3.0` desde `main` cuando `develop` se fusione (ver `CHANGELOG.md`).
- [ ] Lo que exige el registro `frappe/marketplace` (sección 1): `pyproject.toml`, assets precompilados, Semgrep sin bloqueantes y workflow de publicación.
- [x] CI público en verde en cada PR.
- [x] Capturas en tema oscuro con datos ficticios (`docs/capturas/`).
- [x] Enlace de soporte (issues de GitHub con plantillas) y documentación de uso (`docs/GUIA-DE-USO.md`).
- [x] Padrón RNC medido: descarga 46 s (zip de 23 MB) e importación de 793 985 registros en 3 min 16 s con 154 MB de memoria pico, en la cola `long`.
- [x] Logo: `erpnext_rd/public/images/erpnext_rd_logo.svg` (`app_logo_url`).
- [x] Instala sin acceso a la máquina, funciona sin Frappe HR y se desinstala limpio.
