import { apiFetch, createRequestError, handleJsonResponse } from "@/shared/api/http";

export type OperationNode = {
  id: number;
  name: string;
  children: OperationNode[];
};

export type ProductSummary = {
  id: number;
  name: string;
  version: string;
  author: string;
  authorUserId: number | null;
  isActive: boolean;
  createdAt: string;
  createdAtTs: number;
  operationsCount: number;
};

export type ProductDetail = {
  id: number;
  name: string;
  version: string;
  author: string;
  authorUserId: number | null;
  isActive: boolean;
  createdAt: string;
  createdAtTs: number;
  operations: OperationNode[];
};

export type ProductCreatePayload = {
  name: string;
  version: string;
  author_user_id?: number | null;
  operations: Array<{
    name: string;
    children: ProductCreatePayload["operations"];
  }>;
};

type ProductSummaryApi = {
  id: number;
  name: string;
  version: string;
  author: string;
  author_user_id: number | null;
  is_active: boolean;
  created_at: number;
  operations_count: number;
};

type ProductDetailApi = {
  id: number;
  name: string;
  version: string;
  author: string;
  author_user_id: number | null;
  is_active: boolean;
  created_at: number;
  operations: OperationNode[];
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
    isActive: product.is_active,
    createdAt: formatDate(product.created_at),
    createdAtTs: product.created_at,
    operationsCount: product.operations_count,
  };
}

function mapProductDetail(product: ProductDetailApi): ProductDetail {
  return {
    id: product.id,
    name: product.name,
    version: product.version,
    author: product.author,
    authorUserId: product.author_user_id,
    isActive: product.is_active,
    createdAt: formatDate(product.created_at),
    createdAtTs: product.created_at,
    operations: product.operations,
  };
}

function formatDate(value: number): string {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(value));
}
