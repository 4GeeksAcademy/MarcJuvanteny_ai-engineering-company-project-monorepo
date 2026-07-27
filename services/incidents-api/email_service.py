from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

RESEND_API_URL = "https://api.resend.com/emails"


def _get_email_from() -> str:
    return os.environ.get("EMAIL_FROM", "TrackFlow <onboarding@resend.dev>")


def _build_reset_email_html(reset_link: str) -> str:
    return f"""
    <div style="font-family: -apple-system, Helvetica, Arial, sans-serif; max-width: 480px; margin: 0 auto; padding: 24px; color: #1a1a1a;">
      <h2 style="font-size: 20px; margin-bottom: 12px;">Restablece tu contraseña</h2>
      <p style="font-size: 15px; line-height: 1.5;">
        Recibimos una solicitud para restablecer la contraseña de tu cuenta en TrackFlow Backoffice.
      </p>
      <p style="margin: 24px 0;">
        <a href="{reset_link}"
           style="background:#0f6db6;color:#ffffff;padding:14px 22px;border-radius:8px;
                  text-decoration:none;display:inline-block;font-size:15px;font-weight:600;">
          Restablecer contraseña
        </a>
      </p>
      <p style="font-size: 13px; line-height: 1.5; color: #555;">
        Si el botón no funciona, copia y pega este enlace en tu navegador:<br />
        <a href="{reset_link}" style="color:#0f6db6; word-break: break-all;">{reset_link}</a>
      </p>
      <p style="font-size: 13px; line-height: 1.5; color: #555;">
        Si no solicitaste este cambio, puedes ignorar este email. El enlace expira pronto.
      </p>
    </div>
    """.strip()


def send_password_reset_email(to_email: str, reset_link: str) -> None:
    api_key = os.environ.get("RESEND_API_KEY")

    if not api_key:
        print(
            f"[email_service] RESEND_API_KEY no configurada; no se envio email real. "
            f"Enlace de restablecimiento para {to_email}: {reset_link}"
        )
        return

    payload = json.dumps(
        {
            "from": _get_email_from(),
            "to": [to_email],
            "subject": "Restablece tu contraseña - TrackFlow",
            "html": _build_reset_email_html(reset_link),
        }
    ).encode("utf-8")

    request = urllib.request.Request(
        RESEND_API_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            response.read()
    except urllib.error.URLError as exc:
        print(f"[email_service] No se pudo enviar el email de restablecimiento a {to_email}: {exc}")
