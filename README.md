# Práctica de laboratorio 1 — RPC con CGI y Shell script sobre nginx

**Sistemas Distribuidos — 8.º semestre, Ing. en Computación, ESIME-CU IPN**

Servicio remoto invocable por HTTP mediante el modelo **Common Gateway Interface (CGI)**,
usando **GNU bash** como lenguaje del procedimiento, **fcgiwrap** como puente FastCGI y
**nginx** como servidor web frontal.

> **Nota de plataforma:** el documento original de la práctica está escrito para
> Debian/Ubuntu (`apt`, usuario `www-data`, `sites-available`). Este repositorio está
> **adaptado a Fedora Server 44** (`dnf`, usuario `nginx`, `default.d/`, SELinux en
> *Enforcing*). Las diferencias se detallan más abajo.

---

## Arquitectura y mapeo a los cinco componentes de RPC

```
  curl  --HTTP-->  nginx  --FastCGI (socket Unix)-->  fcgiwrap  --fork/exec-->  *.cgi (bash)
 cliente          gateway                             runtime                  procedimiento
```

| Componente RPC | Realización en esta práctica |
|---|---|
| **Cliente** | `curl` (o navegador) invocando la URL `/rpc/saludo.cgi`. |
| **Stub del cliente** | `libcurl`: arma la petición HTTP, codifica `QUERY_STRING`/cuerpo y cabeceras. |
| **RPC runtime** | **nginx + fcgiwrap**: gestionan TCP, FastCGI, socket Unix y variables CGI. |
| **Stub del servidor** | Primeras líneas del `.cgi`: parseo de variables CGI -> variables bash (unmarshalling). |
| **Servidor** | Cuerpo del script que calcula la respuesta y la emite por `stdout`. |

---

## Estructura del repositorio

```
practica1-rpc-cgi/
├── README.md
├── install.sh                 # Instalación reproducible (Fedora)
├── .gitignore
├── cgi-bin/
│   ├── saludo.cgi             # Procedimiento remoto base (5.3 del documento)
│   └── calc.cgi               # Reto de extensión: multi-operación + idempotencia
├── nginx/
│   └── rpc-cgi.conf           # location /rpc/ -> va en /etc/nginx/default.d/
└── selinux/
    └── nginx_fcgiwrap.te      # Módulo de política SELinux (permite connectto)
```

---

## Prerrequisitos

- Fedora Server 36 en adelante (probado en **Fedora 44**).
- Usuario con privilegios `sudo`.
- Paquetes: `nginx`, `fcgiwrap`, `fcgi`, `bc`, `curl`, `jq`,
  `policycoreutils-python-utils` (para `semanage`/`audit2allow`).

---

## Instalación (adaptada a Fedora)

Puedes ejecutar `./install.sh` (recomendado) o seguir los pasos manualmente:

### 1. Instalar paquetes
```bash
sudo dnf install -y nginx fcgiwrap fcgi bc curl jq policycoreutils-python-utils
sudo systemctl enable --now nginx
```

### 2. Activar fcgiwrap (socket-activation de systemd)
En Fedora el paquete usa **units plantilla**; se activa por usuario del servidor web:
```bash
sudo systemctl enable --now fcgiwrap@nginx.socket
```
El socket queda en `/run/fcgiwrap/fcgiwrap-nginx.sock`, propiedad de `nginx`.

### 3. SELinux (dos ajustes necesarios en *Enforcing*)
```bash
# (a) Permitir que nginx escriba en el archivo del socket
sudo semanage fcontext -a -t httpd_var_run_t '/run/fcgiwrap(/.*)?'
sudo restorecon -Rv /run/fcgiwrap

# (b) Permitir que nginx (httpd_t) haga connectto al proceso fcgiwrap (unconfined_service_t)
sudo semodule -i selinux/nginx_fcgiwrap.pp     # compilar antes si solo tienes el .te (ver abajo)
```
Para compilar el módulo desde el `.te`:
```bash
checkmodule -M -m -o nginx_fcgiwrap.mod selinux/nginx_fcgiwrap.te
semodule_package -o nginx_fcgiwrap.pp -m nginx_fcgiwrap.mod
sudo semodule -i nginx_fcgiwrap.pp
```

