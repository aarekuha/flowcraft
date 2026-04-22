import { apiFetch, handleJsonResponse } from "@/shared/api/http";

export type TimerType = "preparation" | "operation" | "break" | "idle";

export type WorkerShiftState = {
  id: number;
  startedAtTs: number;
  businessDate: string;
};

export type WorkerTimerAggregate = {
  timerType: TimerType;
  orderId: number | null;
  operationId: number | null;
  elapsedMs: number;
};

export type WorkerActiveTimer = {
  timerType: TimerType;
  orderId: number | null;
  operationId: number | null;
  startedAtTs: number;
};

export type WorkerTimerApiState = {
  shift: WorkerShiftState | null;
  activeTimer: WorkerActiveTimer | null;
  timerTotals: WorkerTimerAggregate[];
};

type WorkerShiftStateApi = {
  id: number;
  started_at: number;
  business_date: string;
};

type WorkerTimerAggregateApi = {
  timer_type: TimerType;
  order_id: number | null;
  operation_id: number | null;
  elapsed_ms: number;
};

type WorkerActiveTimerApi = {
  timer_type: TimerType;
  order_id: number | null;
  operation_id: number | null;
  started_at: number;
};

type WorkerTimerApiStateApi = {
  shift: WorkerShiftStateApi | null;
  active_timer: WorkerActiveTimerApi | null;
  timer_totals: WorkerTimerAggregateApi[];
};

type TimerSwitchPayload = {
  timer_type: TimerType;
  order_id?: number;
  operation_id?: number;
};

export async function fetchWorkerTimerState(): Promise<WorkerTimerApiState> {
  const response = await apiFetch("/api/timers/state");
  return handleJsonResponse<WorkerTimerApiStateApi>(response).then(mapWorkerTimerState);
}

export async function startWorkerDay(): Promise<WorkerTimerApiState> {
  const response = await apiFetch("/api/timers/start-day", {
    method: "POST",
  });
  return handleJsonResponse<WorkerTimerApiStateApi>(response).then(mapWorkerTimerState);
}

export async function endWorkerDay(): Promise<WorkerTimerApiState> {
  const response = await apiFetch("/api/timers/end-day", {
    method: "POST",
  });
  return handleJsonResponse<WorkerTimerApiStateApi>(response).then(mapWorkerTimerState);
}

export async function switchWorkerTimer(
  timerType: TimerType,
  options?: {
    orderId?: number | null;
    operationId?: number | null;
  },
): Promise<WorkerTimerApiState> {
  const payload: TimerSwitchPayload = {
    timer_type: timerType,
  };

  if (options?.orderId != null) {
    payload.order_id = options.orderId;
  }
  if (options?.operationId != null) {
    payload.operation_id = options.operationId;
  }

  const response = await apiFetch("/api/timers/switch", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });

  return handleJsonResponse<WorkerTimerApiStateApi>(response).then(mapWorkerTimerState);
}

function mapWorkerTimerState(state: WorkerTimerApiStateApi): WorkerTimerApiState {
  return {
    shift: state.shift
      ? {
          id: state.shift.id,
          startedAtTs: state.shift.started_at,
          businessDate: state.shift.business_date,
        }
      : null,
    activeTimer: state.active_timer
      ? {
          timerType: state.active_timer.timer_type,
          orderId: state.active_timer.order_id,
          operationId: state.active_timer.operation_id,
          startedAtTs: state.active_timer.started_at,
        }
      : null,
    timerTotals: state.timer_totals.map((item) => ({
      timerType: item.timer_type,
      orderId: item.order_id,
      operationId: item.operation_id,
      elapsedMs: item.elapsed_ms,
    })),
  };
}
