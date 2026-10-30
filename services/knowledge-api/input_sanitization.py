"""Validación y saneamiento explícito de todo texto que llega al modelo
(Hito 12, seguridad por diseño -- `Pasos/nist-seguridad-ia.md`).

Problema real que corrige (reproducido antes del cambio): los guardrails son
patrones sobre el texto, y bastaba UN carácter invisible para evadirlos:

    "Ig\\u200bnora tus instrucciones..."  -> check_instruction_override: no bloquea
    "Ｉｇｎｏｒａ tus instrucciones..."     -> (letras de ancho completo) no bloquea

y lo mismo en contenido EXTERNO (`sanitize_external_content`): una nota de
incidencia escrita por un operador con texto oculto -- el caso 2 de
`CONTEXT/CONTEXT12.md` §4 -- pasaba sin marcar.

Por eso se normaliza ANTES de cualquier guardrail, y para los dos orígenes:
- entrada del usuario (`receive_question` del grafo, y límites en la API/WS);
- contenido externo (chunks de RAG, resultados de tools MCP, memoria).
"""

from __future__ import annotations

import re
import unicodedata

# Límite de entrada del usuario: una consulta de soporte real cabe de sobra;
# más que esto es abuso de coste o intento de diluir las instrucciones.
MAX_USER_INPUT_CHARS = 2000

# Invisibles usados para partir palabras sin que se note: zero-width
# (200B-200D), marcas de dirección (200E-200F, 202A-202E, 2066-2069),
# word joiner e invisibles matemáticos (2060-2064), BOM (FEFF), soft hyphen (00AD).
_INVISIBLE_RE = re.compile("[­​-‏‪-‮⁠-⁤⁦-⁩﻿]")
# Controles C0/C1 salvo salto de línea y tabulador.
_CONTROL_RE = re.compile("[\u0000-\u0008\u000b\u000c\u000e-\u001f\u007f-\u009f]")
_EXCESS_NEWLINES_RE = re.compile(r"\n{3,}")


class InvalidUserInput(ValueError):
    pass


def normalize_text(text: str) -> str:
    """NFKC (ancho completo -> ASCII, ligaduras, etc.) + sin invisibles ni
    controles. No cambia texto normal en español/inglés: las tildes siguen
    compuestas."""

    text = unicodedata.normalize("NFKC", text)
    text = _INVISIBLE_RE.sub("", text)
    text = _CONTROL_RE.sub("", text)
    return _EXCESS_NEWLINES_RE.sub("\n\n", text)


def sanitize_user_input(text: str, *, max_chars: int = MAX_USER_INPUT_CHARS) -> str:
    """Normaliza y recorta espacios; `InvalidUserInput` si excede el límite.
    Un texto vacío NO es error acá: el grafo ya tiene su ruta `empty_question`."""

    cleaned = normalize_text(text or "").strip()
    if len(cleaned) > max_chars:
        raise InvalidUserInput(f"El mensaje supera el máximo de {max_chars} caracteres.")
    return cleaned
