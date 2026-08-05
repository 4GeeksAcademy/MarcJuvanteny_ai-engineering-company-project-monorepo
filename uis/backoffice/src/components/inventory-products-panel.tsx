"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { useAuth } from "@/lib/auth-context";
import { createInventoryApi, InventoryApiError, InventoryProduct } from "@/lib/inventory";

// Thresholds defined for UX signals in this table:
// low stock: <= 10 units, healthy stock: > 10 units.
const LOW_STOCK_THRESHOLD = 10;

function getStockBadgeClass(currentStock: number): string {
  return currentStock <= LOW_STOCK_THRESHOLD ? "status-badge status-badge-low-stock" : "status-badge status-badge-healthy-stock";
}

function getStockLabel(currentStock: number): string {
  return currentStock <= LOW_STOCK_THRESHOLD ? "Stock bajo" : "Stock saludable";
}

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

export function InventoryProductsPanel() {
  const { authFetch } = useAuth();
  const inventoryApi = useMemo(() => createInventoryApi(authFetch), [authFetch]);

  const [products, setProducts] = useState<InventoryProduct[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [listError, setListError] = useState<string | null>(null);

  async function refreshProducts() {
    setIsLoading(true);
    setListError(null);

    try {
      const rows = await inventoryApi.listProducts();
      setProducts(rows);
    } catch (error) {
      setProducts([]);
      setListError(getListErrorMessage(error));
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    const timerId = window.setTimeout(() => {
      void refreshProducts();
    }, 0);

    return () => window.clearTimeout(timerId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inventoryApi]);

  const lowStockCount = useMemo(
    () => products.filter((product) => product.current_stock <= LOW_STOCK_THRESHOLD).length,
    [products]
  );

  const totalUnits = useMemo(
    () => products.reduce((sum, product) => sum + product.current_stock, 0),
    [products]
  );

  return (
    <div className="suppliers-layout">
      <section className="card suppliers-hero-card">
        <div>
          <div className="eyebrow">Hito 05 · Inventario unificado</div>
          <h2 className="panel-title">Productos y stock por almacen</h2>
          <p className="analysis-copy">
            Fuente: GET /inventory/products. Cada fila permite crear una orden de entrada o salida para ese producto.
          </p>
        </div>

        <div className="suppliers-summary-strip">
          <article className="supplier-stat-card">
            <span>Productos</span>
            <strong>{products.length}</strong>
          </article>
          <article className="supplier-stat-card supplier-stat-card-suspended">
            <span>Stock bajo</span>
            <strong>{lowStockCount}</strong>
          </article>
          <article className="supplier-stat-card supplier-stat-card-active">
            <span>Unidades totales</span>
            <strong>{totalUnits}</strong>
          </article>
        </div>
      </section>

      <section className="card suppliers-table-card">
        <div className="section-header-row">
          <div>
            <h3 className="panel-title">Listado de productos</h3>
            <p className="section-caption">Incluye nombre, SKU, cliente, categoria, almacen y current_stock.</p>
          </div>
          <div style={{ display: "flex", gap: "0.6rem", alignItems: "center", flexWrap: "wrap" }}>
            <Link href="/inventory/orders" className="secondary-button compact-button">
              Ver historial de ordenes
            </Link>
            <div className="summary-pill">{isLoading ? "Cargando..." : `${products.length} productos`}</div>
          </div>
        </div>

        {listError ? (
          <p className="feedback-error">
            {listError}{" "}
            <button type="button" className="secondary-button compact-button" onClick={() => void refreshProducts()}>
              Reintentar
            </button>
          </p>
        ) : null}

        <div className="suppliers-table-wrap">
          <table className="suppliers-table">
            <thead>
              <tr>
                <th>Producto</th>
                <th>SKU</th>
                <th>Cliente</th>
                <th>Categoria</th>
                <th>Almacen</th>
                <th>current_stock</th>
                <th>Nivel</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {products.map((product) => (
                <tr key={product.id}>
                  <td>
                    <div className="supplier-name-cell">
                      <strong>{product.name}</strong>
                    </div>
                  </td>
                  <td>{product.sku}</td>
                  <td>{product.client_name}</td>
                  <td>{product.category}</td>
                  <td>{product.warehouse}</td>
                  <td>{product.current_stock}</td>
                  <td>
                    <span className={getStockBadgeClass(product.current_stock)}>{getStockLabel(product.current_stock)}</span>
                  </td>
                  <td>
                    <div className="row-actions row-actions-inline">
                      <Link
                        href={`/inventory/orders/inbound?productId=${product.id}`}
                        className="secondary-button compact-button"
                      >
                        Crear entrada
                      </Link>
                      <Link
                        href={`/inventory/orders/outbound?productId=${product.id}`}
                        className="primary-button compact-button"
                      >
                        Crear salida
                      </Link>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        {!isLoading && !listError && products.length === 0 ? (
          <p className="empty-state-inline">No hay productos para mostrar.</p>
        ) : null}
      </section>
    </div>
  );
}
