import { apiFetch, createRequestError, handleJsonResponse } from "@/shared/api/http";

export type ReportFilters = {
  dateFrom: string;
  dateTo: string;
  productId?: number;
  workerUserId?: number;
  operationCatalogEntryId?: number;
  orderNumber?: string;
  page?: number;
  pageSize?: number;
};

export type ReportFilterOptions = {
  workers: Array<{
    id: number;
    name: string;
    isActive: boolean;
    isDeleted: boolean;
  }>;
  operations: Array<{
    id: number;
    name: string;
    isActive: boolean;
  }>;
};

export type ProductQuantityReportRow = {
  productId: number;
  productName: string;
  monthQuantities: number[];
  dayQuantities: number[];
  totalQuantity: number;
};

export type ProductQuantityReport = {
  dateFrom: string;
  dateTo: string;
  months: string[];
  days: string[];
  items: ProductQuantityReportRow[];
  totalByMonth: number[];
  totalByDay: number[];
  totalQuantity: number;
};

export type ProductTimeOperationReportRow = {
  operationId: number | null;
  operationName: string;
  workerUserId: number;
  workerUserName: string;
  dailyAverageMs: number[];
  averageMs: number;
  totalElapsedMs: number;
  shareOfProductTime: number;
};

export type ProductTimeReportSection = {
  productId: number;
  productName: string;
  rows: ProductTimeOperationReportRow[];
  dailyAverageMs: number[];
  averageMs: number;
  totalElapsedMs: number;
};

export type ProductTimeReport = {
  dateFrom: string;
  dateTo: string;
  days: string[];
  products: ProductTimeReportSection[];
};

export type OrderBatchReportDetail = {
  operationId: number | null;
  operationName: string;
  workerUserId: number | null;
  workerUserName: string;
  elapsedMs: number;
  averageMs: number;
};

export type OrderBatchReportItem = {
  orderId: number;
  orderNumber: string;
  productId: number;
  productName: string;
  leatherTypeName: string | null;
  quantity: number;
  submittedQuantity: number;
  completedAt: number;
  totalElapsedMs: number;
  averageMs: number;
  details: OrderBatchReportDetail[];
};

export type OrderBatchReport = {
  dateFrom: string;
  dateTo: string;
  items: OrderBatchReportItem[];
  total: number;
  page: number;
  pageSize: number;
  pages: number;
};

type ProductQuantityReportApi = {
  date_from: string;
  date_to: string;
  months: string[];
  days: string[];
  items: Array<{
    product_id: number;
    product_name: string;
    month_quantities: number[];
    day_quantities: number[];
    total_quantity: number;
  }>;
  total_by_month: number[];
  total_by_day: number[];
  total_quantity: number;
};

type ReportFilterOptionsApi = {
  workers: Array<{
    id: number;
    name: string;
    is_active: boolean;
    is_deleted: boolean;
  }>;
  operations: Array<{
    id: number;
    name: string;
    is_active: boolean;
  }>;
};

type ProductTimeReportApi = {
  date_from: string;
  date_to: string;
  days: string[];
  products: Array<{
    product_id: number;
    product_name: string;
    rows: Array<{
      operation_id: number | null;
      operation_name: string;
      worker_user_id: number;
      worker_user_name: string;
      daily_average_ms: number[];
      average_ms: number;
      total_elapsed_ms: number;
      share_of_product_time: number;
    }>;
    daily_average_ms: number[];
    average_ms: number;
    total_elapsed_ms: number;
  }>;
};

type OrderBatchReportApi = {
  date_from: string;
  date_to: string;
  items: Array<{
    order_id: number;
    order_number: string;
    product_id: number;
    product_name: string;
    leather_type_name: string | null;
    quantity: number;
    submitted_quantity: number;
    completed_at: number;
    total_elapsed_ms: number;
    average_ms: number;
    details: Array<{
      operation_id: number | null;
      operation_name: string;
      worker_user_id: number | null;
      worker_user_name: string;
      elapsed_ms: number;
      average_ms: number;
    }>;
  }>;
  total: number;
  page: number;
  page_size: number;
  pages: number;
};

export async function fetchProductQuantityReport(
  filters: ReportFilters,
): Promise<ProductQuantityReport> {
  const response = await apiFetch(`/api/reports/products?${buildReportQuery(filters)}`);
  return handleJsonResponse<ProductQuantityReportApi>(response).then((report) => ({
    dateFrom: report.date_from,
    dateTo: report.date_to,
    months: report.months,
    days: report.days,
    items: report.items.map((item) => ({
      productId: item.product_id,
      productName: item.product_name,
      monthQuantities: item.month_quantities,
      dayQuantities: item.day_quantities,
      totalQuantity: item.total_quantity,
    })),
    totalByMonth: report.total_by_month,
    totalByDay: report.total_by_day,
    totalQuantity: report.total_quantity,
  }));
}

