import { apiFetch, handleJsonResponse } from "@/shared/api/http";
import type { OperationCatalogEntryKind } from "@/shared/api/operationCatalog";

export type WorkOrderAssignment = {
  id: number;
  operationId: number;
  operationName: string;
  operationKind: OperationCatalogEntryKind;
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
  familyId: number | null;
  partNumber: number | null;
  familyBaseOrderNumber: string | null;
  productId: number;
  productName: string;
  productVersion: string;
  leatherTypeId: number | null;
  leatherTypeName: string | null;
  quantity: number;
  plannedCompletionDate: string | null;
  estimatedMinutes: number;
  totalSpentSeconds: number;
  cuttingSpentSeconds: number;
  hasSpentTime: boolean;
  canSplit: boolean;
  splitBlockReason: string | null;
  canMerge: boolean;
  assignmentsCount: number;
  createdAtTs: number;
  createdAt: string;
  updatedAtTs: number;
  updatedAt: string;
  productionStage: WorkOrderProductionStage;
  cuttingStartedAtTs: number | null;
  cuttingStartedAt: string | null;
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
  familyId: number | null;
  partNumber: number | null;
  familyBaseOrderNumber: string | null;
  productId: number;
  productName: string;
  productVersion: string;
  productComment: string | null;
  leatherTypeId: number | null;
  leatherTypeName: string | null;
  quantity: number;
  plannedCompletionDate: string | null;
  estimatedMinutes: number;
  totalSpentSeconds: number;
  cuttingSpentSeconds: number;
  hasSpentTime: boolean;
  quantityChangeAllowed: boolean;
  createdAtTs: number;
  createdAt: string;
  updatedAtTs: number;
  updatedAt: string;
  productionStage: WorkOrderProductionStage;
  cuttingStartedAtTs: number | null;
  cuttingStartedAt: string | null;
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
  | "cutting_started"
  | "created"
  | "defect"
  | "name"
  | "order_number"
  | "planned_completion"
  | "quality_control"
  | "taken";
export type WorkOrderSortDirection = "asc" | "desc";
export type WorkOrderStatusFilter =
  | "all"
  | "created"
  | "cutting"
  | "in_work"
  | "quality_control"
  | "completed"
  | "deleted";
export type WorkOrderProductionStage = "created" | "cutting" | "in_work";
export type WorkerAssignmentStatus = "in_work" | "hidden" | "completed";

export type WorkOrderNumberSearchItem = {
  id: number;
  orderNumber: string;
  stage: Exclude<WorkOrderStatusFilter, "all">;
};

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
  totalStandardTimeSeconds: number;
  totalElapsedMs: number;
};

export type WorkOrderMergeCandidate = {
  id: number;
  orderNumber: string;
  quantity: number;
};

export type WorkOrderSplitResult = {
  source: WorkOrderDetail;
  created: WorkOrderDetail;
};

export type WorkOrderQrTarget = {
  orderReference: string;
  orders: WorkOrderDetail[];
};

export type WorkOrderCreatePayload = {
  planned_completion_date: string | null;
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
  operation_kind: OperationCatalogEntryKind;
  worker_user_id: number | null;
  worker_user_name: string | null;
  worker_status: WorkerAssignmentStatus;
  worker_hidden_at: number | null;
  worker_completed_at: number | null;
};

type WorkOrderSummaryApi = {
  id: number;
  order_number: string;
  family_id: number | null;
  part_number: number | null;
  family_base_order_number: string | null;
  product_id: number;
  product_name: string;
  product_version: string;
  leather_type_id: number | null;
  leather_type_name: string | null;
  quantity: number;
  planned_completion_date: string | null;
  estimated_minutes: number;
  total_spent_seconds: number;
  cutting_spent_seconds: number;
  has_spent_time: boolean;
  can_split: boolean;
  split_block_reason: string | null;
  can_merge: boolean;
  assignments_count: number;
  created_at: number;
  updated_at: number;
  production_stage: WorkOrderProductionStage;
  cutting_started_at: number | null;
  taken_at: number | null;
  quality_control_at: number | null;
  defect_quantity: number;
  completed_at: number | null;
  deleted_at: number | null;
};

