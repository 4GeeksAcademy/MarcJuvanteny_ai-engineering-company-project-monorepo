# Registro de ordenes

## 2026-08-10

1. Solicitud: Revisar la aplicacion Next.js e identificar al menos dos componentes o rutas candidatas a Lazy Loading. Documentar razon y justificar por que diferir la carga.
Estado: completada
Artefacto: Pasos/lazy-loading-candidatos-nextjs.md

2. Solicitud: Implementar Lazy Loading para los componentes candidatos usando next/dynamic o React.lazy.
Estado: completada
Artefactos: uis/website/src/app/page.tsx, uis/website/src/app/application/page.tsx

3. Solicitud: Revisar componentes en busca de calculos costosos e identificar al menos una oportunidad de useMemo con dependencias bien definidas.
Estado: completada
Artefactos: uis/backoffice/src/components/incidents-management-panel.tsx, Pasos/usememo-oportunidad-incidents-panel.md

4. Solicitud: Implementar la optimizacion con useMemo evitando calculos triviales.
Estado: completada
Artefactos: uis/backoffice/src/components/incidents-management-panel.tsx, Pasos/usememo-oportunidad-incidents-panel.md

5. Solicitud: Listar todos los endpoints FastAPI y evaluar coste, frecuencia de llamada y frecuencia de cambio de datos subyacentes.
Estado: completada
Artefacto: Pasos/analisis-endpoints-fastapi-coste-frecuencia.md

6. Solicitud: Identificar al menos dos endpoints que cumplan criterios de coste + frecuencia + estabilidad para caching.
Estado: completada
Artefacto: Pasos/candidatos-caching-endpoints.md

7. Solicitud: Implementar caching para endpoints candidatos usando cache en memoria con TTL e invalidacion.
Estado: completada
Artefactos: services/incidents-api/main.py, Pasos/implementacion-caching-endpoints.md

8. Solicitud: Implementar invalidacion de cache cuando cambien los datos subyacentes (operaciones de escritura).
Estado: completada
Artefactos: services/incidents-api/main.py, Pasos/implementacion-caching-endpoints.md
