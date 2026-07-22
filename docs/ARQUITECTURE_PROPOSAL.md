# Propuesta de arquitectura de backend

Somos una empresa de logística y paquetería. El backend lo usará sobre todo personal interno (operaciones y almacén) para tracking de paquetes, inventario, rutas y facturación. Equipo pequeño (1-4 devs), poca experiencia en sistemas distribuidos, tráfico moderado y constante.

---

## 1. Patrón elegido: Monolito Modular

- **No microservicios**: el equipo es chico y sin experiencia distribuida, y no hay señal de que necesitemos escalar una parte del sistema por separado. Los microservicios traerían problemas (transacciones entre servicios, monitoreo distribuido) que hoy no sabríamos resolver bien.
- **No monolito sin estructura**: ya hay varios temas de negocio bien distintos (tracking, almacén, rutas, facturación); sin separación interna, el código se desordena rápido.
- **Monolito Modular**: un solo despliegue (simple para nuestro tamaño), pero el código separado por dominio de negocio dentro. Si algún dominio necesita escalar solo (ej. tracking en tiempo real), será fácil sacarlo después porque ya está aislado.

**Justificación corta:** equipo chico + dominios relacionados que necesitan consistencia (facturación e inventario) + sin evidencia de necesidad de escalar por separado.

---

## 2. Investigación en FastAPI

Los proyectos FastAPI suelen organizarse de 3 formas: por capas (routers/, models/... todo junto por tipo), por dominio (cada tema de negocio con su propia carpeta), o híbrida (config compartida + carpetas por dominio). Elegimos la **híbrida**: es la recomendación más común en guías de FastAPI en producción y evita repetir configuración sin perder la separación por dominio.

---

## 3. Estructura de carpetas

```
backend/
├── app/
│   ├── main.py
│   ├── core/        # config, seguridad
│   ├── db/           # conexión a base de datos
│   ├── shared/       # entidades usadas por varios dominios
│   └── domains/
│       ├── shipments/     # tracking de paquetes
│       ├── warehouse/     # inventario
│       ├── routing/       # rutas y repartidores
│       ├── billing/       # facturación
│       ├── users/         # login, roles
│       └── notifications/
├── tests/
├── alembic/          # migraciones
└── .env.example
```

Criterio: un dominio = un tema de negocio, con su propio router, modelo y lógica adentro.

---

## 4. Endpoints por dominio

| Dominio | Rutas | Qué maneja |
|---|---|---|
| shipments | `/api/v1/shipments` | Envíos, estado de paquetes |
| warehouse | `/api/v1/warehouse` | Stock, ubicaciones |
| routing | `/api/v1/routing` | Rutas y repartidores |
| billing | `/api/v1/billing` | Cargos, facturas |
| users | `/api/v1/users` | Login, roles |
| notifications | `/api/v1/notifications` | Alertas internas |

Regla: el router solo recibe/responde; la lógica de negocio va en un servicio aparte, así se puede extraer un dominio después sin reescribir nada.

---

## 5. Frontend y backend separados

- **Repos separados**, cada uno con su propio despliegue.
- **Comunicación solo por API REST** (`/api/v1/...`), nunca acceso directo a la base de datos desde el frontend.
- **Variables de entorno** propias en cada lado (URLs, credenciales), nunca hardcodeadas.
- **CORS**: hay que configurar en FastAPI qué orígenes pueden llamar a la API, o el navegador bloqueará al frontend.
- **OpenAPI/Swagger** (autogenerado por FastAPI) como contrato compartido entre frontend y backend.

---

## 6. Riesgos

1. **Tratar dominios como microservicios** (llamarse por HTTP entre ellos): dentro del monolito, un dominio llama directo a la función de otro.
2. **Mezclar lógica entre dominios** (ej. cálculos de facturación dentro de warehouse): rompe el propósito de la separación.
3. **Inconsistencia entre facturación e inventario**: un cambio de paquete puede afectar stock y cobro casi a la vez; debe resolverse con una transacción, no con actualizaciones sueltas.
4. **CORS mal configurado**: el frontend deja de poder hablar con el backend y parece un bug cuando es solo config.

---

## 7. Próximos pasos

1. Revisar esta propuesta con el equipo.
2. Armar el esqueleto de carpetas antes del primer endpoint real.
3. Definir qué va en `shared/`.
4. Acordar el contrato de API con el equipo de frontend.