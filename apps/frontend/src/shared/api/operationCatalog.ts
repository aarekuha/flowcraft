import { apiFetch, handleJsonResponse } from "@/shared/api/http";

export type OperationCatalogSortDirection = "asc" | "desc";

export type OperationCatalogEntry = {
  id: number;
  name: string;
  isActive: boolean;
  createdAtTs: number;
  createdAt: string;
  updatedAtTs: number;
  updatedAt: string;
};

export type OperationCatalogListParams = {
  search?: string;
  includeInactive?: boolean;
  sortDirection?: OperationCatalogSortDirection;
  page?: number;
  pageSize?: number;
};

export type OperationCatalogPage = {
  items: OperationCatalogEntry[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
};

type OperationCatalogEntryApi = {
  id: number;
  name: string;
  is_active: boolean;
  created_at: number;
  updated_at: number;
};

type OperationCatalogPageApi = {
  items: OperationCatalogEntryApi[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
};

export async function fetchOperationCatalog(
  params: OperationCatalogListParams = {},
): Promise<OperationCatalogPage> {
  const searchParams = buildOperationCatalogSearchParams(params);
  const queryString = searchParams.toString();
  const response = await apiFetch(
    `/api/operation-catalog${queryString ? `?${queryString}` : ""}`,
  );

  return handleJsonResponse<OperationCatalogPageApi>(response).then(
    mapOperationCatalogPage,
  );
}

export async function fetchAllOperationCatalogEntries(
  params: OperationCatalogListParams = {},
): Promise<OperationCatalogEntry[]> {
  const baseParams = { ...params };
  delete baseParams.page;
  delete baseParams.pageSize;

  const pageSize = params.pageSize ?? 100;
  const entries: OperationCatalogEntry[] = [];
  let page = 1;

  while (true) {
    const response = await fetchOperationCatalog({
      ...baseParams,
      page,
      pageSize,
    });
    entries.push(...response.items);

    if (page >= response.pages || entries.length >= response.total) {
      return entries;
    }

    page += 1;
  }
}

export async function createOperationCatalogEntry(
  name: string,
): Promise<OperationCatalogEntry> {
  const response = await apiFetch("/api/operation-catalog", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name }),
  });

  return handleJsonResponse<OperationCatalogEntryApi>(response).then(
    mapOperationCatalogEntry,
  );
}

export async function updateOperationCatalogEntryStatus(
  entryId: number,
  isActive: boolean,
): Promise<OperationCatalogEntry> {
  const response = await apiFetch(`/api/operation-catalog/${entryId}/status`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ is_active: isActive }),
  });

  return handleJsonResponse<OperationCatalogEntryApi>(response).then(
    mapOperationCatalogEntry,
  );
}

function mapOperationCatalogPage(
  page: OperationCatalogPageApi,
): OperationCatalogPage {
  return {
    items: page.items.map(mapOperationCatalogEntry),
    total: page.total,
    page: page.page,
    pageSize: page.page_size,
    pages: page.pages,
  };
}

function mapOperationCatalogEntry(
  entry: OperationCatalogEntryApi,
): OperationCatalogEntry {
  return {
    id: entry.id,
    name: entry.name,
    isActive: entry.is_active,
    createdAtTs: entry.created_at,
    createdAt: formatDate(entry.created_at),
    updatedAtTs: entry.updated_at,
    updatedAt: formatDate(entry.updated_at),
  };
}

function buildOperationCatalogSearchParams(
  params: OperationCatalogListParams,
): URLSearchParams {
  const searchParams = new URLSearchParams();

  if (params.search?.trim()) {
    searchParams.set("search", params.search.trim());
  }

  if (params.includeInactive !== undefined) {
    searchParams.set("include_inactive", String(params.includeInactive));
  }

  if (params.sortDirection) {
    searchParams.set("sort_direction", params.sortDirection);
  }

  if (params.page !== undefined) {
    searchParams.set("page", String(params.page));
  }

  if (params.pageSize !== undefined) {
    searchParams.set("page_size", String(params.pageSize));
  }

  return searchParams;
}

function formatDate(value: number): string {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(value));
}
