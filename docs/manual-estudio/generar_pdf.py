"""Genera manual-estudio-trackflow.pdf a partir de manual-estudio-trackflow.md.

Convierte el Markdown a HTML (tablas, bloques de código, enlaces internos),
dibuja los diagramas Mermaid en un Chromium sin cabeza (Playwright) y lo
imprime en A4. No toca ningún entorno del proyecto:

    cd docs/manual-estudio
    uv run --no-project --with markdown-it-py --with playwright python generar_pdf.py
    # la primera vez, si Playwright no encuentra navegador:
    uv run --with playwright playwright install chromium
    # o reutilizar uno ya instalado:
    CHROMIUM_PATH=~/.cache/ms-playwright/chromium-1243/chrome-linux64/chrome uv run ...

Si se edita el manual por partes (carpeta partes/), primero:
    cat partes/0*.md > manual-estudio-trackflow.md
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from markdown_it import MarkdownIt
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "manual-estudio-trackflow.md"
HTML_OUT = HERE / "manual-estudio-trackflow.html"
PDF_OUT = HERE / "manual-estudio-trackflow.pdf"

MERMAID_CDN = "https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"

CSS = """
@page { size: A4; margin: 18mm 15mm 18mm 15mm; }
:root { --ink:#1b2430; --muted:#5b6675; --line:#d9dee6; --accent:#0f6db6; --soft:#eef5fc; --code:#f5f7fa; }
* { box-sizing: border-box; }
body { font-family: "DejaVu Sans", "Segoe UI", Arial, sans-serif; color: var(--ink); font-size: 10.2pt; line-height: 1.5; }
h1 { font-size: 24pt; color: var(--accent); margin: 0 0 6pt; }
h2 { font-size: 16pt; color: var(--accent); border-bottom: 2px solid var(--accent); padding-bottom: 3pt; margin-top: 18pt; page-break-before: always; }
h1 + p, h2:first-of-type { page-break-before: avoid; }
h3 { font-size: 12.5pt; margin-top: 14pt; color: #12385e; }
h4 { font-size: 11pt; margin-top: 12pt; color: #12385e; }
p, li { orphans: 3; widows: 3; }
a { color: var(--accent); text-decoration: none; }
code { font-family: "DejaVu Sans Mono", Consolas, monospace; font-size: 8.8pt; background: var(--code); padding: 0 2px; border-radius: 3px; }
pre { background: var(--code); border: 1px solid var(--line); border-radius: 6px; padding: 8px 10px; overflow-x: auto; white-space: pre-wrap; word-break: break-word; page-break-inside: avoid; }
pre code { background: none; padding: 0; font-size: 8.4pt; }
table { border-collapse: collapse; width: 100%; margin: 8pt 0; font-size: 8.8pt; page-break-inside: auto; }
tr { page-break-inside: avoid; }
th, td { border: 1px solid var(--line); padding: 4px 6px; vertical-align: top; text-align: left; }
th { background: var(--soft); }
blockquote { margin: 8pt 0; padding: 6pt 10pt; border-left: 4px solid var(--accent); background: var(--soft); border-radius: 0 6px 6px 0; }
blockquote p { margin: 3pt 0; }
hr { border: none; border-top: 1px solid var(--line); margin: 14pt 0; }
.mermaid { text-align: center; margin: 10pt 0; page-break-inside: avoid; }
.mermaid svg { max-width: 100%; height: auto; }
"""


def convert(md_text: str) -> str:
    # CommonMark (como GitHub): listas anidadas con 2 espacios, tablas dentro de
    # listas, HTML en línea (anclas del diccionario).
    body = MarkdownIt("commonmark", {"html": True}).enable("table").render(md_text)
    # ```mermaid -> <div class="mermaid"> para que Mermaid lo dibuje.
    body = re.sub(
        r'<pre><code class="language-mermaid">(.*?)</code></pre>',
        lambda m: f'<div class="mermaid">{m.group(1)}</div>',
        body,
        flags=re.S,
    )
    return f"""<!doctype html>
<html lang="es"><head><meta charset="utf-8"><title>Manual de estudio de TrackFlow</title>
<style>{CSS}</style>
<script src="{MERMAID_CDN}"></script>
</head><body>
{body}
<script>
  mermaid.initialize({{ startOnLoad: false, theme: "default", securityLevel: "loose", themeVariables: {{ fontSize: "15px" }},
                       flowchart: {{ useMaxWidth: true, htmlLabels: true }}, sequence: {{ useMaxWidth: true }} }});
  mermaid.run({{ querySelector: ".mermaid" }})
    .then(() => {{ window.__mermaidDone = "ok"; }})
    .catch((e) => {{ window.__mermaidDone = "error: " + e; }});
</script>
</body></html>"""


def main() -> None:
    HTML_OUT.write_text(convert(SOURCE.read_text(encoding="utf-8")), encoding="utf-8")
    with sync_playwright() as pw:
        # CHROMIUM_PATH permite reutilizar un Chromium ya instalado si la versión
        # de Playwright espera otra build distinta de la que hay en caché.
        executable = os.environ.get("CHROMIUM_PATH") or None
        browser = pw.chromium.launch(executable_path=executable)
        page = browser.new_page()
        page.goto(HTML_OUT.as_uri(), wait_until="networkidle")
        page.wait_for_function("window.__mermaidDone !== undefined", timeout=120_000)
        status = page.evaluate("window.__mermaidDone")
        total = page.evaluate("document.querySelectorAll('.mermaid').length")
        # Un diagrama con sintaxis inválida se "dibuja" igual, como imagen de
        # "Syntax error": se detecta por su texto, no por la existencia del SVG.
        broken = page.evaluate(
            "[...document.querySelectorAll('.mermaid')].map((d, i) => /Syntax error|Parse error/i.test(d.textContent) ? i : -1).filter(i => i >= 0)"
        )
        print(f"Mermaid: {status} — {total - len(broken)}/{total} diagramas correctos")
        if broken:
            raise SystemExit(f"Diagramas Mermaid con error de sintaxis (índice en orden de aparición): {broken}")
        page.pdf(
            path=str(PDF_OUT),
            format="A4",
            print_background=True,
            display_header_footer=True,
            header_template="<div></div>",
            footer_template=(
                '<div style="font-size:8px;width:100%;text-align:center;color:#888;">'
                "Manual de estudio de TrackFlow — página <span class='pageNumber'></span> de "
                "<span class='totalPages'></span></div>"
            ),
            margin={"top": "16mm", "bottom": "18mm", "left": "14mm", "right": "14mm"},
        )
        browser.close()
    print(f"PDF: {PDF_OUT}")


if __name__ == "__main__":
    main()
