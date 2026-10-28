"""Hash de contraseñas (auditoría OWASP A02, `Pasos/owasp-auditoria-hardening.md`).

Antes: `sha256(salt:password)` de UNA pasada -- un hash rápido de propósito
general. Con los hashes en la mano (y `suppliers.json`, el store de
usuarios, está versionado en git), una GPU prueba miles de millones de
candidatos por segundo.

Ahora: `scrypt` (stdlib, `hashlib.scrypt`, sin dependencias nuevas), un KDF
con coste de memoria configurable, recomendado por OWASP Password Storage
Cheat Sheet. Formato: `scrypt$<n>$<r>$<p>$<salt_hex>$<hash_hex>`.

Compatibilidad: `verify_password` sigue aceptando el formato heredado
`sha256$<salt>$<hash>`, y `needs_rehash` permite que `authenticate_user`
lo actualice a scrypt en el primer login correcto -- las cuentas existentes
migran solas, sin forzar un reseteo.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

# OWASP Password Storage Cheat Sheet: N=2^17, r=8, p=1 (~128 MiB). Se usa
# N=2^15 (~32 MiB) para que un login no compita por memoria con el worker de
# Celery en el mismo host; sigue siendo órdenes de magnitud más caro que sha256.
SCRYPT_N = 2**15
SCRYPT_R = 8
SCRYPT_P = 1
_DKLEN = 32
_MAXMEM = 64 * 1024 * 1024


def _scrypt(password: str, salt: bytes, n: int, r: int, p: int) -> bytes:
    return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, dklen=_DKLEN, maxmem=_MAXMEM)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = _scrypt(password, salt, SCRYPT_N, SCRYPT_R, SCRYPT_P)
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt.hex()}${digest.hex()}"


def verify_password(plain_password: str, stored_hash: str) -> bool:
    if stored_hash.startswith("scrypt$"):
        parts = stored_hash.split("$")
        if len(parts) != 6:
            return False
        _, n, r, p, salt_hex, expected_hex = parts
        try:
            computed = _scrypt(plain_password, bytes.fromhex(salt_hex), int(n), int(r), int(p))
        except ValueError:
            return False
        return hmac.compare_digest(computed.hex(), expected_hex)

    if stored_hash.startswith("sha256$"):
        parts = stored_hash.split("$", 2)
        if len(parts) != 3:
            return False
        _, salt, expected_digest = parts
        computed_digest = hashlib.sha256(f"{salt}:{plain_password}".encode("utf-8")).hexdigest()
        return hmac.compare_digest(computed_digest, expected_digest)

    return False


def needs_rehash(stored_hash: str) -> bool:
    """`True` para el formato heredado o para un scrypt con parámetros
    más débiles que los actuales."""

    if not stored_hash.startswith("scrypt$"):
        return True
    parts = stored_hash.split("$")
    return len(parts) != 6 or (int(parts[1]), int(parts[2]), int(parts[3])) < (SCRYPT_N, SCRYPT_R, SCRYPT_P)
