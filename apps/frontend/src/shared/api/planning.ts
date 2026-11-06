import { apiFetch, createRequestError, handleJsonResponse } from "@/shared/api/http";

export type PlanningSettings = {
  displayOffsetDays: number;
  preparationSeconds: number;
  horizonMonths: 1 | 3 | 6 | 12;
  updatedAt: number;
  updatedByUserId: number | null;
};

export type WorkScheduleDay = {
  workDate: string;
  availableSeconds: number;
};

export type WorkScheduleWorker = {
  userId: number;
  userName: string;
  days: WorkScheduleDay[];
};

export type WorkScheduleMonth = {
  month: string;
  daysInMonth: number;
  workers: WorkScheduleWorker[];
};

export type PlanningQueueStage =
  | "created"
  | "cutting"
  | "in_work"
  | "quality_control";

export type PlanningQueueItem = {
  orderId: number;
  position: number;
  orderNumber: string;
  productName: string;
  leatherTypeName: string | null;
  quantity: number;
  stage: PlanningQueueStage;
};

export type PlanningQueue = {
  revision: number;
  items: PlanningQueueItem[];
};

export type ProductionPlanningCalculationStatus =
  | "idle"
  | "pending"
  | "running"
  | "error";

export type ProductionPlanningStatus = {
  calculationStatus: ProductionPlanningCalculationStatus;
  inputRevision: number;
  requestedRevision: number;
  runningRevision: number | null;
  activeRunId: number | null;
  activeRevision: number | null;
  activeCompletedAt: number | null;
  isStale: boolean;
};

export type PlanningOrderForecast = {
  orderId: number;
  orderNumber: string;
  productName: string;
  manualCompletionDate: string | null;
  resourceFinishDate: string | null;
  calculatedFinishDate: string | null;
  status: string;
  issueCodes: string[];
};

export type PlanningOperationForecast = {
  operationId: number;
  operationName: string;
  stageStart: number;
  stageEnd: number;
  standardTimeSeconds: number | null;
  standardTimeSource: "manual" | "statistical" | "missing";
  workloadSeconds: number;
  actualSeconds: number;
  remainingSeconds: number;
  preparationSeconds: number;
  firstPlannedDate: string | null;
  lastPlannedDate: string | null;
  status: string;
  issueCodes: string[];
};

export type PlanningAllocation = {
  userId: number;
  userName: string;
  workDate: string;
  operationId: number;
  workSeconds: number;
  preparationSeconds: number;
};

export type PlanningOrderForecastDetail = PlanningOrderForecast & {
  operations: PlanningOperationForecast[];
  allocations: PlanningAllocation[];
};

export type PlanningWorkloadItem = {
  operationCatalogEntryId: number | null;
  operationName: string;
  plannedSeconds: number;
  remainingSeconds: number;
  ordersCount: number;
  deficitSeconds: number;
};

export type PlanningWorkload = {
  month: string;
  activeRunId: number | null;
  items: PlanningWorkloadItem[];
};

type PlanningSettingsApi = {
  display_offset_days: number;
  preparation_seconds: number;
  horizon_months: 1 | 3 | 6 | 12;
  updated_at: number;
  updated_by_user_id: number | null;
};

type WorkScheduleMonthApi = {
  month: string;
  days_in_month: number;
  workers: Array<{
    user_id: number;
    user_name: string;
    days: Array<{
      work_date: string;
      available_seconds: number;
    }>;
  }>;
};

type PlanningQueueApi = {
  revision: number;
  items: Array<{
    order_id: number;
    position: number;
    order_number: string;
    product_name: string;
    leather_type_name: string | null;
    quantity: number;
    stage: PlanningQueueStage;
  }>;
};

type ProductionPlanningStatusApi = {
  calculation_status: ProductionPlanningCalculationStatus;
  input_revision: number;
  requested_revision: number;
  running_revision: number | null;
  active_run_id: number | null;
  active_revision: number | null;
  active_completed_at: number | null;
  is_stale: boolean;
};

