"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";

import { extractErrorMessage } from "@/lib/api-errors";
import { useAuth } from "@/lib/auth-context";

const countryOptions = ["USA", "Spain"] as const;
const categoryOptions = [
  "carrier_last_mile",
  "carrier_international",
  "warehouse_supplies",
  "packaging_materials",
  "reverse_logistics",
  "fleet_maintenance",
  "it_and_wms_software",
  "cleaning_and_facilities",
] as const;

type SupplierStatus = "active" | "suspended";

type SupplierRecord = {
  id: number;
  name: string;
  country: (typeof countryOptions)[number];
  categories: string[];
  rate_per_shipment: number;
  currency: string;
  updated_at: string;
  status: SupplierStatus;
  service_zone: string | null;
  contact_email: string | null;
  notes: string | null;
};

type SupplierCreatePayload = {
  name: string;
  country: string;
  categories: string[];
  rate_per_shipment: number;
  currency: string;
  status: SupplierStatus;
  service_zone?: string;
  contact_email?: string;
  notes?: string;
};

type FormState = {
  name: string;
  country: string;
  categories: string[];
  rate_per_shipment: string;
  currency: string;
  status: SupplierStatus;
  service_zone: string;
  contact_email: string;
  notes: string;
};

const initialFormState: FormState = {
  name: "",
  country: "USA",
  categories: ["carrier_last_mile"],
  rate_per_shipment: "",
  currency: "USD",
  status: "active",
  service_zone: "",
  contact_email: "",
  notes: "",
};

