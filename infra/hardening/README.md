# `infra/hardening` — endurecimiento del servidor de TrackFlow

Baseline de servidor/red de la auditoría de seguridad (`CONTEXT/CONTEXT11.md` §7).
Informe completo, decisiones y evidencia: [`Pasos/owasp-auditoria-hardening.md`](../../Pasos/owasp-auditoria-hardening.md).

| Archivo | Qué hace |
| --- | --- |
| `provision.sh` | Idempotente, como root: usuario de operación `trackops` (no root, solo clave SSH, sudo limitado a comandos de operación), usuario de servicio `trackflow` (sin login), SSH sin root ni contraseña, permisos de carpetas, `ufw` (solo 22/80/443), Docker publicando en `127.0.0.1` |
| `verify.sh` | Solo lectura: un PASS/FAIL por control; `exit 1` si alguno falla |
| `nginx-trackflow.conf` | Reverse proxy TLS (única puerta pública): 80→443, TLS 1.2/1.3, HSTS, cabeceras de seguridad, SSE y WebSocket |

## Uso

```bash
# 1. Desde la consola del proveedor (o cloud-init), como root, ANTES de cerrar root por SSH:
OPS_SSH_PUBKEY="ssh-ed25519 AAAA... ana@trackflow" ./provision.sh
#    opcional: ADMIN_CIDR=10.8.0.0/24 (SSH solo desde la VPN), SSH_PORT, OPS_USER, APP_USER

# 2. Probar el acceso nuevo en OTRA terminal antes de cerrar la sesión actual:
ssh trackops@<servidor>

# 3. Verificar (también sirve como chequeo periódico):
sudo ./verify.sh
```

`provision.sh` **aborta** si `trackops` no tiene ninguna clave en
`authorized_keys`, para no desactivar root/contraseña y dejar el servidor sin acceso.

## Layout de carpetas

| Ruta | Dueño | Modo | Por qué |
| --- | --- | --- | --- |
| `/opt/trackflow/app` | `root:trackflow` | 750 / 640 | Código: la app lo lee, **no** lo puede modificar (un RCE no persiste en el código) |
| `/etc/trackflow` | `root:trackflow` | 750 / 640 | `.env` con secretos (API keys del LLM, `JWT_SECRET_KEY`, tokens MCP): legibles solo por la app, nunca por "otros" ni por el operador |
| `/var/log/trackflow` | `trackflow:adm` | 2750 / 640 | Logs: la app escribe; el operador (grupo `adm`) lee |
| `/var/lib/trackflow` | `trackflow:trackflow` | 700 | Datos locales (TinyDB, PDFs de RFP subidos) |

## Notas

- **Docker vs. ufw**: Docker publica puertos con reglas iptables propias, *por delante* de
  ufw. Por eso `provision.sh` fija `"ip": "127.0.0.1"` en `/etc/docker/daemon.json`, y
  `docker-compose.yml` liga Redis, Flower y Qdrant a `127.0.0.1` de forma explícita.
- `ufw --force reset` en cada corrida: las reglas del firewall son exactamente las de
  este script. Reglas manuales extra se pierden; deben añadirse aquí.
- Flower y Qdrant se consultan por túnel: `ssh -L 5555:127.0.0.1:5555 trackops@<servidor>`
  (`AllowTcpForwarding local`).
