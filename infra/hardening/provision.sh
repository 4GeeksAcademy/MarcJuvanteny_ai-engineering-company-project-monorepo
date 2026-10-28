#!/usr/bin/env bash
# Endurecimiento del servidor de TrackFlow (Ubuntu 22.04/24.04).
# Informe y decisiones: Pasos/owasp-auditoria-hardening.md, sección "Endurecimiento".
#
# Idempotente: se puede correr N veces; cada paso comprueba antes de cambiar.
# Debe correr como root (una única vez por consola/cloud-init, ANTES de
# cerrar el acceso root por SSH).
#
#   OPS_SSH_PUBKEY="ssh-ed25519 AAAA... ana@trackflow" sudo -E ./provision.sh
#
# Variables:
#   OPS_USER        usuario de operación diaria, no root          (default: trackops)
#   OPS_SSH_PUBKEY  clave pública del operador. OBLIGATORIA si OPS_USER todavía
#                   no tiene authorized_keys: sin ella no se desactiva el login
#                   por contraseña/root (evita dejar el servidor sin acceso).
#   APP_USER        usuario de sistema que corre la app, sin login (default: trackflow)
#   SSH_PORT        puerto SSH                                     (default: 22)
#   ADMIN_CIDR      si se define, SSH solo se acepta desde ese rango (p. ej. la VPN)
set -euo pipefail

OPS_USER="${OPS_USER:-trackops}"
APP_USER="${APP_USER:-trackflow}"
SSH_PORT="${SSH_PORT:-22}"
ADMIN_CIDR="${ADMIN_CIDR:-}"
OPS_SSH_PUBKEY="${OPS_SSH_PUBKEY:-}"

APP_DIR=/opt/trackflow/app        # código: solo lectura para el usuario de la app
CONFIG_DIR=/etc/trackflow         # .env con secretos (API keys, JWT_SECRET_KEY, ...)
LOG_DIR=/var/log/trackflow        # logs: escribe la app, lee el operador
DATA_DIR=/var/lib/trackflow       # datos locales (TinyDB, uploads de RFP): solo la app

log() { printf '[provision] %s\n' "$*"; }

if [[ "$(id -u)" -ne 0 ]]; then
  echo "provision.sh debe correr como root" >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
if ! command -v ufw >/dev/null || ! command -v sshd >/dev/null || ! command -v sudo >/dev/null; then
  log "instalando openssh-server, ufw, sudo"
  apt-get update -qq
  apt-get install -y -qq openssh-server ufw sudo >/dev/null
fi

# --- 1. Usuarios ---------------------------------------------------------------------------
# Usuario de la app: de sistema, sin shell ni contraseña -- si el proceso se
# compromete, no hay login interactivo que reutilizar.
if ! id "$APP_USER" >/dev/null 2>&1; then
  log "creando usuario de sistema $APP_USER (sin login)"
  useradd --system --no-create-home --home-dir "$DATA_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

# Usuario de operación: login por clave, sin sudo total. Lee logs (grupo adm)
# y puede ejecutar SOLO los comandos de operación de sudoers.d/trackflow-ops.
if ! id "$OPS_USER" >/dev/null 2>&1; then
  log "creando usuario de operación $OPS_USER"
  useradd --create-home --shell /bin/bash "$OPS_USER"
  passwd --lock "$OPS_USER" >/dev/null  # sin contraseña: solo clave SSH
fi
usermod -aG adm "$OPS_USER"

OPS_HOME="$(getent passwd "$OPS_USER" | cut -d: -f6)"
install -d -m 700 -o "$OPS_USER" -g "$OPS_USER" "$OPS_HOME/.ssh"
AUTH_KEYS="$OPS_HOME/.ssh/authorized_keys"
touch "$AUTH_KEYS"
if [[ -n "$OPS_SSH_PUBKEY" ]] && ! grep -qxF "$OPS_SSH_PUBKEY" "$AUTH_KEYS"; then
  log "agregando clave pública a $AUTH_KEYS"
  printf '%s\n' "$OPS_SSH_PUBKEY" >>"$AUTH_KEYS"
fi
chown "$OPS_USER:$OPS_USER" "$AUTH_KEYS"
chmod 600 "$AUTH_KEYS"

if ! grep -qE '^(ssh-|ecdsa-|sk-)' "$AUTH_KEYS"; then
  echo "ABORTADO: $OPS_USER no tiene ninguna clave en $AUTH_KEYS." >&2
  echo "Desactivar root/contraseña ahora dejaría el servidor sin acceso. Definí OPS_SSH_PUBKEY." >&2
  exit 2
fi

SUDOERS=/etc/sudoers.d/trackflow-ops
log "escribiendo $SUDOERS (comandos de operación, sin sudo total)"
cat >"$SUDOERS.tmp" <<EOF
# Generado por infra/hardening/provision.sh -- mínimo privilegio para $OPS_USER.
# Nada de "ALL": solo operar el stack y el firewall en modo lectura.
# OJO: en sudoers "cmd arg *" exige al menos un argumento más (el espacio es
# literal), por eso la forma sin argumentos va listada aparte.
Cmnd_Alias TRACKFLOW_OPS = \\
    /usr/bin/docker compose -f $APP_DIR/docker-compose.yml ps, \\
    /usr/bin/docker compose -f $APP_DIR/docker-compose.yml logs *, \\
    /usr/bin/docker compose -f $APP_DIR/docker-compose.yml restart *, \\
    /usr/bin/docker compose -f $APP_DIR/docker-compose.yml up -d *, \\
    /usr/bin/systemctl status *, \\
    /usr/bin/journalctl, \\
    /usr/bin/journalctl *, \\
    /usr/sbin/ufw status, \\
    /usr/sbin/ufw status *