function formatCurrency(rate: number, currency: string) {
  return new Intl.NumberFormat("es-ES", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(rate);
}

function buildQuery(country: string, category: string) {
  const params = new URLSearchParams();
  if (country) {
    params.set("country", country);
  }
  if (category) {
    params.set("category", category);
  }
  const queryString = params.toString();
  return queryString ? `?${queryString}` : "";
}

function normalizeOptionalValue(value: string) {
  const normalized = value.trim();
  return normalized ? normalized : undefined;
}

type AuthFetch = (path: string, options?: RequestInit) => Promise<Response>;

async function requestSuppliers(authFetch: AuthFetch, country: string, category: string) {
  const response = await authFetch(`/suppliers${buildQuery(country, category)}`, {
    cache: "no-store",
  });
  const data = await response.json().catch(() => null);

  if (!response.ok) {
    throw new Error(extractErrorMessage(data, "No se pudo cargar el directorio de proveedores."));
  }

  return (data ?? []) as SupplierRecord[];
}

export function SuppliersDirectoryPanel() {
  const { authFetch } = useAuth();
  const [suppliers, setSuppliers] = useState<SupplierRecord[]>([]);
  const [selectedCountry, setSelectedCountry] = useState("");
  const [selectedCategory, setSelectedCategory] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [listError, setListError] = useState<string | null>(null);
  const [feedbackError, setFeedbackError] = useState<string | null>(null);
  const [feedbackSuccess, setFeedbackSuccess] = useState<string | null>(null);
  const [formState, setFormState] = useState<FormState>(initialFormState);
  const [rateDrafts, setRateDrafts] = useState<Record<number, string>>({});
  const [updatingIds, setUpdatingIds] = useState<number[]>([]);

  async function refreshSuppliers(country = selectedCountry, category = selectedCategory) {
    setIsLoading(true);
    setListError(null);

    try {
      const nextSuppliers = await requestSuppliers(authFetch, country, category);
      setSuppliers(nextSuppliers);
      setRateDrafts(
        Object.fromEntries(nextSuppliers.map((supplier) => [supplier.id, supplier.rate_per_shipment.toFixed(2)]))
      );
    } catch (error) {
      setSuppliers([]);
      setListError(error instanceof Error ? error.message : "No se pudo conectar con la API de proveedores.");
    } finally {
      setIsLoading(false);
    }
  }

  useEffect(() => {
    const timerId = window.setTimeout(() => {
      void refreshSuppliers(selectedCountry, selectedCategory);
    }, 0);

    return () => window.clearTimeout(timerId);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCountry, selectedCategory, authFetch]);

  const activeCount = useMemo(
    () => suppliers.filter((supplier) => supplier.status === "active").length,
    [suppliers]
  );

  const suspendedCount = useMemo(
    () => suppliers.filter((supplier) => supplier.status === "suspended").length,
    [suppliers]
  );

  function onCategoryToggle(category: string) {
    setFormState((current) => {
      const exists = current.categories.includes(category);
      const nextCategories = exists
        ? current.categories.filter((item) => item !== category)
        : [...current.categories, category];

      return {
        ...current,
        categories: nextCategories.length ? nextCategories : current.categories,
      };
    });
  }

  function onCountryChange(country: string) {
    setFormState((current) => ({
      ...current,
      country,
      currency: country === "USA" ? "USD" : "EUR",
    }));
  }

  async function submitSupplier(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSubmitting(true);
    setFeedbackError(null);
    setFeedbackSuccess(null);

    const payload: SupplierCreatePayload = {
      name: formState.name.trim(),
      country: formState.country,
      categories: formState.categories,
      rate_per_shipment: Number(formState.rate_per_shipment),
      currency: formState.currency,
      status: formState.status,
      service_zone: normalizeOptionalValue(formState.service_zone),
      contact_email: normalizeOptionalValue(formState.contact_email),
      notes: normalizeOptionalValue(formState.notes),
    };

    try {
      const response = await authFetch("/suppliers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await response.json().catch(() => null);
      if (!response.ok) {
        setFeedbackError(extractErrorMessage(data, "La API rechazo el alta del proveedor."));
        return;
      }

      setFormState(initialFormState);
      setFeedbackSuccess("Proveedor registrado correctamente.");
      await refreshSuppliers(selectedCountry, selectedCategory);
    } catch {
      setFeedbackError("No se pudo registrar el proveedor en la API.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function updateRate(supplierId: number) {
    const draftValue = Number(rateDrafts[supplierId]);
    setUpdatingIds((current) => [...current, supplierId]);
    setFeedbackError(null);
    setFeedbackSuccess(null);

    try {
      const response = await authFetch(`/suppliers/${supplierId}/rate`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ rate_per_shipment: draftValue }),
      });
      const data = await response.json().catch(() => null);

      if (!response.ok) {
        setFeedbackError(extractErrorMessage(data, "No se pudo actualizar la tarifa."));
        return;
      }

      const updatedSupplier = data as SupplierRecord;
      setSuppliers((current) => current.map((supplier) => supplier.id === supplierId ? updatedSupplier : supplier));
      setRateDrafts((current) => ({ ...current, [supplierId]: updatedSupplier.rate_per_shipment.toFixed(2) }));
      setFeedbackSuccess(`Tarifa actualizada para ${updatedSupplier.name}.`);
    } catch {
      setFeedbackError("No se pudo conectar con la API para actualizar la tarifa.");
    } finally {
      setUpdatingIds((current) => current.filter((id) => id !== supplierId));
    }
  }

  async function toggleStatus(supplier: SupplierRecord) {
    const nextStatus: SupplierStatus = supplier.status === "active" ? "suspended" : "active";
    setUpdatingIds((current) => [...current, supplier.id]);
    setFeedbackError(null);
    setFeedbackSuccess(null);

    try {
      const response = await authFetch(`/suppliers/${supplier.id}/status`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ status: nextStatus }),
      });
      const data = await response.json().catch(() => null);

      if (!response.ok) {
        setFeedbackError(extractErrorMessage(data, "No se pudo cambiar el estado del proveedor."));
        return;
      }

      const updatedSupplier = data as SupplierRecord;
      setSuppliers((current) => current.map((item) => item.id === supplier.id ? updatedSupplier : item));
      setFeedbackSuccess(`Estado actualizado para ${updatedSupplier.name}.`);
    } catch {
      setFeedbackError("No se pudo conectar con la API para cambiar el estado.");
    } finally {
      setUpdatingIds((current) => current.filter((id) => id !== supplier.id));
    }
  }

  return (
    <div className="suppliers-layout">
      <section className="card suppliers-hero-card">
        <div>
          <div className="eyebrow">Hito 09 · Directorio de proveedores</div>
          <h2 className="panel-title">Unifica carriers, embalaje, devoluciones y software operativo</h2>
          <p className="analysis-copy">
            Filtra por mercado o categoria, registra nuevos acuerdos y actualiza tarifas y estado sin recargar la pagina.
          </p>
        </div>

        <div className="suppliers-summary-strip">
          <article className="supplier-stat-card supplier-stat-card-active">
            <span>Activos</span>
            <strong>{activeCount}</strong>
          </article>
          <article className="supplier-stat-card supplier-stat-card-suspended">
            <span>Suspendidos</span>
            <strong>{suspendedCount}</strong>
          </article>
          <article className="supplier-stat-card">
            <span>Total visible</span>
            <strong>{suppliers.length}</strong>
          </article>
        </div>
      </section>

      <section className="card suppliers-toolbar-card">
        <div className="section-header-row">
          <div>
            <h3 className="panel-title">Filtros operativos</h3>
            <p className="section-caption">El listado se refresca automaticamente al cambiar pais o categoria.</p>
          </div>
        </div>

        <div className="suppliers-filters-grid">
          <label className="field-block">
            <span>Pais</span>
            <select value={selectedCountry} onChange={(event) => setSelectedCountry(event.target.value)}>
              <option value="">Todos</option>
              {countryOptions.map((country) => (
                <option key={country} value={country}>{country}</option>
              ))}
            </select>
          </label>

          <label className="field-block">
            <span>Categoria</span>
            <select value={selectedCategory} onChange={(event) => setSelectedCategory(event.target.value)}>
              <option value="">Todas</option>
              {categoryOptions.map((category) => (
                <option key={category} value={category}>{category}</option>
              ))}
            </select>
          </label>
        </div>
      </section>

      <section className="card suppliers-table-card">
        <div className="section-header-row">
          <div>
            <h3 className="panel-title">Listado completo</h3>
            <p className="section-caption">Vista resumida con pais, categorias, tarifa y acciones operativas por fila.</p>
          </div>
          <div className="summary-pill">{isLoading ? "Cargando..." : `${suppliers.length} proveedores`}</div>
        </div>

        {listError ? (
          <p className="feedback-error">
            {listError}{" "}
            <button type="button" className="secondary-button compact-button" onClick={() => void refreshSuppliers()}>
              Reintentar
            </button>
          </p>
        ) : null}
        {feedbackError ? <p className="feedback-error">{feedbackError}</p> : null}
        {feedbackSuccess ? <p className="feedback-success">{feedbackSuccess}</p> : null}

        <div className="suppliers-table-wrap">
          <table className="suppliers-table">
            <thead>
              <tr>
                <th>Proveedor</th>
                <th>Pais</th>
                <th>Categorias</th>
                <th>Tarifa</th>
                <th>Estado</th>
                <th>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {suppliers.map((supplier) => {
                const isUpdating = updatingIds.includes(supplier.id);
                const statusClass = supplier.status === "active" ? "status-badge status-badge-active" : "status-badge status-badge-suspended";

                return (
                  <tr key={supplier.id} className={supplier.status === "suspended" ? "supplier-row-muted" : undefined}>
                    <td>
                      <div className="supplier-name-cell">
                        <strong>{supplier.name}</strong>
                        <span>{supplier.service_zone || supplier.contact_email || "Sin detalle adicional"}</span>
                      </div>
                    </td>
                    <td>{supplier.country}</td>
                    <td>
                      <div className="category-chip-list">
                        {(supplier.categories ?? []).map((category) => (
                          <span key={category} className="category-chip">{category}</span>
                        ))}
                      </div>
                    </td>
                    <td>
                      <div className="rate-editor">
                        <input
                          type="number"
                          min="0.01"
                          step="0.01"
                          value={rateDrafts[supplier.id] || ""}
                          onChange={(event) => setRateDrafts((current) => ({ ...current, [supplier.id]: event.target.value }))}
                        />
                        <span>{formatCurrency(supplier.rate_per_shipment, supplier.currency)}</span>
                      </div>
                    </td>
                    <td>
                      <span className={statusClass}>{supplier.status === "active" ? "Activo" : "Suspendido"}</span>
                    </td>
                    <td>
                      <div className="row-actions">
                        <button type="button" className="secondary-button compact-button" onClick={() => void updateRate(supplier.id)} disabled={isUpdating}>
                          Guardar tarifa
                        </button>
                        <button type="button" className="primary-button compact-button" onClick={() => void toggleStatus(supplier)} disabled={isUpdating}>
                          {supplier.status === "active" ? "Suspender" : "Activar"}
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}

              {!isLoading && !listError && !suppliers.length ? (
                <tr>
                  <td colSpan={6}>
                    <div className="empty-state-inline">No hay proveedores para los filtros seleccionados.</div>
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card supplier-form-card">
        <div className="section-header-row">
          <div>
            <h3 className="panel-title">Registrar proveedor nuevo</h3>
            <p className="section-caption">El formulario consume POST /suppliers y muestra el error devuelto por la API si la entrada no es valida.</p>
          </div>
        </div>

        <form className="supplier-form-grid" onSubmit={(event) => void submitSupplier(event)}>
          <label className="field-block">
            <span>Nombre</span>
            <input
              type="text"
              value={formState.name}
              onChange={(event) => setFormState((current) => ({ ...current, name: event.target.value }))}
              required
            />
          </label>

          <label className="field-block">
            <span>Pais</span>
            <select
              value={formState.country}
              onChange={(event) => onCountryChange(event.target.value)}
            >
              {countryOptions.map((country) => (
                <option key={country} value={country}>{country}</option>
              ))}
            </select>
          </label>

          <label className="field-block">
            <span>Tarifa</span>
            <input
              type="number"
              min="0.01"
              step="0.01"
              value={formState.rate_per_shipment}
              onChange={(event) => setFormState((current) => ({ ...current, rate_per_shipment: event.target.value }))}
              required
            />
          </label>

          <label className="field-block">
            <span>Moneda</span>
            <input type="text" value={formState.currency} readOnly />
          </label>

          <label className="field-block">
            <span>Estado inicial</span>
            <select
              value={formState.status}
              onChange={(event) => setFormState((current) => ({ ...current, status: event.target.value as SupplierStatus }))}
            >
              <option value="active">Activo</option>
              <option value="suspended">Suspendido</option>
            </select>
          </label>

          <label className="field-block">
            <span>Zona de servicio</span>
            <input
              type="text"
              value={formState.service_zone}
              onChange={(event) => setFormState((current) => ({ ...current, service_zone: event.target.value }))}
            />
          </label>

          <label className="field-block">
            <span>Email de contacto</span>
            <input
              type="email"
              value={formState.contact_email}
              onChange={(event) => setFormState((current) => ({ ...current, contact_email: event.target.value }))}
            />
          </label>

          <label className="field-block field-block-wide">
            <span>Notas</span>
            <textarea
              rows={4}
              value={formState.notes}
              onChange={(event) => setFormState((current) => ({ ...current, notes: event.target.value }))}
            />
          </label>

          <fieldset className="field-block field-block-wide category-picker">
            <legend>Categorias</legend>
            <div className="category-picker-grid">
              {categoryOptions.map((category) => {
                const checked = formState.categories.includes(category);
                return (
                  <label key={category} className={checked ? "category-toggle checked" : "category-toggle"}>
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => onCategoryToggle(category)}
                    />
                    <span>{category}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          <div className="supplier-form-actions field-block-wide">
            <button type="submit" className="primary-button" disabled={isSubmitting}>
              {isSubmitting ? "Registrando..." : "Registrar proveedor"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}