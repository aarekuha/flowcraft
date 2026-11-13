import { apiFetch, createRequestError, handleJsonResponse } from "@/shared/api/http";
import type { OperationCatalogEntryKind } from "@/shared/api/operationCatalog";

export type OperationNode = {
  id: number;
  operationCatalogEntryId: number | null;
  name: string;
  operationKind: OperationCatalogEntryKind | null;
  coefficientUnits: number;
  priceCents: number | null;
  standardTimeSeconds: number | null;
  statisticalTimeSeconds: number | null;
  statisticalCompletedOrdersCount: number;
  statisticalItemsCount: number;
  statisticalTimeCalculatedAt: number | null;
  stageStart: number;
  stageEnd: number;
  children: OperationNode[];
};

export type ProductSummary = {
  id: number;
  name: string;
  version: string;
  author: string;
  authorUserId: number | null;
  materialCostCents: number | null;
  stageCount: number;
  isActive: boolean;
  createdAt: string;
  createdAtTs: number;
  operationsCount: number;
};

export type ProductDetail = {
  baseRateCents: number;
  id: number;
  name: string;
  version: string;
  comment: string | null;
  author: string;
  authorUserId: number | null;
  materialCostCents: number | null;
  stageCount: number;
  isActive: boolean;
  createdAt: string;
  createdAtTs: number;
  operations: OperationNode[];
};

export type ProductCreatePayload = {
  name: string;
  version: string;
  source_product_id?: number | null;
  comment?: string | null;
  author_user_id?: number | null;
  material_cost_cents?: number | null;
  stage_count?: number;
  operations: Array<{
    operation_catalog_entry_id?: number | null;
    name: string;
    coefficient_units?: number;
    standard_time_seconds?: number | null;
    stage_start?: number;
    stage_end?: number;
    children: ProductCreatePayload["operations"];
  }>;
};

export type ProductStagesUpdatePayload = {
  stage_count: number;
  operations: Array<{
    operation_id: number;
    stage_start: number;
    stage_end: number;
  }>;
};

export type ProductCostsUpdatePayload = {
  material_cost_cents?: number | null;
  comment?: string | null;
  operations: Array<{
    id: number;
    coefficient_units?: number;
    standard_time_seconds?: number | null;
    children: ProductCostsUpdatePayload["operations"];
  }>;
};

type OperationNodeApi = {
  id: number;
  operation_catalog_entry_id: number | null;
  name: string;
  operation_kind: OperationCatalogEntryKind | null;
  coefficient_units: number;
  price_cents: number | null;
  standard_time_seconds: number | null;
  statistical_time_seconds: number | null;
  statistical_completed_orders_count: number;
  statistical_items_count: number;
  statistical_time_calculated_at: number | null;
  stage_start: number;
  stage_end: number;
  children: OperationNodeApi[];
};

type ProductSummaryApi = {
  id: number;
  name: string;
  version: string;
  author: string;
  author_user_id: number | null;
  material_cost_cents: number | null;
  stage_count: number;
  is_active: boolean;
  created_at: number;
  operations_count: number;
};

type ProductDetailApi = {
  base_rate_cents: number;
  id: number;
  name: string;
  version: string;
  comment: string | null;
  author: string;
  author_user_id: number | null;
  material_cost_cents: number | null;
  stage_count: number;
  is_active: boolean;
  created_at: number;
  operations: OperationNodeApi[];
};

export async function fetchProducts(): Promise<ProductSummary[]> {
  const response = await apiFetch("/api/products");

  return handleJsonResponse<ProductSummaryApi[]>(response).then((products) =>
    products.map(mapProductSummary),
  );
}

export async function fetchProduct(productId: number): Promise<ProductDetail> {
  const response = await apiFetch(`/api/products/${productId}`);
  return handleJsonResponse<ProductDetailApi>(response).then(mapProductDetail);
}

export async function createProduct(
  payload: ProductCreatePayload,
): Promise<ProductDetail> {
  const response = await apiFetch("/api/products", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse<ProductDetailApi>(response).then(mapProductDetail);
}

export async function updateProductCosts(
  productId: number,
  payload: ProductCostsUpdatePayload,
): Promise<ProductDetail> {
  const response = await apiFetch(`/api/products/${productId}/costs`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse<ProductDetailApi>(response).then(mapProductDetail);
}

export async function updateProductStages(
  productId: number,
  payload: ProductStagesUpdatePayload,
): Promise<ProductDetail> {
  const response = await apiFetch(`/api/products/${productId}/stages`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse<ProductDetailApi>(response).then(mapProductDetail);
}

export async function deleteProduct(productId: number): Promise<void> {
  const response = await apiFetch(`/api/products/${productId}`, {
    method: "DELETE",
  });

  if (!response.ok) {
    throw await createRequestError(response);
  }
}

export async function updateProductStatus(
  productId: number,
  isActive: boolean,
): Promise<ProductSummary> {
  const response = await apiFetch(`/api/products/${productId}/status`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ is_active: isActive }),
  });

  return handleJsonResponse<ProductSummaryApi>(response).then(mapProductSummary);
}

function mapProductSummary(product: ProductSummaryApi): ProductSummary {
  return {
    id: product.id,
    name: product.name,
    version: product.version,
    author: product.author,
    authorUserId: product.author_user_id,
    materialCostCents: product.material_cost_cents,
    stageCount: product.stage_count,
    isActive: product.is_active,
    createdAt: formatDate(product.created_at),
    createdAtTs: product.created_at,
    operationsCount: product.operations_count,
  };
}

function mapProductDetail(product: ProductDetailApi): ProductDetail {
  return {
    baseRateCents: product.base_rate_cents,
    id: product.id,
    name: product.name,
    version: product.version,
    comment: product.comment,
    author: product.author,
    authorUserId: product.author_user_id,
    materialCostCents: product.material_cost_cents,
    stageCount: product.stage_count,
    isActive: product.is_active,
    createdAt: formatDate(product.created_at),
    createdAtTs: product.created_at,
    operations: product.operations.map(mapOperationNode),
  };
}

function mapOperationNode(operation: OperationNodeApi): OperationNode {
  return {
    id: operation.id,
    operationCatalogEntryId: operation.operation_catalog_entry_id,
    name: operation.name,
    operationKind: operation.operation_kind,
    coefficientUnits: operation.coefficient_units,
    priceCents: operation.price_cents,
    standardTimeSeconds: operation.standard_time_seconds,
    statisticalTimeSeconds: operation.statistical_time_seconds,
    statisticalCompletedOrdersCount:
      operation.statistical_completed_orders_count,
    statisticalItemsCount: operation.statistical_items_count,
    statisticalTimeCalculatedAt: operation.statistical_time_calculated_at,
    stageStart: operation.stage_start,
    stageEnd: operation.stage_end,
    children: operation.children.map(mapOperationNode),
  };
}

function formatDate(value: number): string {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(value));
}
