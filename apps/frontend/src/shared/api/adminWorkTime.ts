import { apiFetch, createRequestError, handleJsonResponse } from "@/shared/api/http";
import type { TimerType } from "@/shared/api/timers";

export type AdminWorkTimeWorker = {
  id: number;
  name: string;
  isActive: boolean;
  isDeleted: boolean;
  canAddTime: boolean;
};

export type AdminWorkTimeAllocation = {
  orderId: number;
  orderNumber: string;
  allocatedSeconds: number;
};

export type AdminWorkTimeSession = {
  id: number;
  shiftId: number;
  workerUserId: number;
  timerType: TimerType;
  label: string;
  orderId: number | null;
  orderNumber: string | null;
  operationId: number | null;
  operationName: string | null;
  startedAt: number;
  endedAt: number | null;
  isActive: boolean;
  hasAllocations: boolean;
  allocatedOrderNumbers: string[];
  allocations: AdminWorkTimeAllocation[];
  editable: boolean;
  blockedReason: string | null;
  updatedAt: number;
};

export type AdminWorkTimeOrder = {
  id: number;
  orderNumber: string;
  productName: string;
  productVersion: string;
  isDeleted: boolean;
};

export type AdminWorkTimeOperation = {
  id: number;
  name: string;
};

export type AdminWorkTimeOverlap = {
  orderId: number;
  orderNumber: string;
};

export type AdminWorkTimeCreatePayload = {
  worker_user_id: number;
  order_id: number;
  operation_id: number;
  started_at: number;
  ended_at: number;
};

export type AdminWorkTimeUpdatePayload = {
  order_id?: number | null;
  operation_id: number | null;
  started_at: number;
  ended_at: number;
  expected_updated_at: number;
};

type AdminWorkTimeWorkerApi = {
  id: number;
  name: string;
  is_active: boolean;
  is_deleted: boolean;
  can_add_time: boolean;
};

type AdminWorkTimeAllocationApi = {
  order_id: number;
  order_number: string;
  allocated_seconds: number;
};

type AdminWorkTimeSessionApi = {
  id: number;
  shift_id: number;
  worker_user_id: number;
  timer_type: TimerType;
  label: string;
  order_id: number | null;
  order_number: string | null;
  operation_id: number | null;
  operation_name: string | null;
  started_at: number;
  ended_at: number | null;
  is_active: boolean;
  has_allocations: boolean;
  allocated_order_numbers: string[];
  allocations: AdminWorkTimeAllocationApi[];
  editable: boolean;
  blocked_reason: string | null;
  updated_at: number;
};

type AdminWorkTimeOrderApi = {
  id: number;
  order_number: string;
  product_name: string;
  product_version: string;
  is_deleted: boolean;
};

type AdminWorkTimeOperationApi = {
  id: number;
  name: string;
};

type AdminWorkTimeOverlapApi = {
  order_id: number;
  order_number: string;
};

export async function fetchAdminWorkTimeWorkers(
  includeInactive = false,
): Promise<AdminWorkTimeWorker[]> {
  const params = new URLSearchParams({ include_inactive: String(includeInactive) });
  const response = await apiFetch(`/api/admin/work-time/workers?${params.toString()}`);
  return handleJsonResponse<AdminWorkTimeWorkerApi[]>(response).then((items) =>
    items.map((item) => ({
      id: item.id,
      name: item.name,
      isActive: item.is_active,
      isDeleted: item.is_deleted,
      canAddTime: item.can_add_time,
    })),
  );
}

export async function fetchAdminWorkTimeSessions(params: {
  workerUserId: number;
  fromTs: number;
  toTs: number;
}): Promise<AdminWorkTimeSession[]> {
  const query = new URLSearchParams({
    worker_user_id: String(params.workerUserId),
    from_ts: String(params.fromTs),
    to_ts: String(params.toTs),
  });
  const response = await apiFetch(`/api/admin/work-time/sessions?${query.toString()}`);
  return handleJsonResponse<AdminWorkTimeSessionApi[]>(response).then((items) =>
    items.map(mapSession),
  );
}

