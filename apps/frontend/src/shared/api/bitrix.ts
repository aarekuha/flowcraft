import { apiFetch, handleJsonResponse } from "./http";

export type BitrixProgress = { kind: "catalog" | "deals"; stage: string; completed: number; total: number | null; updated_at: number };
export type BitrixStatus = { job_id?: string | null; progress?: BitrixProgress | null; configured: boolean; syncing: boolean; synced_at: number | null; last_error: string | null };
export type BitrixItem = {
  id: number; catalog_id: number; name: string; active: boolean; present: boolean;
  parent_id: number | null; fields: Record<string, unknown>; prices: Record<string, unknown>[];
  mapped_product_id: number | null;
};
export type MappedProduct = { id: number; name: string; version: string; mapping_not_required: boolean; bitrix_ids: number[] };
export type BitrixCatalog = {
  items: BitrixItem[]; products: MappedProduct[];
  metadata: Record<string, { catalog: Record<string, unknown>; fields: Record<string, { name?: string }> }>;
};

async function request<T>(path: string, method = "GET", body?: unknown): Promise<T> {
  return handleJsonResponse<T>(await apiFetch(`/api/bitrix/${path}`, {
    method,
    ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
  }));
}
export const fetchBitrixStatus = () => request<BitrixStatus>("settings");
export const fetchBitrixCatalog = () => request<BitrixCatalog>("catalog");
export const saveBitrixSettings = (webhook: string) => request<BitrixStatus>("settings", "PUT", { webhook });
export const checkBitrixConnection = () => request<{ ok: boolean }>("check", "POST");
export const syncBitrixCatalog = () => request<{ accepted: boolean }>("sync", "POST");
export const saveBitrixMapping = (productId: number, bitrixIds: number[]) => request<{ ok: boolean }>(`mappings/${productId}`, "PUT", { bitrix_ids: bitrixIds });

export type BitrixDealSummary = {
  id: number; title: string; category_id: number; stage_id: string; closed: boolean;
  present: boolean; amount: string | number | null; currency: string | null; updated_at: number;
};
export type BitrixDeals = {
  total: number; page: number; page_size: number; items: BitrixDealSummary[];
  metadata: {
    fields?: Record<string, { title?: string; formLabel?: string; listLabel?: string }>;
    categories?: { id: number; name: string }[];
    stages?: { STATUS_ID: string; NAME: string }[];
  };
};
export type BitrixDealDetails = { id: number; title: string; fields: Record<string, unknown>; product_rows: Record<string, unknown>[] };
export const fetchBitrixDealsStatus = () => request<BitrixStatus>("deals/status");
export const syncBitrixDeals = () => request<{ accepted: boolean }>("deals/sync", "POST");
export const fetchBitrixDeals = (query: URLSearchParams) => request<BitrixDeals>(`deals?${query}`);
export const fetchBitrixDeal = (id: number) => request<BitrixDealDetails>(`deals/${id}`);

export const saveBitrixMappingRequirement = (productId: number, notRequired: boolean) => request<{ ok: boolean }>(`mappings/${productId}/requirement`, "PUT", { not_required: notRequired });

export const cancelBitrixSync = (jobId: string) => request<{ ok: boolean }>("sync/cancel", "POST", { job_id: jobId });