type WorkOrderDetailApi = {
  id: number;
  order_number: string;
  family_id: number | null;
  part_number: number | null;
  family_base_order_number: string | null;
  product_id: number;
  product_name: string;
  product_version: string;
  product_comment: string | null;
  leather_type_id: number | null;
  leather_type_name: string | null;
  quantity: number;
  planned_completion_date: string | null;
  estimated_minutes: number;
  total_spent_seconds: number;
  cutting_spent_seconds: number;
  has_spent_time: boolean;
  quantity_change_allowed: boolean;
  created_at: number;
  updated_at: number;
  production_stage: WorkOrderProductionStage;
  cutting_started_at: number | null;
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
  total_standard_time_seconds: number;
  total_elapsed_ms: number;
};

type WorkOrderMergeCandidateApi = {
  id: number;
  order_number: string;
  quantity: number;
};

type WorkOrderSplitResultApi = {
  source: WorkOrderDetailApi;
  created: WorkOrderDetailApi;
};

type WorkOrderQrTargetApi = {
  order_reference: string;
  orders: WorkOrderDetailApi[];
};

type WorkOrderNumberSearchItemApi = {
  id: number;
  order_number: string;
  stage: Exclude<WorkOrderStatusFilter, "all">;
};

export async function fetchWorkOrders(
  params: WorkOrderListParams = {},
): Promise<WorkOrderPage> {
  const searchParams = buildWorkOrderSearchParams(params);
  const queryString = searchParams.toString();
  const response = await apiFetch(`/api/orders${queryString ? `?${queryString}` : ""}`);

  return handleJsonResponse<WorkOrderPageApi>(response).then(mapWorkOrderPage);
}

export async function searchWorkOrdersByNumber(
  search: string,
): Promise<WorkOrderNumberSearchItem[]> {
  const searchParams = new URLSearchParams({ search });
  const response = await apiFetch(
    `/api/orders/order-number-search?${searchParams.toString()}`,
  );
  return handleJsonResponse<WorkOrderNumberSearchItemApi[]>(response).then(
    (items) =>
      items.map((item) => ({
        id: item.id,
        orderNumber: item.order_number,
        stage: item.stage,
      })),
  );
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

export async function fetchWorkerOrdersByQr(params: {
  orderReference?: string;
  legacyOrderId?: number;
}): Promise<WorkOrderQrTarget> {
  const searchParams = new URLSearchParams();
  if (params.orderReference) {
    searchParams.set("order_reference", params.orderReference);
  }
  if (params.legacyOrderId !== undefined) {
    searchParams.set("legacy_order_id", String(params.legacyOrderId));
  }
  const response = await apiFetch(
    `/api/orders/worker-assignments/qr-target?${searchParams.toString()}`,
  );
  return handleJsonResponse<WorkOrderQrTargetApi>(response).then((target) => ({
    orderReference: target.order_reference,
    orders: target.orders.map(mapWorkOrderDetail),
  }));
}

export async function splitWorkOrder(
  orderId: number,
  sourceQuantity: number,
): Promise<WorkOrderSplitResult> {
  const response = await apiFetch(`/api/orders/${orderId}/split`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ source_quantity: sourceQuantity }),
  });
  return handleJsonResponse<WorkOrderSplitResultApi>(response).then((result) => ({
    source: mapWorkOrderDetail(result.source),
    created: mapWorkOrderDetail(result.created),
  }));
}

