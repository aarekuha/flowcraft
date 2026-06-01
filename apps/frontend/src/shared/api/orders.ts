import { apiFetch, handleJsonResponse } from "@/shared/api/http";

export type WorkOrderAssignment = {
  id: number;
  operationId: number;
  operationName: string;
  workerUserId: number | null;
  workerUserName: string | null;
};

export type WorkOrderSummary = {
  id: number;
  orderNumber: string;
  productId: number;
  productName: string;
  productVersion: string;
  leatherTypeId: number | null;
  leatherTypeName: string | null;
  quantity: number;
  estimatedMinutes: number;
  totalSpentMinutes: number;
  assignmentsCount: number;
  createdAtTs: number;
  createdAt: string;
  updatedAtTs: number;
  updatedAt: string;
  takenAtTs: number | null;
  takenAt: string | null;
  completedAtTs: number | null;
  completedAt: string | null;
  deletedAtTs: number | null;
  deletedAt: string | null;
};

export type WorkOrderDetail = {
  id: number;
  orderNumber: string;
  productId: number;
  productName: string;
  productVersion: string;
  leatherTypeId: number | null;
  leatherTypeName: string | null;
  quantity: number;
  estimatedMinutes: number;
  totalSpentMinutes: number;
  createdAtTs: number;
  createdAt: string;
  updatedAtTs: number;
  updatedAt: string;
  takenAtTs: number | null;
  takenAt: string | null;
  completedAtTs: number | null;
  completedAt: string | null;
  deletedAtTs: number | null;
  deletedAt: string | null;
  assignments: WorkOrderAssignment[];
};

export type WorkOrderSortBy = "created" | "completed" | "name";
export type WorkOrderSortDirection = "asc" | "desc";
export type WorkOrderStatusFilter =
  | "all"
  | "created"
  | "in_work"
  | "completed"
  | "deleted";

export type WorkOrderListParams = {
  search?: string;
  includeCompleted?: boolean;
  status?: WorkOrderStatusFilter;
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
  leather_type_id?: number | null;
  quantity: number;
  estimated_minutes: number;
  assignments: Array<{
    operation_id: number;
    worker_user_id: number | null;
  }>;
};

export type WorkOrderUpdateAssignmentsPayload = {
  leather_type_id?: number | null;
  quantity: number;
  estimated_minutes: number;
  assignments: WorkOrderCreatePayload["assignments"];
};

type WorkOrderAssignmentApi = {
  id: number;
  operation_id: number;
  operation_name: string;
  worker_user_id: number | null;
  worker_user_name: string | null;
};

type WorkOrderSummaryApi = {
  id: number;
  order_number: string;
  product_id: number;
  product_name: string;
  product_version: string;
  leather_type_id: number | null;
  leather_type_name: string | null;
  quantity: number;
  estimated_minutes: number;
  total_spent_minutes: number;
  assignments_count: number;
  created_at: number;
  updated_at: number;
  taken_at: number | null;
  completed_at: number | null;
  deleted_at: number | null;
};

type WorkOrderDetailApi = {
  id: number;
  order_number: string;
  product_id: number;
  product_name: string;
  product_version: string;
  leather_type_id: number | null;
  leather_type_name: string | null;
  quantity: number;
  estimated_minutes: number;
  total_spent_minutes: number;
  created_at: number;
  updated_at: number;
  taken_at: number | null;
  completed_at: number | null;
  deleted_at: number | null;
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

export async function fetchWorkerAssignedWorkOrders(): Promise<WorkOrderDetail[]> {
  const response = await apiFetch("/api/orders/worker-assignments");
  return handleJsonResponse<WorkOrderDetailApi[]>(response).then((orders) =>
    orders.map(mapWorkOrderDetail),
  );
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

export async function updateWorkOrderTakenStatus(
  orderId: number,
  isTaken: boolean,
): Promise<WorkOrderDetail> {
  const response = await apiFetch(`/api/orders/${orderId}/taken-status`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ is_taken: isTaken }),
  });

  return handleJsonResponse<WorkOrderDetailApi>(response).then(mapWorkOrderDetail);
}

export async function updateWorkOrderDeletedStatus(
  orderId: number,
  isDeleted: boolean,
): Promise<WorkOrderDetail> {
  const response = await apiFetch(`/api/orders/${orderId}/deleted-status`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ is_deleted: isDeleted }),
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
    leatherTypeId: order.leather_type_id,
    leatherTypeName: order.leather_type_name,
    quantity: order.quantity,
    estimatedMinutes: order.estimated_minutes,
    totalSpentMinutes: order.total_spent_minutes,
    assignmentsCount: order.assignments_count,
    createdAtTs: order.created_at,
    createdAt: formatDate(order.created_at),
    updatedAtTs: order.updated_at,
    updatedAt: formatDate(order.updated_at),
    takenAtTs: order.taken_at,
    takenAt: order.taken_at === null ? null : formatDate(order.taken_at),
    completedAtTs: order.completed_at,
    completedAt: order.completed_at === null ? null : formatDate(order.completed_at),
    deletedAtTs: order.deleted_at,
    deletedAt: order.deleted_at === null ? null : formatDate(order.deleted_at),
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
    leatherTypeId: order.leather_type_id,
    leatherTypeName: order.leather_type_name,
    quantity: order.quantity,
    estimatedMinutes: order.estimated_minutes,
    totalSpentMinutes: order.total_spent_minutes,
    createdAtTs: order.created_at,
    createdAt: formatDate(order.created_at),
    updatedAtTs: order.updated_at,
    updatedAt: formatDate(order.updated_at),
    takenAtTs: order.taken_at,
    takenAt: order.taken_at === null ? null : formatDate(order.taken_at),
    completedAtTs: order.completed_at,
    completedAt: order.completed_at === null ? null : formatDate(order.completed_at),
    deletedAtTs: order.deleted_at,
    deletedAt: order.deleted_at === null ? null : formatDate(order.deleted_at),
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

  if (params.status) {
    searchParams.set("status", params.status);
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