### 4. Desplegar scripts CGI
```bash
sudo mkdir -p /usr/lib/cgi-bin/rpc
sudo cp cgi-bin/*.cgi /usr/lib/cgi-bin/rpc/
sudo chmod +x /usr/lib/cgi-bin/rpc/*.cgi
sudo chown nginx:nginx /usr/lib/cgi-bin/rpc/*.cgi
```

### 5. Configurar nginx
En Fedora **no existe `sites-available`**; el archivo se incluye desde el `server` de
puerto 80 vía `/etc/nginx/default.d/`:
```bash
sudo cp nginx/rpc-cgi.conf /etc/nginx/default.d/rpc-cgi.conf
sudo nginx -t
sudo systemctl reload nginx
```

---

## Uso / pruebas

### Procedimiento `saludo`
```bash
# GET (texto plano)
curl -s 'http://localhost/rpc/saludo.cgi?nombre=Mike'
# -> Hola, Mike - peticion desde ::1

# POST
curl -s -X POST -d 'nombre=ESIME' http://localhost/rpc/saludo.cgi

# JSON (negociación de contenido por cabecera Accept)
curl -s -H 'Accept: application/json' \
     'http://localhost/rpc/saludo.cgi?nombre=Profesor' | jq .
```

### Reto — servicio `calc` (multi-operación + idempotencia)
Operaciones: `sum | sub | mul | div` · Parámetros: `op`, `a`, `b`
```bash
curl -s 'http://localhost/rpc/calc.cgi?op=sum&a=3&b=4'     # 7
curl -s 'http://localhost/rpc/calc.cgi?op=div&a=5&b=4'     # 1.2500
curl -s 'http://localhost/rpc/calc.cgi?op=div&a=5&b=0'     # 422 division entre cero
curl -s 'http://localhost/rpc/calc.cgi?op=sum&a=abc&b=3'   # 400 validación numérica

# Idempotencia: la misma Idempotency-Key devuelve la respuesta cacheada
curl -s -D - -H 'Idempotency-Key: demo-1' 'http://localhost/rpc/calc.cgi?op=mul&a=6&b=7'
curl -s -D - -H 'Idempotency-Key: demo-1' 'http://localhost/rpc/calc.cgi?op=mul&a=6&b=7'
#   -> 2do intento incluye cabecera "Idempotent-Replay: true"
```

---

## Semántica de invocación

- **Por defecto: *at-most-once*** — HTTP/CGI sin reintentos; cada petición produce a lo
  sumo una ejecución del procedimiento.
- Con reintentos del cliente y **`Idempotency-Key`** (en `calc.cgi`) se **aproxima
  *exactly-once*** para el efecto observable: el cálculo ocurre una vez y los reintentos
  reciben la respuesta cacheada.

---

## Notas de seguridad

- `calc.cgi` valida la operación por **lista blanca** y `a`/`b` por **regex numérica**
  (`^-?[0-9]+(\.[0-9]+)?$`) para evitar inyección en `bc`.
- **Pendiente de endurecer:** la `Idempotency-Key` se usa como nombre de archivo; conviene
  sanearla (`[A-Za-z0-9._-]`) o hashearla para evitar *path traversal*.
- La construcción de JSON por concatenación puede romperse con comillas en la entrada;
  para producción usar `jq -n --arg`.

---

## Solución de problemas

| Síntoma | Causa | Solución |
|---|---|---|
| `502 Bad Gateway` + `connect() ... (13: Permission denied)` en `error.log` | SELinux bloquea `connectto` al socket | Instalar el módulo `nginx_fcgiwrap.pp` (paso 3b) |
| `502 Bad Gateway` + `(2: No such file or directory)` | Socket de fcgiwrap no activo | `sudo systemctl enable --now fcgiwrap@nginx.socket` |
| El script siempre responde el error de validación | Parámetros no llegan / script truncado al pegar | Verificar con `bash -n` y `bash -x`; reinstalar el archivo |

Comandos de diagnóstico:
```bash
sudo tail -f /var/log/nginx/error.log
sudo journalctl -u fcgiwrap@nginx.service -f
sudo ausearch -m avc -ts recent
```
