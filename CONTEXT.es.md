# Contexto de tu empresa

**Sustituye este archivo** por el CONTEXT de la empresa que te hayan asignado:

- **Brasaland** — `CONTEXT-brasaland-briefing.md` (cadena de restaurantes de comida a la parrilla, Colombia + Florida)
- **TrackFlow** — `CONTEXT-trackflow-briefing.md` (última milla y almacén, México + España)
- **Nexova** — `CONTEXT-nexova-briefing.md` (consultoría de RR. HH. y adquisición de talento, Chile + Argentina)
- **HealthCore** — `CONTEXT-healthcore-briefing.md` (red de clínicas ambulatorias, EE.UU. + Reino Unido)

Tu instructor o los materiales del hito te indicarán el archivo CONTEXT correcto. Copia aquí su contenido para que todo el trabajo del proyecto y la asistencia de IA usen los mismos datos de dominio, nombres de campos y restricciones.

---

_Hasta que añadas tu contexto, mantén este placeholder para que la estructura del repositorio quede clara._

_These instructions are also available in [English](./CONTEXT.md)._


# Contexto Técnico: Validación de Incidentes

Este documento define la estructura técnica, restricciones de datos y los requisitos de lógica para el análisis del archivo de incidentes de la empresa.

---

## 📊 1. Estructura y Restricciones del CSV

El archivo de datos en bruto se encuentra en `data/raw/` y debe seguir estrictamente la siguiente estructura de columnas y formatos:

| Campo | Tipo | Requerido | Formato / Valores permitidos |
| :--- | :--- | :---: | :--- |
| `incident_id` | string | ✅ | ID único con formato `TRF-XXXXXX` (ej. `TRF-000001`) |
| `date` | string | ✅ | Fecha en formato ISO `YYYY-MM-DD` |
| `country` | string | ✅ | Solo valores `US` o `ES` |
| `customer_type` | string | ✅ | Solo valores `B2B` o `B2C` |
| `tracking_number` | string | ✅ | Texto, mínimo 8 caracteres |
| `carrier` | string | ✅ | Transportistas válidos según `CONTEXT-company.md` |
| `category` | string | ✅ | Categorías válidas según `CONTEXT-company.md` |
| `description` | string | ✅ | Texto libre, mínimo 5 caracteres |
| `status` | string | ✅ | Valores permitidos: `OPEN`, `CLOSED`, `DISCARDED` |
| `customer_email` | string | ✅ | Email con formato válido (ejemplo@dominio.com) |
| `satisfaction_score` | integer | ❌* | Entero del 1 al 5. **Requerido si `status` == `CLOSED`** |

> ⚠️ **Regla de Negocio Crítica:** Si el estado (`status`) de un incidente es `CLOSED`, el campo `satisfaction_score` pasa a ser **obligatorio**. Si no tiene valor en este escenario, el registro se marca como **inválido**.

---

## ⚙️ 2. Requisitos del Script de Validación (`analyze.py`)

El script de Python se ejecutará desde la consola pasando la ruta del archivo como argumento:
```bash
python analyze.py data/raw/nombre_del_fichero.csv