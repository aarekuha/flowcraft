import { apiFetch, createRequestError, handleJsonResponse } from "@/shared/api/http";

export type StatisticsPeriodParams = {
  days?: number;
  dateFrom?: string;
  dateTo?: string;
};

export type StatisticsKpi = {
  totalTrackedMs: number;
  operationMs: number;
  preparationMs: number;
  breakMs: number;
  idleMs: number;
  productiveRatio: number;
  activeOrdersCount: number;
};

export type StatisticsDailyItem = {
  date: string;
  operationMs: number;
  preparationMs: number;
  breakMs: number;
  idleMs: number;
  totalMs: number;
};

export type StatisticsOperationItem = {
  operationId: number;
  operationName: string;
  productName: string;
  productVersion: string;
  totalMs: number;
  sessionsCount: number;
  averageMs: number;
};

export type StatisticsOrderItem = {
  orderId: number;
  orderNumber: string;
  productName: string;
  productVersion: string;
  totalMs: number;
};

export type StatisticsWorkerItem = {
  userId: number;
  userName: string;
  totalMs: number;
  operationMs: number;
  idleMs: number;
  productiveRatio: number;
};

export type StatisticsOverview = {
  days: number;
  dateFrom: string;
  dateTo: string;
  generatedAtTs: number;
  kpis: StatisticsKpi;
  dailyBreakdown: StatisticsDailyItem[];
  topOperations: StatisticsOperationItem[];
  topOrders: StatisticsOrderItem[];
  workers: StatisticsWorkerItem[];
  idleByDay: StatisticsDailyItem[];
};

type StatisticsKpiApi = {
  total_tracked_ms: number;
  operation_ms: number;
  preparation_ms: number;
  break_ms: number;
  idle_ms: number;
  productive_ratio: number;
  active_orders_count: number;
};

type StatisticsDailyItemApi = {
  date: string;
  operation_ms: number;
  preparation_ms: number;
  break_ms: number;
  idle_ms: number;
  total_ms: number;
};

type StatisticsOperationItemApi = {
  operation_id: number;
  operation_name: string;
  product_name: string;
  product_version: string;
  total_ms: number;
  sessions_count: number;
  average_ms: number;
};

type StatisticsOrderItemApi = {
  order_id: number;
  order_number: string;
  product_name: string;
  product_version: string;
  total_ms: number;
};

type StatisticsWorkerItemApi = {
  user_id: number;
  user_name: string;
  total_ms: number;
  operation_ms: number;
  idle_ms: number;
  productive_ratio: number;
};

type StatisticsOverviewApi = {
  days: number;
  date_from: string;
  date_to: string;
  generated_at: number;
  kpis: StatisticsKpiApi;
  daily_breakdown: StatisticsDailyItemApi[];
  top_operations: StatisticsOperationItemApi[];
  top_orders: StatisticsOrderItemApi[];
  workers: StatisticsWorkerItemApi[];
  idle_by_day: StatisticsDailyItemApi[];
};

export async function fetchStatisticsOverview(
  period: number | StatisticsPeriodParams,
): Promise<StatisticsOverview> {
  const response = await apiFetch(
    `/api/statistics/overview?${buildStatisticsQuery(period)}`,
  );
  return handleJsonResponse<StatisticsOverviewApi>(response).then(mapOverview);
}

export async function downloadStatisticsExport(
  period: number | StatisticsPeriodParams,
): Promise<{ blob: Blob; filename: string }> {
  const response = await apiFetch(
    `/api/statistics/export.xlsx?${buildStatisticsQuery(period)}`,
  );
  if (!response.ok) {
    throw await createRequestError(response);
  }

  return {
    blob: await response.blob(),
    filename: getDownloadFilename(response.headers.get("Content-Disposition")),
  };
}

function mapOverview(overview: StatisticsOverviewApi): StatisticsOverview {
  return {
    days: overview.days,
    dateFrom: overview.date_from,
    dateTo: overview.date_to,
    generatedAtTs: overview.generated_at,
    kpis: {
      totalTrackedMs: overview.kpis.total_tracked_ms,
      operationMs: overview.kpis.operation_ms,
      preparationMs: overview.kpis.preparation_ms,
      breakMs: overview.kpis.break_ms,
      idleMs: overview.kpis.idle_ms,
      productiveRatio: overview.kpis.productive_ratio,
      activeOrdersCount: overview.kpis.active_orders_count,
    },
    dailyBreakdown: overview.daily_breakdown.map(mapDailyItem),
    topOperations: overview.top_operations.map((item) => ({
      operationId: item.operation_id,
      operationName: item.operation_name,
      productName: item.product_name,
      productVersion: item.product_version,
      totalMs: item.total_ms,
      sessionsCount: item.sessions_count,
      averageMs: item.average_ms,
    })),
    topOrders: overview.top_orders.map((item) => ({
      orderId: item.order_id,
      orderNumber: item.order_number,
      productName: item.product_name,
      productVersion: item.product_version,
      totalMs: item.total_ms,
    })),
    workers: overview.workers.map((item) => ({
      userId: item.user_id,
      userName: item.user_name,
      totalMs: item.total_ms,
      operationMs: item.operation_ms,
      idleMs: item.idle_ms,
      productiveRatio: item.productive_ratio,
    })),
    idleByDay: overview.idle_by_day.map(mapDailyItem),
  };
}

function buildStatisticsQuery(period: number | StatisticsPeriodParams): string {
  const params = new URLSearchParams();

  if (typeof period === "number") {
    params.set("days", String(period));
    return params.toString();
  }

  if (period.dateFrom && period.dateTo) {
    params.set("date_from", period.dateFrom);
    params.set("date_to", period.dateTo);
    return params.toString();
  }

  params.set("days", String(period.days ?? 14));
  return params.toString();
}

function getDownloadFilename(contentDisposition: string | null): string {
  if (!contentDisposition) {
    return "flowcraft-statistics.xlsx";
  }

  const match = /filename="?(?<filename>[^";]+)"?/i.exec(contentDisposition);
  return match?.groups?.filename ?? "flowcraft-statistics.xlsx";
}

function mapDailyItem(item: StatisticsDailyItemApi): StatisticsDailyItem {
  return {
    date: item.date,
    operationMs: item.operation_ms,
    preparationMs: item.preparation_ms,
    breakMs: item.break_ms,
    idleMs: item.idle_ms,
    totalMs: item.total_ms,
  };
}