export async function fetchReportFilterOptions(): Promise<ReportFilterOptions> {
  const response = await apiFetch("/api/reports/filter-options");
  return handleJsonResponse<ReportFilterOptionsApi>(response).then((options) => ({
    workers: options.workers.map((worker) => ({
      id: worker.id,
      name: worker.name,
      isActive: worker.is_active,
      isDeleted: worker.is_deleted,
    })),
    operations: options.operations.map((operation) => ({
      id: operation.id,
      name: operation.name,
      isActive: operation.is_active,
    })),
  }));
}

export async function fetchProductTimeReport(
  filters: ReportFilters,
): Promise<ProductTimeReport> {
  const response = await apiFetch(`/api/reports/product-time?${buildReportQuery(filters)}`);
  return handleJsonResponse<ProductTimeReportApi>(response).then((report) => ({
    dateFrom: report.date_from,
    dateTo: report.date_to,
    days: report.days,
    products: report.products.map((product) => ({
      productId: product.product_id,
      productName: product.product_name,
      rows: product.rows.map((item) => ({
        operationId: item.operation_id,
        operationName: item.operation_name,
        workerUserId: item.worker_user_id,
        workerUserName: item.worker_user_name,
        dailyAverageMs: item.daily_average_ms,
        averageMs: item.average_ms,
        totalElapsedMs: item.total_elapsed_ms,
        shareOfProductTime: item.share_of_product_time,
      })),
      dailyAverageMs: product.daily_average_ms,
      averageMs: product.average_ms,
      totalElapsedMs: product.total_elapsed_ms,
    })),
  }));
}

export async function fetchOrderBatchReport(
  filters: ReportFilters,
): Promise<OrderBatchReport> {
  const response = await apiFetch(`/api/reports/order-batches?${buildReportQuery(filters)}`);
  return handleJsonResponse<OrderBatchReportApi>(response).then((report) => ({
    dateFrom: report.date_from,
    dateTo: report.date_to,
    items: report.items.map((item) => ({
      orderId: item.order_id,
      orderNumber: item.order_number,
      productId: item.product_id,
      productName: item.product_name,
      leatherTypeName: item.leather_type_name,
      quantity: item.quantity,
      submittedQuantity: item.submitted_quantity,
      completedAt: item.completed_at,
      totalElapsedMs: item.total_elapsed_ms,
      averageMs: item.average_ms,
      details: item.details.map((detail) => ({
        operationId: detail.operation_id,
        operationName: detail.operation_name,
        workerUserId: detail.worker_user_id,
        workerUserName: detail.worker_user_name,
        elapsedMs: detail.elapsed_ms,
        averageMs: detail.average_ms,
      })),
    })),
    total: report.total,
    page: report.page,
    pageSize: report.page_size,
    pages: report.pages,
  }));
}

export async function downloadProductQuantityReport(
  filters: ReportFilters,
): Promise<{ blob: Blob; filename: string }> {
  return downloadReport(`/api/reports/products/export.xlsx?${buildReportQuery(filters)}`);
}

export async function downloadProductTimeReport(
  filters: ReportFilters,
): Promise<{ blob: Blob; filename: string }> {
  return downloadReport(`/api/reports/product-time/export.xlsx?${buildReportQuery(filters)}`);
}

export async function downloadOrderBatchReport(
  filters: ReportFilters,
): Promise<{ blob: Blob; filename: string }> {
  return downloadReport(`/api/reports/order-batches/export.xlsx?${buildReportQuery(filters)}`);
}

function buildReportQuery(filters: ReportFilters): string {
  const params = new URLSearchParams({
    date_from: filters.dateFrom,
    date_to: filters.dateTo,
  });
  if (filters.productId) {
    params.set("product_id", String(filters.productId));
  }
  if (filters.workerUserId) {
    params.set("worker_user_id", String(filters.workerUserId));
  }
  if (filters.operationCatalogEntryId) {
    params.set("operation_catalog_entry_id", String(filters.operationCatalogEntryId));
  }
  if (filters.orderNumber?.trim()) {
    params.set("order_number", filters.orderNumber.trim());
  }
  if (filters.page) {
    params.set("page", String(filters.page));
  }
  if (filters.pageSize) {
    params.set("page_size", String(filters.pageSize));
  }
  return params.toString();
}

async function downloadReport(path: string): Promise<{ blob: Blob; filename: string }> {
  const response = await apiFetch(path);
  if (!response.ok) {
    throw await createRequestError(response);
  }
  return {
    blob: await response.blob(),
    filename: getDownloadFilename(response.headers.get("Content-Disposition")),
  };
}

function getDownloadFilename(contentDisposition: string | null): string {
  if (!contentDisposition) {
    return "flowcraft-report.xlsx";
  }
  const match = /filename="?(?<filename>[^";]+)"?/i.exec(contentDisposition);
  return match?.groups?.filename ?? "flowcraft-report.xlsx";
}
