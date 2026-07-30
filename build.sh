#!/usr/bin/env bash
# build.sh — Script de construcción para Render
# Render lo ejecuta automáticamente antes de iniciar el servidor

set -o errexit  # Detener si cualquier comando falla

echo "==> Instalando dependencias..."
pip install -r requirements.txt

echo "==> Recolectando archivos estáticos..."
python manage.py collectstatic --no-input

echo "==> Aplicando migraciones..."
python manage.py migrate

echo "==> Build completado."
