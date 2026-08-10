"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { useSearchParams } from "next/navigation";

import { useAuth } from "@/lib/auth-context";
import { createInventoryApi, InventoryApiError, InventoryProduct } from "@/lib/inventory";

type FormState = {
  sku_id: string;
  quantity: string;
  reference: string;
};

const initialFormState: FormState = {
  sku_id: "",
  quantity: "",
  reference: "",
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

export function InventoryInboundOrderPanel() {
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

  const selectedProduct = useMemo(
    () => products.find((product) => product.id === Number(formState.sku_id)) || null,
    [products, formState.sku_id]
  );

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

    if (!selectedProduct) {
      setSubmitError("Selecciona un producto valido antes de enviar.");
      return;
    }

    setIsSubmitting(true);

    try {
      await inventoryApi.createInboundOrder({
        sku_id: selectedProduct.id,
        quantity: Number(formState.quantity),
        reference: formState.reference.trim(),
        warehouse: selectedProduct.warehouse,
      });

      setFormState((current) => ({ ...current, quantity: "", reference: "" }));
      setSubmitSuccess(`Entrada registrada correctamente para ${selectedProduct.name}.`);
    } catch (error) {
      setSubmitError(getErrorMessage(error, "No se pudo crear la orden de entrada."));
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <div className="suppliers-layout">
      <section className="card suppliers-hero-card">
        <div>
          <div className="eyebrow">Orden de entrada</div>
          <h2 className="panel-title">Registrar recepcion de stock</h2>
          <p className="analysis-copy">Envia datos a POST /inventory/orders/inbound usando seleccion de producto por nombre.</p>
        </div>
      </section>

      <section className="card supplier-form-card">
        <div className="section-header-row">
          <div>
            <h3 className="panel-title">Formulario</h3>
            <p className="section-caption">Tras enviar correctamente, el formulario limpia cantidad y referencia.</p>
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
            <span>Cantidad</span>
            <input
              type="number"
              min="1"
              step="1"
              value={formState.quantity}
              onChange={(event) => setFormState((current) => ({ ...current, quantity: event.target.value }))}
              required
            />
          </label>

          <label className="field-block">
            <span>Referencia</span>
            <input
              type="text"
              value={formState.reference}
              onChange={(event) => setFormState((current) => ({ ...current, reference: event.target.value }))}
              required
            />
          </label>

          <div className="field-block-wide supplier-form-actions">
            <button type="submit" className="primary-button" disabled={isSubmitting || isLoadingProducts || !products.length}>
              {isSubmitting ? "Enviando..." : "Registrar entrada"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}