$OPS_USER ALL=(root) NOPASSWD: TRACKFLOW_OPS
EOF
visudo -cf "$SUDOERS.tmp" >/dev/null
install -m 440 -o root -g root "$SUDOERS.tmp" "$SUDOERS"
rm -f "$SUDOERS.tmp"

# --- 2. SSH --------------------------------------------------------------------------------
# "00-" para que gane: sshd usa el PRIMER valor que lee y los drop-ins se leen
# en orden alfabético -- Ubuntu cloud trae 50-cloud-init.conf con
# "PasswordAuthentication yes", que con otro nombre ganaría.
SSHD_DROPIN=/etc/ssh/sshd_config.d/00-trackflow-hardening.conf
log "escribiendo $SSHD_DROPIN"
install -d -m 755 /etc/ssh/sshd_config.d
cat >"$SSHD_DROPIN.tmp" <<EOF
# Generado por infra/hardening/provision.sh
Port $SSH_PORT
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitEmptyPasswords no
PubkeyAuthentication yes
AuthenticationMethods publickey
AllowUsers $OPS_USER
MaxAuthTries 3
LoginGraceTime 30
ClientAliveInterval 300
ClientAliveCountMax 2
X11Forwarding no
AllowAgentForwarding no
# "local": permite el túnel de ops a servicios en loopback (Flower, Qdrant),
# nunca exponer puertos del servidor hacia afuera (-R).
AllowTcpForwarding local
EOF
if ! grep -qE '^\s*Include\s+/etc/ssh/sshd_config\.d/\*\.conf' /etc/ssh/sshd_config; then
  log "agregando Include de sshd_config.d al principio de sshd_config"
  sed -i '1i Include /etc/ssh/sshd_config.d/*.conf' /etc/ssh/sshd_config
fi
mv "$SSHD_DROPIN.tmp" "$SSHD_DROPIN"
chmod 644 "$SSHD_DROPIN"
mkdir -p /run/sshd
sshd -t  # configuración inválida -> set -e corta ANTES de recargar
if command -v systemctl >/dev/null && systemctl is-active --quiet ssh 2>/dev/null; then
  systemctl reload ssh
fi

# --- 3. Permisos de carpetas -----------------------------------------------------------------
log "aplicando permisos de carpetas"
#   código   root:APP 750/640 -> la app lo lee, NO lo puede modificar (un RCE no persiste en el código)
#   config   root:APP 750/640 -> secretos legibles solo por la app; nunca world-readable
#   logs     APP:adm 2750/640 -> la app escribe; el operador (grupo adm) lee; nadie más
#   datos    APP:APP 700      -> solo la app
install -d -m 750 -o root -g "$APP_USER" /opt/trackflow "$APP_DIR" "$CONFIG_DIR"
install -d -m 2750 -o "$APP_USER" -g adm "$LOG_DIR"
install -d -m 700 -o "$APP_USER" -g "$APP_USER" "$DATA_DIR"

chown -R root:"$APP_USER" "$APP_DIR" "$CONFIG_DIR"
find "$APP_DIR" -type d -exec chmod 750 {} +
find "$APP_DIR" -type f -perm /111 -exec chmod 750 {} +
find "$APP_DIR" -type f ! -perm /111 -exec chmod 640 {} +
find "$CONFIG_DIR" -type f -exec chmod 640 {} +
find "$LOG_DIR" -type f -exec chmod 640 {} +
chown -R "$APP_USER":"$APP_USER" "$DATA_DIR"

# --- 4. Firewall -------------------------------------------------------------------------------
# Público: solo HTTPS (API + frontend detrás del reverse proxy) y SSH de ops.
# 80 queda abierto solo para redirigir a 443 y para el desafío ACME.
log "configurando ufw"
ufw --force reset >/dev/null
ufw default deny incoming >/dev/null
ufw default allow outgoing >/dev/null
if [[ -n "$ADMIN_CIDR" ]]; then
  ufw allow from "$ADMIN_CIDR" to any port "$SSH_PORT" proto tcp comment 'ssh ops' >/dev/null
else
  ufw limit "$SSH_PORT"/tcp comment 'ssh ops (rate-limited)' >/dev/null
fi
ufw allow 80/tcp comment 'http -> https redirect / ACME' >/dev/null
ufw allow 443/tcp comment 'https: api + frontend' >/dev/null
ufw --force enable >/dev/null

# Docker publica puertos con sus propias reglas iptables, POR DELANTE de ufw:
# un "8000:8000" en docker-compose quedaría abierto a internet aunque ufw lo
# niegue. Con "ip": "127.0.0.1" todo puerto publicado sin IP explícita queda en
# loopback, y solo el reverse proxy (80/443) los expone.
if [[ -d /etc/docker ]] || command -v dockerd >/dev/null; then
  log "fijando bind por defecto de Docker a 127.0.0.1 (/etc/docker/daemon.json)"
  install -d -m 755 /etc/docker
  python3 - <<'PY'
import json, pathlib
path = pathlib.Path("/etc/docker/daemon.json")
config = json.loads(path.read_text()) if path.exists() and path.read_text().strip() else {}
config["ip"] = "127.0.0.1"
path.write_text(json.dumps(config, indent=2) + "\n")
PY
  if command -v systemctl >/dev/null && systemctl is-active --quiet docker 2>/dev/null; then
    systemctl restart docker
  fi
fi

log "listo. Verificar con: sudo ./verify.sh"
