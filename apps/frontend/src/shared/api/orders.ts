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
  assignments: WorkOrderAssignment[];
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
  assignments: WorkOrderAssignmentApi[];
};

export async function fetchWorkOrders(): Promise<WorkOrderSummary[]> {
  const response = await apiFetch("/api/orders");
  return handleJsonResponse<WorkOrderSummaryApi[]>(response).then((orders) =>
    orders.map(mapWorkOrderSummary),
  );
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
    assignments: order.assignments.map(mapWorkOrderAssignment),
  };
}

function formatDate(value: number): string {
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(value));
}