export async function fetchWorkOrderMergeCandidates(
  orderId: number,
  search = "",
): Promise<WorkOrderMergeCandidate[]> {
  const searchParams = new URLSearchParams();
  if (search.trim()) {
    searchParams.set("search", search.trim());
  }
  const query = searchParams.toString();
  const response = await apiFetch(
    `/api/orders/${orderId}/merge-candidates${query ? `?${query}` : ""}`,
  );
  return handleJsonResponse<WorkOrderMergeCandidateApi[]>(response).then(
    (candidates) =>
      candidates.map((candidate) => ({
        id: candidate.id,
        orderNumber: candidate.order_number,
        quantity: candidate.quantity,
      })),
  );
}

export async function mergeWorkOrders(
  orderId: number,
  includedOrderIds: number[],
): Promise<WorkOrderDetail> {
  const response = await apiFetch(`/api/orders/${orderId}/merge`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ included_order_ids: includedOrderIds }),
  });
  return handleJsonResponse<WorkOrderDetailApi>(response).then(mapWorkOrderDetail);
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

export async function updateWorkOrderPlannedCompletionDate(
  orderId: number,
  plannedCompletionDate: string,
): Promise<WorkOrderDetail> {
  const response = await apiFetch(
    `/api/orders/${orderId}/planned-completion-date`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ planned_completion_date: plannedCompletionDate }),
    },
  );

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

export async function updateWorkOrderProductionStage(
  orderId: number,
  productionStage: WorkOrderProductionStage,
): Promise<WorkOrderDetail> {
  const response = await apiFetch(`/api/orders/${orderId}/production-stage`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ production_stage: productionStage }),
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
    operationKind: assignment.operation_kind,
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
    totalStandardTimeSeconds: breakdown.total_standard_time_seconds,
    totalElapsedMs: breakdown.total_elapsed_ms,
  };
}

function mapWorkOrderSummary(order: WorkOrderSummaryApi): WorkOrderSummary {
  return {
    id: order.id,
    orderNumber: order.order_number,
    familyId: order.family_id,
    partNumber: order.part_number,
    familyBaseOrderNumber: order.family_base_order_number,
    productId: order.product_id,
    productName: order.product_name,
    productVersion: order.product_version,
    leatherTypeId: order.leather_type_id,
    leatherTypeName: order.leather_type_name,
    quantity: order.quantity,
    plannedCompletionDate: order.planned_completion_date,
    estimatedMinutes: order.estimated_minutes,
    totalSpentSeconds: order.total_spent_seconds,
    cuttingSpentSeconds: order.cutting_spent_seconds,
    hasSpentTime: order.has_spent_time,
    canSplit: order.can_split,
    splitBlockReason: order.split_block_reason,
    canMerge: order.can_merge,
    assignmentsCount: order.assignments_count,
    createdAtTs: order.created_at,
    createdAt: formatDate(order.created_at),
    updatedAtTs: order.updated_at,
    updatedAt: formatDate(order.updated_at),
    productionStage: order.production_stage,
    cuttingStartedAtTs: order.cutting_started_at,
    cuttingStartedAt:
      order.cutting_started_at === null ? null : formatDate(order.cutting_started_at),
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
    familyId: order.family_id,
    partNumber: order.part_number,
    familyBaseOrderNumber: order.family_base_order_number,
    productId: order.product_id,
    productName: order.product_name,
    productVersion: order.product_version,
    productComment: order.product_comment,
    leatherTypeId: order.leather_type_id,
    leatherTypeName: order.leather_type_name,
    quantity: order.quantity,
    plannedCompletionDate: order.planned_completion_date,
    estimatedMinutes: order.estimated_minutes,
    totalSpentSeconds: order.total_spent_seconds,
    cuttingSpentSeconds: order.cutting_spent_seconds,
    hasSpentTime: order.has_spent_time,
    quantityChangeAllowed: order.quantity_change_allowed,
    createdAtTs: order.created_at,
    createdAt: formatDate(order.created_at),
    updatedAtTs: order.updated_at,
    updatedAt: formatDate(order.updated_at),
    productionStage: order.production_stage,
    cuttingStartedAtTs: order.cutting_started_at,
    cuttingStartedAt:
      order.cutting_started_at === null ? null : formatDate(order.cutting_started_at),
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
