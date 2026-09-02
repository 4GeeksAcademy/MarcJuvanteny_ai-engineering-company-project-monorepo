import { extractErrorMessage } from "@/lib/api-errors";

// Thresholds defined for UX signals in the products table and for the
// stock_threshold_triggered telemetry event: low stock: <= 10 units.
export const LOW_STOCK_THRESHOLD = 10;

export type InventoryWarehouse = "LA" | "ZGZ";
export type InventoryCategory = "fashion" | "electronics" | "cosmetics";
export type StockExitType = "dispatch" | "loss";

export type InventoryProduct = {
  id: number;
  name: string;
  sku: string;
  client_name: string;
  category: InventoryCategory;
  warehouse: InventoryWarehouse;
  current_stock: number;
};

export type InventoryInboundOrder = {
  id: number;
  sku_id: number;
  quantity: number;
  reference: string;
  warehouse: InventoryWarehouse;
  created_at: string;
  user_uuid: string;
};

export type InventoryOutboundOrder = {
  id: number;
  sku_id: number;
  quantity: number;
  exit_type: StockExitType;
  tracking_number: string | null;
  warehouse: InventoryWarehouse;
  created_at: string;
  user_uuid: string;
};

export type InventoryMovement = {
  movement_type: "inbound" | "outbound";
  id: number;
  sku_id: number;
  sku: string;
  sku_name: string;
  warehouse: InventoryWarehouse;
  quantity: number;
  created_at: string;
  user_uuid: string;
  reference: string | null;
  exit_type: StockExitType | null;
  tracking_number: string | null;
};

export type CreateInventoryProductInput = {
  name: string;
  sku: string;
  client_name: string;
  category: InventoryCategory;
  warehouse: InventoryWarehouse;
};

export type CreateInboundOrderInput = {
  sku_id: number;
  quantity: number;
  reference: string;
  warehouse: InventoryWarehouse;
};

export type CreateOutboundOrderInput = {
  sku_id: number;
  quantity: number;
  exit_type: StockExitType;
  tracking_number: string | null;
  warehouse: InventoryWarehouse;
};

export class InventoryApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "InventoryApiError";
    this.status = status;
  }
}

type ApiRequester = (path: string, options?: RequestInit) => Promise<Response>;

async function parseJsonSafely(response: Response): Promise<unknown> {
  try {
    return await response.json();
  } catch {
    return null;
  }
}

async function assertOk(response: Response, fallbackMessage: string): Promise<void> {
  if (response.ok) {
    return;
  }

  const data = await parseJsonSafely(response);
  const message = extractErrorMessage(data, fallbackMessage);
  throw new InventoryApiError(message, response.status);
}

export function createInventoryApi(request: ApiRequester) {
  return {
    async listProducts(): Promise<InventoryProduct[]> {
      const response = await request("/inventory/products", { cache: "no-store" });
      await assertOk(response, "No se pudo cargar el inventario.");
      return (await response.json()) as InventoryProduct[];
    },

    async getProduct(productId: number): Promise<InventoryProduct> {
      const response = await request(`/inventory/products/${productId}`, { cache: "no-store" });
      await assertOk(response, "No se pudo cargar el producto.");
      return (await response.json()) as InventoryProduct;
    },

    async createProduct(payload: CreateInventoryProductInput): Promise<InventoryProduct> {
      const response = await request("/inventory/products", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      await assertOk(response, "No se pudo crear el producto.");
      return (await response.json()) as InventoryProduct;
    },

    async createInboundOrder(payload: CreateInboundOrderInput): Promise<InventoryInboundOrder> {
      const response = await request("/inventory/orders/inbound", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      await assertOk(response, "No se pudo registrar la entrada de stock.");
      return (await response.json()) as InventoryInboundOrder;
    },

    async createOutboundOrder(payload: CreateOutboundOrderInput): Promise<InventoryOutboundOrder> {
      const response = await request("/inventory/orders/outbound", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      await assertOk(response, "No se pudo registrar la salida de stock.");
      return (await response.json()) as InventoryOutboundOrder;
    },

    async listOrders(): Promise<InventoryMovement[]> {
      const response = await request("/inventory/orders", { cache: "no-store" });
      await assertOk(response, "No se pudieron cargar los movimientos de inventario.");
      return (await response.json()) as InventoryMovement[];
    },
  };
}
