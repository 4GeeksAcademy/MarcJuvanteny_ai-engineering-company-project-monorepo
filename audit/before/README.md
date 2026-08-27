# audit/before — Medición inicial (Lighthouse)

Capturas e informes de Lighthouse **antes** de aplicar correcciones.

## Qué hay que capturar

### Web corporativa (`uis/website`) — escritorio y móvil

| Página | Modo | Performance | Accessibility | Best Practices | SEO |
|---|---|---|---|---|---|
| `/` (inicio) | escritorio | | | | |
| `/` (inicio) | móvil | | | | |
| `/application` | escritorio | | | | |
| `/application` | móvil | | | | |

### Backoffice (`uis/backoffice`)

| Página | Modo | Performance | Accessibility | Best Practices | SEO |
|---|---|---|---|---|---|
| `/` (dashboard principal) | escritorio | | | | |

## Cómo generarlo

Este entorno (Codespace) **no tiene Chrome instalado**, así que Lighthouse debe
ejecutarse desde una máquina con Chrome:

```bash
# 1. Web corporativa
cd uis/website && npm install && npm run build && npm start   # http://localhost:3000

# 2. Backoffice (necesita la API de incidentes en :8001 y sus vars de entorno)
cd uis/backoffice && cp .env.local.example .env.local && npm install && npm run build && npm start

# 3. Lighthouse (Chrome DevTools > Lighthouse, o CLI)
npx lighthouse http://localhost:3000/ --preset=desktop --view
npx lighthouse http://localhost:3000/ --form-factor=mobile --view
npx lighthouse http://localhost:3000/application --preset=desktop --view
npx lighthouse http://localhost:3000/application --form-factor=mobile --view
npx lighthouse http://localhost:3001/ --preset=desktop --view   # backoffice
```

Guardar aquí las capturas de pantalla (`website-home-desktop.png`, etc.) y
rellenar las tablas de arriba antes de hacer commit.
