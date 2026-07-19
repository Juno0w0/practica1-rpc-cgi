#!/usr/bin/env bash
# calc.cgi - Procedimiento remoto multi-operacion (RPC via CGI)
# Operaciones: sum | sub | mul | div     Parametros: op, a, b
# Idempotencia: cabecera Idempotency-Key -> cache en /var/tmp/rpc-calc-cache
set -euo pipefail

decode() { printf '%b' "${1//%/\\x}"; }
param()  { echo "${1}" | sed -n "s/.*${2}=\([^&]*\).*/\1/p"; }
json_header() { printf 'Content-Type: application/json; charset=UTF-8\r\n'; }

# --- Lectura de parametros (GET o POST) ---
qs="${QUERY_STRING:-}"
[ "${REQUEST_METHOD:-GET}" = POST ] && qs=$(head -c "${CONTENT_LENGTH:-0}")

op=$(decode "$(param "$qs" op)")
a=$(decode "$(param "$qs" a)")
b=$(decode "$(param "$qs" b)")
idemp="${HTTP_IDEMPOTENCY_KEY:-}"

# --- Validacion (seguridad: evitar inyeccion en bc) ---
num_re='^-?[0-9]+(\.[0-9]+)?$'
if [ -z "$op" ] || [ -z "$a" ] || [ -z "$b" ]; then
  printf 'Status: 400 Bad Request\r\n'; json_header; printf '\r\n'
  echo '{"error":"parametros op, a y b son obligatorios"}'; exit 0
fi
if ! [[ "$a" =~ $num_re ]] || ! [[ "$b" =~ $num_re ]]; then
  printf 'Status: 400 Bad Request\r\n'; json_header; printf '\r\n'
  echo '{"error":"a y b deben ser numeros (ej. 3 o 2.5)"}'; exit 0
fi

# --- Idempotencia: reenviar respuesta cacheada ---
cache=/var/tmp/rpc-calc-cache
mkdir -p "$cache"
if [ -n "$idemp" ] && [ -f "$cache/$idemp" ]; then
  json_header; printf 'Idempotent-Replay: true\r\n\r\n'
  cat "$cache/$idemp"; exit 0
fi

# --- Ejecucion del procedimiento ---
case "$op" in
  sum) sym="+"; expr_bc="$a + $b" ;;
  sub) sym="-"; expr_bc="$a - $b" ;;
  mul) sym="*"; expr_bc="$a * $b" ;;
  div)
    if [ "$(echo "$b == 0" | bc)" -eq 1 ]; then
      printf 'Status: 422 Unprocessable Entity\r\n'; json_header; printf '\r\n'
      echo '{"error":"division entre cero"}'; exit 0
    fi
    sym="/"; expr_bc="$a / $b" ;;
  *)
    printf 'Status: 422 Unprocessable Entity\r\n'; json_header; printf '\r\n'
    echo "{\"error\":\"operacion no soportada: $op (use sum|sub|mul|div)\"}"; exit 0 ;;
esac

res=$(echo "scale=4; $expr_bc" | bc)
# Normalizar para JSON: .5 -> 0.5 ; -.5 -> -0.5
case "$res" in
  -.*) res="-0.${res#-.}" ;;
  .*)  res="0$res" ;;
esac

resp="{\"servicio\":\"calc\",\"op\":\"$op\",\"a\":$a,\"b\":$b,\"resultado\":$res,\"expr\":\"$a $sym $b = $res\"}"
[ -n "$idemp" ] && echo "$resp" > "$cache/$idemp"

json_header; printf '\r\n'
echo "$resp"
