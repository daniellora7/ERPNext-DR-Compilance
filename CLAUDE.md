# CLAUDE.md

El usuario escribe en español: responder en español.

**ERPNext RD**: ERPNext + Frappe HR + app propia `erpnext_rd` con la localización de República Dominicana (NCF, e-CF, reportes DGII, padrón RNC, nómina RD). Docker local; después Dokploy y Marketplace de Frappe Cloud.

Documentos (leer el que haga falta, no todo):
- `docs/PLAN.md`: fases, estado y pendientes. Actualizarlo al avanzar.
- `docs/NOTAS-TECNICAS.md`: cómo está implementado cada módulo (NCF, reportes, padrón, panel, nómina, TSS, IR-3/IR-13, etc.). Actualizarlo al cambiar un módulo.
- `docs/lineamientos-diseno-frappe.md`: lineamientos de diseño de Frappe y lista de revisión de la interfaz.

## Versiones fijadas

Frappe **v16.52.0** (`FRAPPE_BRANCH` en `deploy/Containerfile`), ERPNext **v16.51.1** y HRMS **v16.51.0** (`deploy/apps.json`), MariaDB 11.8, Python 3.14.

## Reglas

- **Un sitio Frappe, una base MariaDB** (no PostgreSQL). Varias empresas = varias *Company*.
- **No modificar Frappe, ERPNext ni HRMS**: todo en `erpnext_rd` (DocTypes, `hooks.py`, `override_doctype_class`, Custom Fields y Property Setters creados por código en `install.py`, patches).
- Tasas, topes y escalas que cambian por ley: en DocTypes de configuración editables, nunca en el código.
- Lógica fiscal y de nómina **solo en empresas con país *Dominican Republic*** (`ncf.es_empresa_rd`).
- **HRMS es opcional**: lo que toque sus DocTypes se condiciona con `nomina_rd.hrms_instalado()`.
- **Marketplace**: instalable sin acceso a la máquina (`after_install`/`after_migrate`, patches), funciona sin HRMS y se desinstala limpio (todo Property Setter lleva `module` de la app).
- **Interfaz**: estándar frappe-ui. Solo tokens CSS (`--ink-*`, `--surface-*`, `--outline-*`; avisos `--ink-amber-8`, errores `--ink-red-6`), nunca hex ni Bootstrap (salvo formatos de impresión). Revisar en claro y oscuro.
- **Formatos imprimibles: siempre editables en el constructor de formatos de Frappe** (Print Format no estándar del constructor, bloques HTML/Jinja; ver `erpnext_rd/formatos.py`). Nunca formatos estándar ni `{% include %}` a plantillas de la app.
- Nómina RD va del lado de Frappe HR (sidebar `nomina_rd`); lo fiscal, en el sidebar único de RD Compliance.
- Código de terceros solo con licencia GPL-3, LGPL-3 o MIT. La app es GPL-3.0.

## Entorno local

- URL http://localhost:8090, sitio `erp.localhost`. **El 8080 es de otro proyecto (`plastidel-dev-api`): no tocarlo.**
- Contraseñas en `deploy/.env` (no se versiona): **no repetirlas en el chat**.
- El sitio tiene la empresa real del usuario (**Dynamics Plastics**): no crear documentos de prueba sin permiso. Respaldar (`bench backup --with-files`) antes de actualizar versiones.
- `down -v` borra los volúmenes con los datos: **nunca sin confirmación**.

```bash
# Stack de desarrollo (monta erpnext_rd/ del repo)
docker compose -f deploy/compose.yaml -f deploy/compose.dev.yaml --env-file deploy/.env up -d
# Cambios Python: reiniciar; DocTypes/campos: migrate
docker restart deploy-backend-1 deploy-queue-short-1 deploy-queue-long-1 deploy-scheduler-1
docker exec deploy-backend-1 bench --site erp.localhost migrate
# Tests y lint
docker exec deploy-backend-1 bench --site erp.localhost run-tests --app erpnext_rd
MSYS_NO_PATHCONV=1 docker run --rm -v "$PWD:/w" -w /w ghcr.io/astral-sh/ruff:0.12.12 check erpnext_rd
# Imagen (~15 min)
docker build -f deploy/Containerfile -t erpnext-rd:local .
# Panel (frontend/) sin Node local
MSYS_NO_PATHCONV=1 docker run --rm -u root --entrypoint bash -v "$PWD:/work" -v erpnext-rd-frontend-nm:/work/frontend/node_modules -w /work/frontend erpnext-rd:local -c "yarn install --frozen-lockfile && yarn build"
```

## Estilo

- Python: tabs, comillas dobles, ruff (line-length 110). Repo en LF (`.gitattributes`).
- Nombres de reportes sin tilde (la carpeta se arma con el nombre); el título con tilde va en `locale/es.po` (`bench compile-po-to-mo --app erpnext_rd --locale es`).
- Editar archivos con Edit/Write o scripts en el scratchpad con `python -X utf8`: los heredocs de bash rompen `\n` y tildes.

## Control de versiones

- Commit local de cada unidad de trabajo, sin esperar a que lo pidan. Mensajes en español con prefijo (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`).
- **Push, PR y merge solo cuando el usuario lo pida.** Ramas: `main` (producción), `develop` (integración), `feature/<nombre>`.
- Nunca versionar `deploy/.env`, certificados `.p12`, contraseñas ni tokens (el repo es público: https://github.com/daniellora7/ERPNext-DR-Compilance).
