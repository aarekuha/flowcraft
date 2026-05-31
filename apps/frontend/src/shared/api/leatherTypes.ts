import { apiFetch, handleJsonResponse } from "@/shared/api/http";

export type LeatherTypeSortDirection = "asc" | "desc";

export type LeatherTypeRecord = {
  id: number;
  name: string;
  isActive: boolean;
  createdAtTs: number;
  createdAt: string;
  updatedAtTs: number;
  updatedAt: string;
};

export type LeatherTypeListParams = {
  search?: string;
  includeInactive?: boolean;
  sortDirection?: LeatherTypeSortDirection;
  page?: number;
  pageSize?: number;
};

export type LeatherTypePage = {
  items: LeatherTypeRecord[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
};

type LeatherTypeApi = {
  id: number;
  name: string;
  is_active: boolean;
  created_at: number;
  updated_at: number;
};

type LeatherTypePageApi = {
  items: LeatherTypeApi[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
};

export async function fetchLeatherTypes(
  params: LeatherTypeListParams = {},
): Promise<LeatherTypePage> {
  const searchParams = buildLeatherTypeSearchParams(params);
  const queryString = searchParams.toString();
  const response = await apiFetch(
    `/api/leather-types${queryString ? `?${queryString}` : ""}`,
  );

  return handleJsonResponse<LeatherTypePageApi>(response).then(mapLeatherTypePage);
}

export async function fetchAllLeatherTypes(
  params: LeatherTypeListParams = {},
): Promise<LeatherTypeRecord[]> {
  const baseParams = { ...params };
  delete baseParams.page;
  delete baseParams.pageSize;

  const pageSize = params.pageSize ?? 100;
  const leatherTypes: LeatherTypeRecord[] = [];
  let page = 1;

  while (true) {
    const response = await fetchLeatherTypes({
      ...baseParams,
      page,
      pageSize,
    });
    leatherTypes.push(...response.items);

    if (page >= response.pages || leatherTypes.length >= response.total) {
      return leatherTypes;
    }

    page += 1;
  }
}

export async function createLeatherType(name: string): Promise<LeatherTypeRecord> {
  const response = await apiFetch("/api/leather-types", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ name }),
  });

  return handleJsonResponse<LeatherTypeApi>(response).then(mapLeatherType);
}

export async function updateLeatherTypeStatus(
  leatherTypeId: number,
  isActive: boolean,
): Promise<LeatherTypeRecord> {
  const response = await apiFetch(`/api/leather-types/${leatherTypeId}/status`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ is_active: isActive }),
  });

  return handleJsonResponse<LeatherTypeApi>(response).then(mapLeatherType);
}

function mapLeatherTypePage(page: LeatherTypePageApi): LeatherTypePage {
  return {
    items: page.items.map(mapLeatherType),
    total: page.total,
    page: page.page,
    pageSize: page.page_size,
    pages: page.pages,
  };
}

function mapLeatherType(leatherType: LeatherTypeApi): LeatherTypeRecord {
  return {
    id: leatherType.id,
    name: leatherType.name,
    isActive: leatherType.is_active,
    createdAtTs: leatherType.created_at,
    createdAt: formatDate(leatherType.created_at),
    updatedAtTs: leatherType.updated_at,
    updatedAt: formatDate(leatherType.updated_at),
  };
}

function buildLeatherTypeSearchParams(params: LeatherTypeListParams): URLSearchParams {
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