type PlanningOrderForecastApi = {
  order_id: number;
  order_number: string;
  product_name: string;
  manual_completion_date: string | null;
  resource_finish_date: string | null;
  calculated_finish_date: string | null;
  status: string;
  issue_codes: string[];
};

type PlanningOperationForecastApi = {
  operation_id: number;
  operation_name: string;
  stage_start: number;
  stage_end: number;
  standard_time_seconds: number | null;
  standard_time_source: "manual" | "statistical" | "missing";
  workload_seconds: number;
  actual_seconds: number;
  remaining_seconds: number;
  preparation_seconds: number;
  first_planned_date: string | null;
  last_planned_date: string | null;
  status: string;
  issue_codes: string[];
};

type PlanningAllocationApi = {
  user_id: number;
  user_name: string;
  work_date: string;
  operation_id: number;
  work_seconds: number;
  preparation_seconds: number;
};

type PlanningOrderForecastDetailApi = PlanningOrderForecastApi & {
  operations: PlanningOperationForecastApi[];
  allocations: PlanningAllocationApi[];
};

type PlanningWorkloadApi = {
  month: string;
  active_run_id: number | null;
  items: Array<{
    operation_catalog_entry_id: number | null;
    operation_name: string;
    planned_seconds: number;
    remaining_seconds: number;
    orders_count: number;
    deficit_seconds: number;
  }>;
};

export async function fetchProductionPlanningStatus(): Promise<ProductionPlanningStatus> {
  const response = await apiFetch("/api/planning/status");
  return handleJsonResponse<ProductionPlanningStatusApi>(response).then(
    mapProductionPlanningStatus,
  );
}

export async function requestProductionPlanningRecalculation(): Promise<ProductionPlanningStatus> {
  const response = await apiFetch("/api/planning/recalculate", {
    method: "POST",
  });
  return handleJsonResponse<ProductionPlanningStatusApi>(response).then(
    mapProductionPlanningStatus,
  );
}

export async function fetchPlanningOrderForecasts(): Promise<PlanningOrderForecast[]> {
  const response = await apiFetch("/api/planning/results/orders");
  return handleJsonResponse<PlanningOrderForecastApi[]>(response).then(
    (items) => items.map(mapPlanningOrderForecast),
  );
}

export async function fetchPlanningOrderForecastDetail(
  orderId: number,
): Promise<PlanningOrderForecastDetail> {
  const response = await apiFetch(`/api/planning/results/orders/${orderId}`);
  const payload = await handleJsonResponse<PlanningOrderForecastDetailApi>(response);
  return {
    ...mapPlanningOrderForecast(payload),
    operations: payload.operations.map((operation) => ({
      operationId: operation.operation_id,
      operationName: operation.operation_name,
      stageStart: operation.stage_start,
      stageEnd: operation.stage_end,
      standardTimeSeconds: operation.standard_time_seconds,
      standardTimeSource: operation.standard_time_source,
      workloadSeconds: operation.workload_seconds,
      actualSeconds: operation.actual_seconds,
      remainingSeconds: operation.remaining_seconds,
      preparationSeconds: operation.preparation_seconds,
      firstPlannedDate: operation.first_planned_date,
      lastPlannedDate: operation.last_planned_date,
      status: operation.status,
      issueCodes: operation.issue_codes,
    })),
    allocations: payload.allocations.map((allocation) => ({
      userId: allocation.user_id,
      userName: allocation.user_name,
      workDate: allocation.work_date,
      operationId: allocation.operation_id,
      workSeconds: allocation.work_seconds,
      preparationSeconds: allocation.preparation_seconds,
    })),
  };
}

export async function fetchPlanningWorkload(
  month: string,
): Promise<PlanningWorkload> {
  const response = await apiFetch(
    `/api/planning/workload?month=${encodeURIComponent(month)}`,
  );
  const payload = await handleJsonResponse<PlanningWorkloadApi>(response);
  return {
    month: payload.month,
    activeRunId: payload.active_run_id,
    items: payload.items.map((item) => ({
      operationCatalogEntryId: item.operation_catalog_entry_id,
      operationName: item.operation_name,
      plannedSeconds: item.planned_seconds,
      remainingSeconds: item.remaining_seconds,
      ordersCount: item.orders_count,
      deficitSeconds: item.deficit_seconds,
    })),
  };
}

