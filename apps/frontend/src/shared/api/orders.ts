import { apiFetch, handleJsonResponse } from "@/shared/api/http";

export type WorkOrderAssignment = {
  id: number;
  operationId: number;
  operationName: string;
  workerUserId: number;
  workerUserName: string;
};

export type WorkOrderSummary = {
  id: number;
  orderNumber: string;
  productId: number;
  productName: string;
  productVersion: string;
  quantity: number;
  totalSpentMinutes: number;
  assignmentsCount: number;
  createdAtTs: number;
  createdAt: string;
  updatedAtTs: number;
  updatedAt: string;
  completedAtTs: number | null;
  completedAt: string | null;
};

export type WorkOrderDetail = {
  id: number;
  orderNumber: string;
  productId: number;
  productName: string;
  productVersion: string;
  quantity: number;
  totalSpentMinutes: number;
  createdAtTs: number;
  createdAt: string;
  updatedAtTs: number;
  updatedAt: string;
  completedAtTs: number | null;
  completedAt: string | null;
  assignments: WorkOrderAssignment[];
};

export type WorkOrderSortBy = "created" | "completed" | "name";
export type WorkOrderSortDirection = "asc" | "desc";

export type WorkOrderListParams = {
  search?: string;
  includeCompleted?: boolean;
  sortBy?: WorkOrderSortBy;
  sortDirection?: WorkOrderSortDirection;
  page?: number;
  pageSize?: number;
};

export type WorkOrderPage = {
  items: WorkOrderSummary[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
};

export type WorkOrderCreatePayload = {
  order_number: string;
  product_id: number;
  quantity: number;
  total_spent_minutes: number;
  assignments: Array<{
    operation_id: number;
    worker_user_id: number;
  }>;
};

export type WorkOrderUpdateAssignmentsPayload = {
  quantity: number;
  total_spent_minutes: number;
  assignments: WorkOrderCreatePayload["assignments"];
};

type WorkOrderAssignmentApi = {
  id: number;
  operation_id: number;
  operation_name: string;
  worker_user_id: number;
  worker_user_name: string;
};

type WorkOrderSummaryApi = {
  id: number;
  order_number: string;
  product_id: number;
  product_name: string;
  product_version: string;
  quantity: number;
  total_spent_minutes: number;
  assignments_count: number;
  created_at: number;
  updated_at: number;
  completed_at: number | null;
};

type WorkOrderDetailApi = {
  id: number;
  order_number: string;
  product_id: number;
  product_name: string;
  product_version: string;
  quantity: number;
  total_spent_minutes: number;
  created_at: number;
  updated_at: number;
  completed_at: number | null;
  assignments: WorkOrderAssignmentApi[];
};

type WorkOrderPageApi = {
  items: WorkOrderSummaryApi[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
};

export async function fetchWorkOrders(
  params: WorkOrderListParams = {},
): Promise<WorkOrderPage> {
  const searchParams = buildWorkOrderSearchParams(params);
  const queryString = searchParams.toString();
  const response = await apiFetch(`/api/orders${queryString ? `?${queryString}` : ""}`);

  return handleJsonResponse<WorkOrderPageApi>(response).then(mapWorkOrderPage);
}

export async function fetchAllWorkOrders(
  params: WorkOrderListParams = {},
): Promise<WorkOrderSummary[]> {
  const baseParams = { ...params };
  delete baseParams.page;
  delete baseParams.pageSize;

  const pageSize = params.pageSize ?? 100;
  const orders: WorkOrderSummary[] = [];
  let page = 1;

  while (true) {
    const response = await fetchWorkOrders({
      ...baseParams,
      page,
      pageSize,
    });
    orders.push(...response.items);

    if (page >= response.pages || orders.length >= response.total) {
      return orders;
    }

    page += 1;
  }
}

export async function fetchWorkOrder(orderId: number): Promise<WorkOrderDetail> {
  const response = await apiFetch(`/api/orders/${orderId}`);
  return handleJsonResponse<WorkOrderDetailApi>(response).then(mapWorkOrderDetail);
}

export async function createWorkOrder(
  payload: WorkOrderCreatePayload,
): Promise<WorkOrderDetail> {
  const response = await apiFetch("/api/orders", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse<WorkOrderDetailApi>(response).then(mapWorkOrderDetail);
}

export async function updateWorkOrderAssignments(
  orderId: number,
  payload: WorkOrderUpdateAssignmentsPayload,
): Promise<WorkOrderDetail> {
  const response = await apiFetch(`/api/orders/${orderId}/assignments`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse<WorkOrderDetailApi>(response).then(mapWorkOrderDetail);
}

export async function updateWorkOrderStatus(
  orderId: number,
  isCompleted: boolean,
): Promise<WorkOrderDetail> {
  const response = await apiFetch(`/api/orders/${orderId}/status`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ is_completed: isCompleted }),
  });

  return handleJsonResponse<WorkOrderDetailApi>(response).then(mapWorkOrderDetail);
}

function mapWorkOrderAssignment(assignment: WorkOrderAssignmentApi): WorkOrderAssignment {
  return {
    id: assignment.id,
    operationId: assignment.operation_id,
    operationName: assignment.operation_name,
    workerUserId: assignment.worker_user_id,
    workerUserName: assignment.worker_user_name,
  };
}

function mapWorkOrderSummary(order: WorkOrderSummaryApi): WorkOrderSummary {
  return {
    id: order.id,
    orderNumber: order.order_number,
    productId: order.product_id,
    productName: order.product_name,
    productVersion: order.product_version,
    quantity: order.quantity,
    totalSpentMinutes: order.total_spent_minutes,
    assignmentsCount: order.assignments_count,
    createdAtTs: order.created_at,
    createdAt: formatDate(order.created_at),
    updatedAtTs: order.updated_at,
    updatedAt: formatDate(order.updated_at),
    completedAtTs: order.completed_at,
    completedAt: order.completed_at === null ? null : formatDate(order.completed_at),
  };
}

function mapWorkOrderPage(page: WorkOrderPageApi): WorkOrderPage {
  return {
    items: page.items.map(mapWorkOrderSummary),
    total: page.total,
    page: page.page,
    pageSize: page.page_size,
    pages: page.pages,
  };
}

function mapWorkOrderDetail(order: WorkOrderDetailApi): WorkOrderDetail {
  return {
    id: order.id,
    orderNumber: order.order_number,
    productId: order.product_id,
    productName: order.product_name,
    productVersion: order.product_version,
    quantity: order.quantity,
    totalSpentMinutes: order.total_spent_minutes,
    createdAtTs: order.created_at,
    createdAt: formatDate(order.created_at),
    updatedAtTs: order.updated_at,
    updatedAt: formatDate(order.updated_at),
    completedAtTs: order.completed_at,
    completedAt: order.completed_at === null ? null : formatDate(order.completed_at),
    assignments: order.assignments.map(mapWorkOrderAssignment),
  };
}

function buildWorkOrderSearchParams(params: WorkOrderListParams): URLSearchParams {
  const searchParams = new URLSearchParams();

  if (params.search?.trim()) {
    searchParams.set("search", params.search.trim());
  }

  if (params.includeCompleted !== undefined) {
    searchParams.set("include_completed", String(params.includeCompleted));
  }

  if (params.sortBy) {
    searchParams.set("sort_by", params.sortBy);
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
