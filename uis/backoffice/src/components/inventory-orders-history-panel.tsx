"use client";

import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/lib/auth-context";
import { createInventoryApi, InventoryApiError, InventoryMovement } from "@/lib/inventory";

function getListErrorMessage(error: unknown): string {
  if (error instanceof InventoryApiError) {
    if (error.status >= 500) {
      return `Error ${error.status}: ${error.message}`;
    }
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return "No se pudo conectar con la API de inventario.";
}

function formatDateTime(value: string) {
  return new Intl.DateTimeFormat("es-ES", { dateStyle: "medium", timeStyle: "short" }).format(new Date(value));
}

function getMovementBadgeClass(movementType: string): string {
  return movementType === "inbound"
    ? "status-badge movement-badge-inbound"
    : "status-badge movement-badge-outbound";
}

function getMovementLabel(movementType: string): string {
  return movementType === "inbound" ? "Entrada" : "Salida";
}

// Con meses de historico hay miles de movimientos: se pintan por paginas.
const PAGE_SIZE = 100;

export function InventoryOrdersHistoryPanel() {
  const { authFetch } = useAuth();
  const inventoryApi = useMemo(() => createInventoryApi(authFetch), [authFetch]);

  const [orders, setOrders] = useState<InventoryMovement[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE);

  // La API devuelve primero todas las entradas y luego todas las salidas;
  // aqui se mezclan en una sola linea temporal (mas reciente primero).
  const sortedOrders = useMemo(
    () => [...orders].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at)),
    [orders],
  );
  const visibleOrders = sortedOrders.slice(0, visibleCount);

  async function refreshOrders() {
    setIsLoading(true);
    setListError(null);

    try {
      const rows = await inventoryApi.listOrders();
      setOrders(rows);
      setVisibleCount(PAGE_SIZE);
    } catch (error) {
      setOrders([]);
      setListError(getListErrorMessage(error));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    const timerId = window.setTimeout(() => {
      void refreshOrders();
    }, 0);

    return () => window.clearTimeout(timerId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inventoryApi]);

  return (
    <div className="suppliers-layout">
      <section className="card suppliers-hero-card">
        <div>
          <div className="eyebrow">Historial de ordenes</div>
          <h2 className="panel-title">Registro de entradas y salidas</h2>
          <p className="analysis-copy">Todas las entradas y salidas de stock, de la mas reciente a la mas antigua.</p>
        </div>
      </section>

      <section className="card suppliers-table-card">
        <div className="section-header-row">
          <div>
            <h3 className="panel-title">Movimientos de inventario</h3>
            <p className="section-caption">Producto, cantidad, tipo, fecha y operario.</p>
          </div>
          <div className="summary-pill">{isLoading ? "Cargando..." : `${orders.length} ordenes`}</div>
        </div>

        {listError ? (
          <p className="feedback-error">
            {listError}{" "}
            <button type="button" className="secondary-button compact-button" onClick={() => void refreshOrders()}>
              Reintentar
            </button>
          </p>
        ) : null}

        <div className="suppliers-table-wrap">
          <table className="suppliers-table">
            <thead>
              <tr>
                <th>Producto</th>
                <th>Cantidad</th>
                <th>Tipo</th>
                <th>Fecha de creacion</th>
                <th>Operario</th>
              </tr>
            </thead>
            <tbody>
              {visibleOrders.map((order) => (
                <tr key={`${order.movement_type}-${order.id}`}>
                  <td>
                    <div className="supplier-name-cell">
                      <strong>{order.sku_name}</strong>
                      <span>{order.sku}</span>
                    </div>
                  </td>
                  <td>{order.quantity}</td>
                  <td>
                    <span className={getMovementBadgeClass(order.movement_type)}>{getMovementLabel(order.movement_type)}</span>
                  </td>
                  <td>{formatDateTime(order.created_at)}</td>
                  <td title={order.user_uuid}>{`OP-${order.user_uuid.slice(0, 6).toUpperCase()}`}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {sortedOrders.length > visibleCount ? (
          <div className="analysis-actions">
            <span className="section-caption">
              Mostrando {visibleCount.toLocaleString("es-ES")} de {sortedOrders.length.toLocaleString("es-ES")} movimientos
            </span>
            <button
              type="button"
              className="secondary-button compact-button"
              onClick={() => setVisibleCount((count) => count + PAGE_SIZE)}
            >
              Mostrar {PAGE_SIZE} mas
            </button>
          </div>
        ) : null}

        {!isLoading && !listError && orders.length === 0 ? (
          <p className="empty-state-inline">No hay ordenes para mostrar.</p>
        ) : null}
      </section>
    </div>
  );
}
