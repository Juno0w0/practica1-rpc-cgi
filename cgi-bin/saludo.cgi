#!/usr/bin/env bash
# saludo.cgi — Procedimiento remoto demostrativo (RPC vía CGI)
# Variables CGI estándar: REQUEST_METHOD, QUERY_STRING, CONTENT_LENGTH,
# CONTENT_TYPE, HTTP_ACCEPT, REMOTE_ADDR, etc.

set -euo pipefail

# --- 1) Lectura de parámetros (marshalling inverso) ---
nombre=""
case "${REQUEST_METHOD:-GET}" in
  GET)
    nombre=$(echo "${QUERY_STRING:-}" | sed -n 's/.*nombre=\([^&]*\).*/\1/p')
    ;;
  POST)
    body=$(head -c "${CONTENT_LENGTH:-0}")
    nombre=$(echo "$body" | sed -n 's/.*nombre=\([^&]*\).*/\1/p')
    ;;
  *)
    printf 'Status: 405 Method Not Allowed\r\n'
    printf 'Content-Type: text/plain; charset=UTF-8\r\n\r\n'
    echo "Metodo no soportado: $REQUEST_METHOD"
    exit 0
    ;;
esac

# Decodificar URL (manera simple)
nombre=$(printf '%b' "${nombre//%/\\x}")
[ -z "$nombre" ] && nombre="alumna(o) de ESIME"

# --- 2) Seleccion de representacion segun el cliente ---
if [[ "${HTTP_ACCEPT:-}" == *json* ]]; then
  printf 'Content-Type: application/json; charset=UTF-8\r\n\r\n'
  printf '{"servicio":"saludo","resultado":"Hola, %s","origen":"%s"}\n' \
    "$nombre" "${REMOTE_ADDR:-?}"
else
  printf 'Content-Type: text/plain; charset=UTF-8\r\n\r\n'
  echo "Hola, $nombre - peticion desde ${REMOTE_ADDR:-?}"
fi
