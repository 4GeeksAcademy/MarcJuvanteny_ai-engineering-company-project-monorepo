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

export function InventoryOrdersHistoryPanel() {
  const { authFetch } = useAuth();
  const inventoryApi = useMemo(() => createInventoryApi(authFetch), [authFetch]);

  const [orders, setOrders] = useState<InventoryMovement[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  async function refreshOrders() {
    setIsLoading(true);
    setListError(null);

    try {
      const rows = await inventoryApi.listOrders();
      setOrders(rows);
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
          <p className="analysis-copy">Vista de solo lectura alimentada por GET /inventory/orders.</p>
        </div>
      </section>

      <section className="card suppliers-table-card">
        <div className="section-header-row">
          <div>
            <h3 className="panel-title">Movimientos de inventario</h3>
            <p className="section-caption">Incluye producto, cantidad, tipo, fecha y user_uuid creador.</p>
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
                <th>user_uuid</th>
              </tr>
            </thead>
            <tbody>
              {orders.map((order) => (
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
                  <td>{order.user_uuid}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!isLoading && !listError && orders.length === 0 ? (
          <p className="empty-state-inline">No hay ordenes para mostrar.</p>
        ) : null}
      </section>
    </div>
  );
}
