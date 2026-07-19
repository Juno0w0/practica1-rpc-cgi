#!/usr/bin/env bash
# install.sh — Despliegue reproducible de la Práctica 1 (RPC con CGI/bash sobre nginx)
# Plataforma objetivo: Fedora Server 36+ (probado en Fedora 44), SELinux Enforcing.
# Ejecutar desde la raíz del repositorio: ./install.sh
set -euo pipefail

RED=/usr/lib/cgi-bin/rpc
HERE="$(cd "$(dirname "$0")" && pwd)"

echo "==> 1. Instalando paquetes"
sudo dnf install -y nginx fcgiwrap fcgi bc curl jq policycoreutils-python-utils \
                    checkpolicy policycoreutils
sudo systemctl enable --now nginx

echo "==> 2. Activando fcgiwrap (socket-activation para el usuario nginx)"
sudo systemctl enable --now fcgiwrap@nginx.socket

echo "==> 3. SELinux: etiqueta del socket + módulo connectto"
sudo semanage fcontext -a -t httpd_var_run_t '/run/fcgiwrap(/.*)?' 2>/dev/null || true
sudo restorecon -Rv /run/fcgiwrap || true

# Compilar e instalar el módulo de política a partir del .te versionado
tmpd="$(mktemp -d)"
checkmodule -M -m -o "$tmpd/nginx_fcgiwrap.mod" "$HERE/selinux/nginx_fcgiwrap.te"
semodule_package -o "$tmpd/nginx_fcgiwrap.pp" -m "$tmpd/nginx_fcgiwrap.mod"
sudo semodule -i "$tmpd/nginx_fcgiwrap.pp"
rm -rf "$tmpd"

echo "==> 4. Desplegando scripts CGI en $RED"
sudo mkdir -p "$RED"
sudo cp "$HERE"/cgi-bin/*.cgi "$RED"/
sudo chmod +x "$RED"/*.cgi
sudo chown nginx:nginx "$RED"/*.cgi

echo "==> 5. Configurando nginx (default.d)"
sudo cp "$HERE/nginx/rpc-cgi.conf" /etc/nginx/default.d/rpc-cgi.conf
sudo nginx -t
sudo systemctl reload nginx

echo "==> Listo. Prueba rápida:"
curl -s 'http://localhost/rpc/saludo.cgi?nombre=Instalador' || true
echo
curl -s 'http://localhost/rpc/calc.cgi?op=sum&a=3&b=4' || true
echo
