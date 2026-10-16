#!/usr/bin/env bash
# Corre los tests de erpnext_rd en un stack desechable (proyecto Compose aparte, sitio y base
# de datos propios, contraseñas aleatorias). No toca el sitio de desarrollo ni sus volúmenes.
#
#   deploy/ci/run-tests.sh                 usa la imagen ${ERPNEXT_IMAGE}:${ERPNEXT_IMAGE_TAG}
#   DEV=1 deploy/ci/run-tests.sh           monta el código del repo (sin reconstruir la imagen)
#   KEEP=1 deploy/ci/run-tests.sh          deja el stack arriba para revisar fallos
#   SIN_HRMS=0 deploy/ci/run-tests.sh      omite la segunda pasada en un sitio sin Frappe HR
set -euo pipefail
cd "$(dirname "$0")/../.."

export COMPOSE_PROJECT_NAME="${COMPOSE_PROJECT_NAME:-erpnext-rd-ci}"
export SITE_NAME="${SITE_NAME:-ci.localhost}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' | head -c 24)}"
export DB_ROOT_PASSWORD="${DB_ROOT_PASSWORD:-$(head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n' | head -c 24)}"
export ERPNEXT_IMAGE="${ERPNEXT_IMAGE:-erpnext-rd}"
export ERPNEXT_IMAGE_TAG="${ERPNEXT_IMAGE_TAG:-local}"

archivos=(-f deploy/compose.yaml)
if [ "${DEV:-0}" = "1" ]; then
	archivos+=(-f deploy/compose.dev.yaml)
fi
compose() { docker compose "${archivos[@]}" "$@"; }

limpiar() {
	if [ "${KEEP:-0}" != "1" ]; then
		compose down --volumes --remove-orphans >/dev/null 2>&1 || true
	fi
}
trap limpiar EXIT

echo "==> Creando el sitio de pruebas ${SITE_NAME} (proyecto ${COMPOSE_PROJECT_NAME})"
compose up -d --no-build redis-cache redis-queue create-site backend
contenedor="$(compose ps -aq create-site)"
estado="$(docker wait "$contenedor")"
if [ "$estado" != "0" ]; then
	docker logs "$contenedor" | tail -80
	echo "create-site terminó con código $estado" >&2
	exit 1
fi

if [ "${DEV:-0}" = "1" ]; then
	# El código montado puede traer traducciones más nuevas que las compiladas en la imagen
	compose exec -T backend bench compile-po-to-mo --app erpnext_rd --force
fi

echo "==> Tests"
compose exec -T backend bench --site "$SITE_NAME" set-config allow_tests true
compose exec -T backend bench --site "$SITE_NAME" run-tests --app erpnext_rd --failfast

# HRMS es opcional: la app debe instalar y pasar los tests en un sitio solo con ERPNext
if [ "${SIN_HRMS:-1}" = "1" ]; then
	sitio_sin_hrms="sin-hrms.localhost"
	echo "==> Tests en ${sitio_sin_hrms} (ERPNext + erpnext_rd, sin Frappe HR)"
	compose exec -T backend bench new-site "$sitio_sin_hrms" \
		--mariadb-user-host-login-scope='%' \
		--admin-password="$ADMIN_PASSWORD" \
		--db-root-username=root \
		--db-root-password="$DB_ROOT_PASSWORD" \
		--install-app erpnext \
		--install-app erpnext_rd
	compose exec -T backend bench --site "$sitio_sin_hrms" set-config allow_tests true
	compose exec -T backend bench --site "$sitio_sin_hrms" run-tests --app erpnext_rd --failfast
fi
