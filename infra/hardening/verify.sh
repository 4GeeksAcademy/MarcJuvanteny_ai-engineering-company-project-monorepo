#!/usr/bin/env bash
# Verificación del endurecimiento (SOLO LECTURA: no cambia nada).
# Una línea PASS/FAIL por control; exit 1 si alguno falla.
# Correr como root para poder leer sshd -T, ufw y /etc/trackflow.
#
#   sudo ./verify.sh            # antes y después de provision.sh -> evidencia
set -uo pipefail

OPS_USER="${OPS_USER:-trackops}"
APP_USER="${APP_USER:-trackflow}"
SSH_PORT="${SSH_PORT:-22}"
FAILURES=0

check() {  # check "<descripción>" <comando...>
  local description="$1"
  shift
  if "$@" >/dev/null 2>&1; then
    printf 'PASS  %s\n' "$description"
  else
    printf 'FAIL  %s\n' "$description"
    FAILURES=$((FAILURES + 1))
  fi
}

sshd_value() { mkdir -p /run/sshd; sshd -T 2>/dev/null | awk -v k="$1" '$1 == k { $1 = ""; sub(/^ /, ""); print; exit }'; }
mode_of() { stat -c '%a' "$1" 2>/dev/null; }
owner_of() { stat -c '%U:%G' "$1" 2>/dev/null; }

echo "== Usuarios"
check "existe el usuario de operación $OPS_USER" id "$OPS_USER"
check "$OPS_USER no es root (uid != 0)" bash -c "id -u $OPS_USER && test \"\$(id -u $OPS_USER)\" != 0"
check "root es la ÚNICA cuenta con uid 0" test "$(awk -F: '$3 == 0' /etc/passwd | wc -l)" -eq 1
check "$OPS_USER no tiene sudo total (no está en el grupo sudo)" bash -c "id $OPS_USER && ! id -nG $OPS_USER | tr ' ' '\n' | grep -qx sudo"
check "$OPS_USER tiene contraseña bloqueada (solo clave SSH)" bash -c "passwd -S $OPS_USER | awk '{print \$2}' | grep -qx L"
check "$OPS_USER tiene authorized_keys 600" bash -c "test \"\$(stat -c %a \$(getent passwd $OPS_USER | cut -d: -f6)/.ssh/authorized_keys)\" = 600"
check "sudoers de ops existe y es válido" visudo -cf /etc/sudoers.d/trackflow-ops
check "sudoers de ops no concede ALL" bash -c "test -f /etc/sudoers.d/trackflow-ops && ! grep -E 'NOPASSWD:\s*ALL|\(ALL(:ALL)?\)\s*ALL' /etc/sudoers.d/trackflow-ops"
check "usuario de la app $APP_USER sin shell de login" bash -c "getent passwd $APP_USER | cut -d: -f7 | grep -Eq '(nologin|false)$'"

echo "== SSH (configuración efectiva, sshd -T)"
check "PermitRootLogin no" test "$(sshd_value permitrootlogin)" = "no"
check "PasswordAuthentication no" test "$(sshd_value passwordauthentication)" = "no"
check "KbdInteractiveAuthentication no" test "$(sshd_value kbdinteractiveauthentication)" = "no"
check "AllowUsers = $OPS_USER" test "$(sshd_value allowusers)" = "$OPS_USER"
check "MaxAuthTries <= 3" test "$(sshd_value maxauthtries)" -le 3
check "X11Forwarding no" test "$(sshd_value x11forwarding)" = "no"
check "AllowTcpForwarding solo local" test "$(sshd_value allowtcpforwarding)" = "local"

echo "== Permisos de carpetas"
check "/opt/trackflow/app root:$APP_USER 750 (código no modificable por la app)" \
  test "$(owner_of /opt/trackflow/app) $(mode_of /opt/trackflow/app)" = "root:$APP_USER 750"
check "/etc/trackflow root:$APP_USER 750 (secretos)" \
  test "$(owner_of /etc/trackflow) $(mode_of /etc/trackflow)" = "root:$APP_USER 750"
check "ningún archivo de /etc/trackflow es legible por 'otros'" \
  bash -c "test -d /etc/trackflow && test -z \"\$(find /etc/trackflow -type f -perm /o+rwx)\""
check "/var/log/trackflow $APP_USER:adm 2750" \
  test "$(owner_of /var/log/trackflow) $(mode_of /var/log/trackflow)" = "$APP_USER:adm 2750"
check "/var/lib/trackflow $APP_USER:$APP_USER 700" \
  test "$(owner_of /var/lib/trackflow) $(mode_of /var/lib/trackflow)" = "$APP_USER:$APP_USER 700"
check "la app no puede escribir en el código" bash -c "id $APP_USER && ! sudo -u $APP_USER test -w /opt/trackflow/app"

echo "== Firewall (ufw)"
UFW_STATUS="$(ufw status verbose 2>/dev/null || true)"
check "ufw activo" grep -q '^Status: active' <<<"$UFW_STATUS"
check "entrante denegado por defecto" grep -q 'Default: deny (incoming)' <<<"$UFW_STATUS"
check "abiertos SOLO $SSH_PORT, 80 y 443" bash -c "
  ports=\$(ufw status 2>/dev/null | awk 'NR>4 && \$2 ~ /ALLOW|LIMIT/ {split(\$1,a,\"/\"); print a[1]}' | sort -u | tr '\n' ' ')
  test \"\$ports\" = \"\$(printf '%s\n' $SSH_PORT 80 443 | sort -u | tr '\n' ' ')\""
if [[ -d /etc/docker ]]; then
  check "Docker publica en 127.0.0.1 por defecto (no salta ufw)" \
    python3 -c "import json,sys; sys.exit(json.load(open('/etc/docker/daemon.json')).get('ip') != '127.0.0.1')"
fi

echo
if [[ "$FAILURES" -eq 0 ]]; then
  echo "RESULTADO: todos los controles PASS"
else
  echo "RESULTADO: $FAILURES control(es) FAIL"
fi
exit $((FAILURES > 0))