export async function fetchPlanningQueue(): Promise<PlanningQueue> {
  const response = await apiFetch("/api/planning/queue");
  return handleJsonResponse<PlanningQueueApi>(response).then(mapPlanningQueue);
}

export async function reorderPlanningQueue(payload: {
  order_id: number;
  expected_revision: number;
  before_order_id?: number | null;
  after_order_id?: number | null;
  position?: number;
}): Promise<PlanningQueue> {
  const response = await apiFetch("/api/planning/queue", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleJsonResponse<PlanningQueueApi>(response).then(mapPlanningQueue);
}

export async function fetchPlanningSettings(): Promise<PlanningSettings> {
  const response = await apiFetch("/api/planning/settings");
  return handleJsonResponse<PlanningSettingsApi>(response).then(mapSettings);
}

export async function updatePlanningSettings(payload: {
  display_offset_days: number;
  preparation_seconds: number;
  horizon_months: 1 | 3 | 6 | 12;
}): Promise<PlanningSettings> {
  const response = await apiFetch("/api/planning/settings", {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return handleJsonResponse<PlanningSettingsApi>(response).then(mapSettings);
}

export async function fetchWorkSchedule(
  month: string,
): Promise<WorkScheduleMonth> {
  const response = await apiFetch(
    `/api/planning/work-schedule?month=${encodeURIComponent(month)}`,
  );
  return handleJsonResponse<WorkScheduleMonthApi>(response).then((payload) => ({
    month: payload.month,
    daysInMonth: payload.days_in_month,
    workers: payload.workers.map((worker) => ({
      userId: worker.user_id,
      userName: worker.user_name,
      days: worker.days.map((day) => ({
        workDate: day.work_date,
        availableSeconds: day.available_seconds,
      })),
    })),
  }));
}

export async function updateWorkSchedule(payload: {
  user_id: number;
  work_dates: string[];
  available_seconds: number;
}): Promise<void> {
  const response = await apiFetch("/api/planning/work-schedule", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await createRequestError(response);
  }
}

export async function deleteWorkSchedule(payload: {
  user_id: number;
  work_dates: string[];
}): Promise<void> {
  const response = await apiFetch("/api/planning/work-schedule", {
    method: "DELETE",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw await createRequestError(response);
  }
}

function mapSettings(payload: PlanningSettingsApi): PlanningSettings {
  return {
    displayOffsetDays: payload.display_offset_days,
    preparationSeconds: payload.preparation_seconds,
    horizonMonths: payload.horizon_months,
    updatedAt: payload.updated_at,
    updatedByUserId: payload.updated_by_user_id,
  };
}

function mapPlanningQueue(payload: PlanningQueueApi): PlanningQueue {
  return {
    revision: payload.revision,
    items: payload.items.map((item) => ({
      orderId: item.order_id,
      position: item.position,
      orderNumber: item.order_number,
      productName: item.product_name,
      leatherTypeName: item.leather_type_name,
      quantity: item.quantity,
      stage: item.stage,
    })),
  };
}

function mapProductionPlanningStatus(
  payload: ProductionPlanningStatusApi,
): ProductionPlanningStatus {
  return {
    calculationStatus: payload.calculation_status,
    inputRevision: payload.input_revision,
    requestedRevision: payload.requested_revision,
    runningRevision: payload.running_revision,
    activeRunId: payload.active_run_id,
    activeRevision: payload.active_revision,
    activeCompletedAt: payload.active_completed_at,
    isStale: payload.is_stale,
  };
}

function mapPlanningOrderForecast(
  payload: PlanningOrderForecastApi,
): PlanningOrderForecast {
  return {
    orderId: payload.order_id,
    orderNumber: payload.order_number,
    productName: payload.product_name,
    manualCompletionDate: payload.manual_completion_date,
    resourceFinishDate: payload.resource_finish_date,
    calculatedFinishDate: payload.calculated_finish_date,
    status: payload.status,
    issueCodes: payload.issue_codes,
  };
}
