# Telemetry Plan - TrackFlow

## Fase 3 - Estrategia de entrega

Esta fase define para cada evento si se procesa como stream o batch, en funcion de la urgencia de la decision de negocio que habilita.

### 3.1 Decision stream vs batch por evento

| event_type | Modo | Justificacion de negocio |
| --- | --- | --- |
| inbound_order_created | stream | Ana necesita visibilidad casi inmediata del volumen entrante para reasignar capacidad y personal del turno. |
| outbound_order_created | stream | El despacho impacta SLA de entrega; detectar caidas de ritmo en minutos evita incumplimientos. |
| stock_threshold_triggered | stream | Riesgo directo de rotura de stock; requiere alertado preventivo al cliente y comercial sin esperar corte por lotes. |
| direct_stock_edit_rejected | stream | Senal de posible incumplimiento operativo o de permisos; conviene intervenir rapido en el almacen afectado. |
| inventory_discrepancy_detected | stream | Una discrepancia puede comprometer decisiones de picking y promesa de stock; requiere accion inmediata de operaciones. |
| auth_login_attempted | batch | Volumen alto y decision no inmediata; sirve para tendencias de uso y capacidad por franja horaria. |
| auth_login_succeeded | batch | KPI de conversion de acceso para analitica de adopcion; no exige respuesta en tiempo real. |
| auth_login_failed | stream | Picos de fallo pueden indicar incidente de acceso o ataque de credenciales; requiere deteccion temprana. |
| session_expired | batch | Util para ajustar TTL y UX de sesion con analisis agregado diario/semanal. |
| protected_route_redirected | batch | Metrica de friccion de navegacion protegida, de naturaleza analitica. |
| route_changed | batch | Comportamiento de navegacion para optimizacion de IA/UX, no operativo en tiempo real. |
| page_load_completed | batch | Optimizacion de experiencia por tendencia de rendimiento, no decision minuto a minuto. |
| api_latency_recorded | stream | Degradaciones de latencia afectan operacion; se necesita deteccion y alerta rapida. |
| api_request_failed | stream | Errores de API impactan continuidad de trabajo del backoffice; requiere respuesta inmediata. |
| frontend_error_captured | stream | Errores no controlados pueden bloquear flujos criticos; conviene alertar al equipo tecnico rapido. |

### 3.2 Politica de throttle/debounce para eventos de alta frecuencia

Objetivo: reducir ruido y costo sin perder capacidad de decision.

| event_type | Riesgo de frecuencia | Estrategia | Regla recomendada |
| --- | --- | --- | --- |
| route_changed | Alto | debounce | Emitir solo si no hay otro cambio de ruta en 600 ms. |
| page_load_completed | Medio | throttle | Maximo 1 evento por ruta por sesion cada 15 s. |
| api_latency_recorded | Muy alto | muestreo + agregacion por ventana | Para endpoints no criticos: muestreo 20%. Para criticos de inventario: 100%. Agregar p50/p95/p99 cada 60 s por endpoint. |
| api_request_failed | Medio | sin debounce en error, deduplicacion corta | Emitir todos los fallos, pero deduplicar eventos identicos (endpoint+status+reason) en ventana de 10 s para evitar tormenta. |
| frontend_error_captured | Medio | deduplicacion por huella | Emitir primera ocurrencia inmediata y luego agrupar por stack_hash cada 5 min con contador. |
| auth_login_attempted | Alto | batch con agregacion | No emitir individual en tiempo real; agregar por minuto y por canal. |
| auth_login_failed | Medio | throttle adaptativo | Emitir individual hasta 5 fallos/min por usuario/sesion; luego agregar contador para evitar ruido. |

Notas:
- Los eventos obligatorios de inventario no se muestrean.
- En eventos stream, la deduplicacion solo evita duplicados tecnicos, no cambios reales de negocio.

### 3.3 Riesgos y exclusiones

#### Riesgos principales

1. Sobreinstrumentacion y costo
- Riesgo: eventos de navegacion y rendimiento pueden crecer rapidamente.
- Mitigacion: muestreo, agregacion por ventana y limites por sesion.

2. Falsos positivos operativos
- Riesgo: alertas de latencia o errores aislados pueden disparar ruido.
- Mitigacion: umbrales de alerta por persistencia (por ejemplo, 3 ventanas consecutivas degradadas).

3. Sesgo por perdidas de eventos cliente
- Riesgo: bloqueadores, cierres de pestana o red intermitente.
- Mitigacion: cola local corta con reintento y envio best-effort en unload.

4. Deriva de esquema
- Riesgo: introducir claves fuera de allowlist rompe comparabilidad historica.
- Mitigacion: validacion estricta en backend contra [event-shcemas.json](event-shcemas.json) con rechazo de claves no permitidas.

#### Exclusiones de datos por privacidad y costo

No se capturan en properties:
- email, telefono, direccion, nombre completo.
- datos del destinatario final de paquetes.
- password, tokens, cookies, cabeceras de autorizacion.
- payloads crudos de request/response.
- stack traces completos en cliente.

Sanitizacion aplicada:
- endpoint siempre en formato plantilla (sin ids ni query sensible).
- errores frontend con error_message_safe y stack_hash (sin stack completo).
- intentos de edicion directa con attempted_value_type y attempted_value_length, nunca valor crudo.

#### Eventos considerados y descartados

1. keystroke_captured
- Motivo de descarte: alto riesgo de privacidad y nulo valor para decision operativa.

2. raw_response_logged
- Motivo de descarte: costo alto y riesgo de fuga de datos.

3. full_stacktrace_uploaded
- Motivo de descarte: posible inclusion de datos sensibles; se sustituye por stack_hash.

4. clickstream_full_fidelity
- Motivo de descarte: volumen excesivo para valor incremental bajo frente a route_changed agregado.

### 3.4 Criterios de operacion

1. Cualquier evento con propiedades fuera de allowlist se rechaza.
2. Cualquier evento obligatorio sin campos minimos se rechaza.
3. Eventos stream criticos (inventario y fallos API) deben estar disponibles para alertado en menos de 1 minuto.
4. Eventos batch deben publicarse en lotes de 5 minutos para analitica operativa y de 24 horas para reporte ejecutivo.