export async function fetchAdminWorkTimeOverlaps(params: {
  workerUserId: number;
  orderId: number;
  startedAt: number;
  endedAt: number;
  excludeSessionId?: number;
}): Promise<AdminWorkTimeOverlap[]> {
  const query = new URLSearchParams({
    worker_user_id: String(params.workerUserId),
    order_id: String(params.orderId),
    started_at: String(params.startedAt),
    ended_at: String(params.endedAt),
  });
  if (params.excludeSessionId !== undefined) {
    query.set("exclude_session_id", String(params.excludeSessionId));
  }
  const response = await apiFetch(`/api/admin/work-time/overlaps?${query.toString()}`);
  return handleJsonResponse<AdminWorkTimeOverlapApi[]>(response).then((items) =>
    items.map((item) => ({
      orderId: item.order_id,
      orderNumber: item.order_number,
    })),
  );
}

export async function searchAdminWorkTimeOrders(
  query: string,
): Promise<AdminWorkTimeOrder[]> {
  const params = new URLSearchParams({ query });
  const response = await apiFetch(
    `/api/admin/work-time/orders/search?${params.toString()}`,
  );
  return handleJsonResponse<AdminWorkTimeOrderApi[]>(response).then((items) =>
    items.map((item) => ({
      id: item.id,
      orderNumber: item.order_number,
      productName: item.product_name,
      productVersion: item.product_version,
      isDeleted: item.is_deleted,
    })),
  );
}

export async function fetchAdminWorkTimeOperations(
  orderId: number,
): Promise<AdminWorkTimeOperation[]> {
  const response = await apiFetch(
    `/api/admin/work-time/orders/${orderId}/operations`,
  );
  return handleJsonResponse<AdminWorkTimeOperationApi[]>(response).then((items) =>
    items.map((item) => ({ id: item.id, name: item.name })),
  );
}

export async function createAdminWorkTimeSession(
  payload: AdminWorkTimeCreatePayload,
): Promise<AdminWorkTimeSession> {
  const response = await apiFetch("/api/admin/work-time/sessions", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleJsonResponse<AdminWorkTimeSessionApi>(response).then(mapSession);
}

export async function updateAdminWorkTimeSession(
  sessionId: number,
  payload: AdminWorkTimeUpdatePayload,
): Promise<AdminWorkTimeSession> {
  const response = await apiFetch(`/api/admin/work-time/sessions/${sessionId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleJsonResponse<AdminWorkTimeSessionApi>(response).then(mapSession);
}

export async function deleteAdminWorkTimeSession(
  sessionId: number,
  expectedUpdatedAt: number,
): Promise<void> {
  const params = new URLSearchParams({
    expected_updated_at: String(expectedUpdatedAt),
  });
  const response = await apiFetch(
    `/api/admin/work-time/sessions/${sessionId}?${params.toString()}`,
    { method: "DELETE" },
  );
  if (!response.ok) {
    throw await createRequestError(response);
  }
}

function mapSession(item: AdminWorkTimeSessionApi): AdminWorkTimeSession {
  return {
    id: item.id,
    shiftId: item.shift_id,
    workerUserId: item.worker_user_id,
    timerType: item.timer_type,
    label: item.label,
    orderId: item.order_id,
    orderNumber: item.order_number,
    operationId: item.operation_id,
    operationName: item.operation_name,
    startedAt: item.started_at,
    endedAt: item.ended_at,
    isActive: item.is_active,
    hasAllocations: item.has_allocations,
    allocatedOrderNumbers: item.allocated_order_numbers,
    allocations: item.allocations.map((allocation) => ({
      orderId: allocation.order_id,
      orderNumber: allocation.order_number,
      allocatedSeconds: allocation.allocated_seconds,
    })),
    editable: item.editable,
    blockedReason: item.blocked_reason,
    updatedAt: item.updated_at,
  };
}
