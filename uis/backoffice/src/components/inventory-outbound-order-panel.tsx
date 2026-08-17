"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { useAuth } from "@/lib/auth-context";
import {
  createInventoryApi,
  InventoryApiError,
  InventoryProduct,
  LOW_STOCK_THRESHOLD,
  StockExitType,
} from "@/lib/inventory";
import { track } from "@/services/telemetry";

type FormState = {
  sku_id: string;
  quantity: string;
  exit_type: StockExitType;
  tracking_number: string;
};

const initialFormState: FormState = {
  sku_id: "",
  quantity: "",
  exit_type: "dispatch",
  tracking_number: "",
};

function getErrorMessage(error: unknown, fallback: string): string {
  if (error instanceof InventoryApiError) {
    if (error.status >= 500) {
      return `Error ${error.status}: ${error.message}`;
    }
    return error.message;
  }

  if (error instanceof Error) {
    return error.message;
  }

  return fallback;
}

export function InventoryOutboundOrderPanel() {
  const { authFetch } = useAuth();
  const searchParams = useSearchParams();
  const inventoryApi = useMemo(() => createInventoryApi(authFetch), [authFetch]);

  const [products, setProducts] = useState<InventoryProduct[]>([]);
  const [formState, setFormState] = useState<FormState>(initialFormState);
  const [isLoadingProducts, setIsLoadingProducts] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);
  const [quantityInlineError, setQuantityInlineError] = useState<string | null>(null);

  const selectedProduct = useMemo(
    () => products.find((product) => product.id === Number(formState.sku_id)) || null,
    [products, formState.sku_id]
  );

  const requestedQuantity = Number(formState.quantity || 0);
  const stockWarning =
    selectedProduct && requestedQuantity > 0 && requestedQuantity > selectedProduct.current_stock
      ? `La cantidad solicitada (${requestedQuantity}) supera el stock actual (${selectedProduct.current_stock}).`
      : null;

  async function loadProducts() {
    setIsLoadingProducts(true);
    setLoadError(null);

    try {
      const rows = await inventoryApi.listProducts();
      setProducts(rows);

      const preselectedId = searchParams.get("productId");
      if (preselectedId && rows.some((product) => product.id === Number(preselectedId))) {
        setFormState((current) => ({ ...current, sku_id: preselectedId }));
      } else if (!formState.sku_id && rows.length) {
        setFormState((current) => ({ ...current, sku_id: String(rows[0].id) }));
      }
    } catch (error) {
      setProducts([]);
      setLoadError(getErrorMessage(error, "No se pudo cargar el listado de productos."));
    } finally {
      setIsLoadingProducts(false);
    }
  }

  useEffect(() => {
    const timerId = window.setTimeout(() => {
      void loadProducts();
    }, 0);

    return () => window.clearTimeout(timerId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [inventoryApi, searchParams]);

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitError(null);
    setSubmitSuccess(null);
    setQuantityInlineError(null);

    if (!selectedProduct) {
      setSubmitError("Selecciona un producto valido antes de enviar.");
      return;
    }

    setIsSubmitting(true);

    const submittedQuantity = Number(formState.quantity);

    try {
      const createdOrder = await inventoryApi.createOutboundOrder({
        sku_id: selectedProduct.id,
        quantity: submittedQuantity,
        exit_type: formState.exit_type,
        tracking_number: formState.exit_type === "dispatch" ? formState.tracking_number.trim() : null,
        warehouse: selectedProduct.warehouse,
      });

      track("outbound_order_created", {
        warehouse: selectedProduct.warehouse,
        client_id: selectedProduct.client_name,
        product_id: selectedProduct.sku,
        product_category: selectedProduct.category,
        quantity: submittedQuantity,
        outbound_order_id: String(createdOrder.id),
        exit_type: createdOrder.exit_type,
        tracking_number: createdOrder.tracking_number,
        source_screen: "inventory.orders.outbound",
        source_action: "submit_outbound_form",
      });

      setFormState((current) => ({
        ...current,
        quantity: "",
        tracking_number: "",
      }));
      setSubmitSuccess(`Salida registrada correctamente para ${selectedProduct.name}.`);

      try {
        const refreshedProduct = await inventoryApi.getProduct(selectedProduct.id);
        if (refreshedProduct.current_stock <= LOW_STOCK_THRESHOLD) {
          track("stock_threshold_triggered", {
            warehouse: refreshedProduct.warehouse,
            client_id: refreshedProduct.client_name,
            product_id: refreshedProduct.sku,
            product_category: refreshedProduct.category,
            quantity: submittedQuantity,
            threshold_min: LOW_STOCK_THRESHOLD,
            current_stock: refreshedProduct.current_stock,
            threshold_gap: LOW_STOCK_THRESHOLD - refreshedProduct.current_stock,
            trigger_source: "outbound",
          });
        }
      } catch {
        // Best-effort telemetry check only — does not affect the submitted order.
      }
    } catch (error) {
      if (error instanceof InventoryApiError && error.status === 400) {
        setQuantityInlineError(error.message);
      } else {
        setSubmitError(getErrorMessage(error, "No se pudo crear la orden de salida."));
      }
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="suppliers-layout">
      <section className="card suppliers-hero-card">
        <div>
          <div className="eyebrow">Orden de salida</div>
          <h2 className="panel-title">Registrar despacho o perdida</h2>
          <p className="analysis-copy">Envia datos a POST /inventory/orders/outbound usando seleccion de producto por nombre.</p>
        </div>
      </section>

      <section className="card supplier-form-card">
        <div className="section-header-row">
          <div>
            <h3 className="panel-title">Formulario</h3>
            <p className="section-caption">Si el tipo es dispatch, tracking_number es obligatorio. Si es loss, se envia null.</p>
          </div>
        </div>

        {isLoadingProducts ? <p className="empty-state-inline">Cargando productos...</p> : null}
        {loadError ? (
          <p className="feedback-error">
            {loadError}{" "}
            <button type="button" className="secondary-button compact-button" onClick={() => void loadProducts()}>
              Reintentar
            </button>
          </p>
        ) : null}

        {submitError ? <p className="feedback-error">{submitError}</p> : null}
        {submitSuccess ? <p className="feedback-success">{submitSuccess}</p> : null}

        <form className="supplier-form-grid" onSubmit={(event) => void onSubmit(event)}>
          <label className="field-block">
            <span>Producto</span>
            <select
              value={formState.sku_id}
              onChange={(event) => setFormState((current) => ({ ...current, sku_id: event.target.value }))}
              required
              disabled={isLoadingProducts || !products.length}
            >
              {!products.length ? <option value="">Sin productos disponibles</option> : null}
              {products.map((product) => (
                <option key={product.id} value={product.id}>
                  {product.name} ({product.sku})
                </option>
              ))}
            </select>
          </label>

          <label className="field-block">
            <span>Almacen</span>
            <input type="text" value={selectedProduct?.warehouse || "-"} readOnly />
          </label>

          <label className="field-block">
            <span>Stock actual</span>
            <input type="text" value={selectedProduct ? String(selectedProduct.current_stock) : "-"} readOnly />
          </label>

          <label className="field-block">
            <span>Cantidad</span>
            <input
              type="number"
              min="1"
              step="1"
              value={formState.quantity}
              onChange={(event) => setFormState((current) => ({ ...current, quantity: event.target.value }))}
              required
            />
            {stockWarning ? <span className="field-warning">{stockWarning}</span> : null}
            {quantityInlineError ? <span className="field-error">{quantityInlineError}</span> : null}
          </label>

          <label className="field-block">
            <span>Tipo de salida</span>
            <select
              value={formState.exit_type}
              onChange={(event) => setFormState((current) => ({ ...current, exit_type: event.target.value as StockExitType }))}
            >
              <option value="dispatch">dispatch</option>
              <option value="loss">loss</option>
            </select>
          </label>

          <label className="field-block field-block-wide">
            <span>Tracking number</span>
            <input
              type="text"
              value={formState.tracking_number}
              onChange={(event) => setFormState((current) => ({ ...current, tracking_number: event.target.value }))}
              required={formState.exit_type === "dispatch"}
              placeholder={formState.exit_type === "dispatch" ? "Obligatorio para dispatch" : "Se ignora para loss"}
              disabled={formState.exit_type === "loss"}
            />
          </label>

          <div className="field-block-wide supplier-form-actions">
            <button type="submit" className="primary-button" disabled={isSubmitting || isLoadingProducts || !products.length}>
              {isSubmitting ? "Enviando..." : "Registrar salida"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
