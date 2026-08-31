import { apiFetch, handleJsonResponse } from "@/shared/api/http";

export type WorkOrderAssignment = {
  id: number;
  operationId: number;
  operationName: string;
  workerUserId: number | null;
  workerUserName: string | null;
  workerStatus: WorkerAssignmentStatus;
  workerHiddenAtTs: number | null;
  workerHiddenAt: string | null;
  workerCompletedAtTs: number | null;
  workerCompletedAt: string | null;
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
  hasSpentTime: boolean;
  assignmentsCount: number;
  createdAtTs: number;
  createdAt: string;
  updatedAtTs: number;
  updatedAt: string;
  takenAtTs: number | null;
  takenAt: string | null;
  qualityControlAtTs: number | null;
  qualityControlAt: string | null;
  defectQuantity: number;
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
  hasSpentTime: boolean;
  createdAtTs: number;
  createdAt: string;
  updatedAtTs: number;
  updatedAt: string;
  takenAtTs: number | null;
  takenAt: string | null;
  qualityControlAtTs: number | null;
  qualityControlAt: string | null;
  defectQuantity: number;
  completedAtTs: number | null;
  completedAt: string | null;
  deletedAtTs: number | null;
  deletedAt: string | null;
  assignments: WorkOrderAssignment[];
};

export type WorkOrderSortBy =
  | "completed"
  | "created"
  | "defect"
  | "name"
  | "order_number"
  | "quality_control"
  | "taken";
export type WorkOrderSortDirection = "asc" | "desc";
export type WorkOrderStatusFilter =
  | "all"
  | "created"
  | "in_work"
  | "quality_control"
  | "completed"
  | "deleted";
export type WorkerAssignmentStatus = "in_work" | "hidden" | "completed";

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

export type WorkOrderTimeBreakdownItem = {
  operationId: number | null;
  operationName: string;
  workerUserId: number;
  workerUserName: string;
  elapsedMs: number;
  standardTimeSeconds: number | null;
  averageElapsedMs: number;
};

export type WorkOrderTimeBreakdown = {
  orderId: number;
  items: WorkOrderTimeBreakdownItem[];
  totalElapsedMs: number;
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
  worker_status: WorkerAssignmentStatus;
  worker_hidden_at: number | null;
  worker_completed_at: number | null;
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
  has_spent_time: boolean;
  assignments_count: number;
  created_at: number;
  updated_at: number;
  taken_at: number | null;
  quality_control_at: number | null;
  defect_quantity: number;
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
  has_spent_time: boolean;
  created_at: number;
  updated_at: number;
  taken_at: number | null;
  quality_control_at: number | null;
  defect_quantity: number;
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

type WorkOrderTimeBreakdownItemApi = {
  operation_id: number | null;
  operation_name: string;
  worker_user_id: number;
  worker_user_name: string;
  elapsed_ms: number;
  standard_time_seconds: number | null;
  average_elapsed_ms: number;
};

type WorkOrderTimeBreakdownApi = {
  order_id: number;
  items: WorkOrderTimeBreakdownItemApi[];
  total_elapsed_ms: number;
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

export async function fetchWorkOrderTimeBreakdown(
  orderId: number,
): Promise<WorkOrderTimeBreakdown> {
  const response = await apiFetch(`/api/orders/${orderId}/time-breakdown`);
  return handleJsonResponse<WorkOrderTimeBreakdownApi>(response).then(
    mapWorkOrderTimeBreakdown,
  );
}

export async function fetchWorkerAssignedWorkOrders(
  status: WorkerAssignmentStatus = "in_work",
): Promise<WorkOrderDetail[]> {
  const searchParams = new URLSearchParams({ status });
  const response = await apiFetch(
    `/api/orders/worker-assignments?${searchParams.toString()}`,
  );
  return handleJsonResponse<WorkOrderDetailApi[]>(response).then((orders) =>
    orders.map(mapWorkOrderDetail),
  );
}

export async function updateWorkerAssignmentStatus(
  assignmentId: number,
  status: WorkerAssignmentStatus,
): Promise<WorkOrderDetail> {
  const response = await apiFetch(
    `/api/orders/worker-assignments/${assignmentId}/status`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ status }),
    },
  );

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

export async function updateWorkOrderQualityControlStatus(
  orderId: number,
  isInQualityControl: boolean,
): Promise<WorkOrderDetail> {
  const response = await apiFetch(`/api/orders/${orderId}/quality-control-status`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ is_in_quality_control: isInQualityControl }),
  });

  return handleJsonResponse<WorkOrderDetailApi>(response).then(mapWorkOrderDetail);
}

export async function acceptWorkOrderQualityControl(
  orderId: number,
  defectQuantity: number,
): Promise<WorkOrderDetail> {
  const response = await apiFetch(
    `/api/orders/${orderId}/quality-control-acceptance`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ defect_quantity: defectQuantity }),
    },
  );

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
    workerStatus: assignment.worker_status,
    workerHiddenAtTs: assignment.worker_hidden_at,
    workerHiddenAt:
      assignment.worker_hidden_at === null
        ? null
        : formatDate(assignment.worker_hidden_at),
    workerCompletedAtTs: assignment.worker_completed_at,
    workerCompletedAt:
      assignment.worker_completed_at === null
        ? null
        : formatDate(assignment.worker_completed_at),
  };
}

function mapWorkOrderTimeBreakdown(
  breakdown: WorkOrderTimeBreakdownApi,
): WorkOrderTimeBreakdown {
  return {
    orderId: breakdown.order_id,
    items: breakdown.items.map((item) => ({
      operationId: item.operation_id,
      operationName: item.operation_name,
      workerUserId: item.worker_user_id,
      workerUserName: item.worker_user_name,
      elapsedMs: item.elapsed_ms,
      standardTimeSeconds: item.standard_time_seconds,
      averageElapsedMs: item.average_elapsed_ms,
    })),
    totalElapsedMs: breakdown.total_elapsed_ms,
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
    hasSpentTime: order.has_spent_time,
    assignmentsCount: order.assignments_count,
    createdAtTs: order.created_at,
    createdAt: formatDate(order.created_at),
    updatedAtTs: order.updated_at,
    updatedAt: formatDate(order.updated_at),
    takenAtTs: order.taken_at,
    takenAt: order.taken_at === null ? null : formatDate(order.taken_at),
    qualityControlAtTs: order.quality_control_at,
    qualityControlAt:
      order.quality_control_at === null ? null : formatDate(order.quality_control_at),
    defectQuantity: order.defect_quantity,
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
    hasSpentTime: order.has_spent_time,
    createdAtTs: order.created_at,
    createdAt: formatDate(order.created_at),
    updatedAtTs: order.updated_at,
    updatedAt: formatDate(order.updated_at),
    takenAtTs: order.taken_at,
    takenAt: order.taken_at === null ? null : formatDate(order.taken_at),
    qualityControlAtTs: order.quality_control_at,
    qualityControlAt:
      order.quality_control_at === null ? null : formatDate(order.quality_control_at),
    defectQuantity: order.defect_quantity,
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
