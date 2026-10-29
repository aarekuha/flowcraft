export type TimelineTick = {
  timestamp: number;
  leftPercent: number;
  timeLabel: string;
  dateLabel: string | null;
};

export type TimelineBlockStyle = {
  left: string;
  width: string;
};

export type TimelineOperationInterval = {
  id: number;
  timerType: "preparation" | "operation" | "break" | "idle";
  orderId: number | null;
  orderNumber: string | null;
  hasAllocations: boolean;
  allocations: TimelineAllocation[];
  startedAt: number;
  endedAt: number | null;
};

export type TimelineAllocation = {
  orderId: number;
  orderNumber: string;
  allocatedSeconds: number;
};

export type TimelineRowSource = {
  id: number;
  timerType: "preparation" | "operation" | "break" | "idle";
  orderId: number | null;
  orderNumber: string | null;
  hasAllocations: boolean;
  allocations: TimelineAllocation[];
};

export type TimelineEffectiveOrderLink = {
  orderId: number;
  orderNumber: string | null;
  allocatedSeconds: number | null;
};

export type TimelineRowEntry<T extends TimelineRowSource> = {
  key: string;
  session: T;
  allocatedSeconds: number | null;
};

export type TimelineRow<T extends TimelineRowSource> = {
  key: string;
  label: string;
  entries: TimelineRowEntry<T>[];
};

type TimelineRowTarget = {
  key: string;
  label: string;
  allocatedSeconds: number | null;
};

export type SameOrderCollisionDetail = {
  code: "same_order_time_overlap";
  message: string;
  collision: {
    session_id: number;
    label: string;
    started_at: number;
    ended_at: number | null;
  };
};

type CollisionFormatOptions = {
  locale?: string;
  timeZone?: string;
};

const OPERATION_COLORS = [
  "#2563eb",
  "#7c3aed",
  "#0891b2",
  "#059669",
  "#d97706",
  "#db2777",
  "#4f46e5",
  "#0f766e",
];

export function buildTimelineRows<T extends TimelineRowSource>(
  sessions: T[],
): TimelineRow<T>[] {
  const rows = new Map<string, TimelineRow<T>>();
  for (const session of sessions) {
    const effectiveOrderLinks = getEffectiveOrderLinks(session);
    const targets: TimelineRowTarget[] = session.timerType !== "operation"
      ? [{ key: "service", label: "Служебное время", allocatedSeconds: null }]
      : effectiveOrderLinks.length > 0
        ? effectiveOrderLinks.map((orderLink) => ({
            key: `order-${orderLink.orderId}`,
            label: `Заказ ${orderLink.orderNumber ?? "—"}`,
            allocatedSeconds: orderLink.allocatedSeconds,
          }))
        : [buildUnallocatedOperationTarget(session)];
    for (const target of targets) {
      const row = rows.get(target.key) ?? {
        key: target.key,
        label: target.label,
        entries: [],
      };
      row.entries.push({
        key: `${session.id}:${target.key}`,
        session,
        allocatedSeconds: target.allocatedSeconds,
      });
      rows.set(target.key, row);
    }
  }
  return [...rows.values()].sort((first, second) => {
    if (first.key === "service") {
      return 1;
    }
    if (second.key === "service") {
      return -1;
    }
    return first.label.localeCompare(second.label, "ru");
  });
}

function buildUnallocatedOperationTarget(
  session: TimelineRowSource,
): TimelineRowTarget {
  if (session.hasAllocations) {
    return {
      key: `unallocated-order-${session.orderId ?? "unknown"}`,
      label: session.orderNumber === null
        ? "Операции без распределённого заказа"
        : `Заказ ${session.orderNumber} · без распределённого времени`,
      allocatedSeconds: 0,
    };
  }
  return {
    key: "operation-without-order",
    label: "Операции без доступного заказа",
    allocatedSeconds: null,
  };
}

export function getEffectiveOrderLinks(
  session: TimelineRowSource,
): TimelineEffectiveOrderLink[] {
  if (session.timerType !== "operation") {
    return [];
  }
  if (session.hasAllocations) {
    return session.allocations
      .filter((allocation) => allocation.allocatedSeconds > 0)
      .map((allocation) => ({
        orderId: allocation.orderId,
        orderNumber: allocation.orderNumber,
        allocatedSeconds: allocation.allocatedSeconds,
      }));
  }
  if (session.orderId === null) {
    return [];
  }
  return [{
    orderId: session.orderId,
    orderNumber: session.orderNumber,
    allocatedSeconds: null,
  }];
}

export function buildTimelineTicks(
  rangeStart: number,
  rangeEnd: number,
): TimelineTick[] {
  if (rangeEnd <= rangeStart) {
    return [];
  }

  const first = new Date(rangeStart);
  first.setMinutes(0, 0, 0);
  if (first.getTime() < rangeStart) {
    first.setHours(first.getHours() + 1);
  }

  const ticks: TimelineTick[] = [];
  for (
    let timestamp = first.getTime();
    timestamp < rangeEnd;
    timestamp += 60 * 60 * 1000
  ) {
    const value = new Date(timestamp);
    ticks.push({
      timestamp,
      leftPercent: ((timestamp - rangeStart) / (rangeEnd - rangeStart)) * 100,
      timeLabel: `${String(value.getHours()).padStart(2, "0")}:00`,
      dateLabel:
        value.getHours() === 0 || ticks.length === 0
          ? value.toLocaleDateString("ru-RU", {
              day: "2-digit",
              month: "2-digit",
            })
          : null,
    });
  }
  return ticks;
}

export function getTimelineBlockStyle(
  startedAt: number,
  endedAt: number | null,
  rangeStart: number,
  rangeEnd: number,
  now = Date.now(),
): TimelineBlockStyle {
  const visibleStart = Math.max(startedAt, rangeStart);
  const visibleEnd = Math.min(endedAt ?? now, rangeEnd);
  const duration = Math.max(rangeEnd - rangeStart, 1);
  const leftPercent = ((visibleStart - rangeStart) / duration) * 100;
  const widthPercent = (Math.max(visibleEnd - visibleStart, 0) / duration) * 100;
  return {
    left: `${Math.max(0, Math.min(leftPercent, 100))}%`,
    width: `${Math.max(0, Math.min(widthPercent, 100))}%`,
  };
}

export function getOperationColor(operationId: number | null): string {
  if (operationId === null) {
    return "#64748b";
  }
  return OPERATION_COLORS[Math.abs(operationId) % OPERATION_COLORS.length];
}

export function intervalsOverlap(
  firstStartedAt: number,
  firstEndedAt: number | null,
  secondStartedAt: number,
  secondEndedAt: number | null,
  now = Date.now(),
): boolean {
  const firstEnd = firstEndedAt ?? now;
  const secondEnd = secondEndedAt ?? now;
  return firstStartedAt < secondEnd && secondStartedAt < firstEnd;
}

export function getCrossOrderOverlapSessionIds(
  sessions: TimelineOperationInterval[],
  now = Date.now(),
): Set<number> {
  const result = new Set<number>();
  const operations = sessions
    .map((item) => ({ item, orderLinks: getEffectiveOrderLinks(item) }))
    .filter((entry) => entry.orderLinks.length > 0);
  for (let firstIndex = 0; firstIndex < operations.length; firstIndex += 1) {
    for (
      let secondIndex = firstIndex + 1;
      secondIndex < operations.length;
      secondIndex += 1
    ) {
      const first = operations[firstIndex];
      const second = operations[secondIndex];
      const hasDifferentOrders = first.orderLinks.some((firstLink) =>
        second.orderLinks.some((secondLink) => firstLink.orderId !== secondLink.orderId),
      );
      if (
        hasDifferentOrders
        && intervalsOverlap(
          first.item.startedAt,
          first.item.endedAt,
          second.item.startedAt,
          second.item.endedAt,
          now,
        )
      ) {
        result.add(first.item.id);
        result.add(second.item.id);
      }
    }
  }
  return result;
}

export function toLocalDateValue(timestamp: number): string {
  const value = new Date(timestamp);
  return [
    value.getFullYear(),
    String(value.getMonth() + 1).padStart(2, "0"),
    String(value.getDate()).padStart(2, "0"),
  ].join("-");
}

export function toLocalTimeValue(timestamp: number): string {
  const value = new Date(timestamp);
  return [
    String(value.getHours()).padStart(2, "0"),
    String(value.getMinutes()).padStart(2, "0"),
  ].join(":");
}

export function combineLocalDateTime(
  dateValue: string,
  timeValue: string,
  originalTimestamp?: number,
): number | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(dateValue) || !/^\d{2}:\d{2}$/.test(timeValue)) {
    return null;
  }
  if (
    originalTimestamp !== undefined
    && toLocalDateValue(originalTimestamp) === dateValue
    && toLocalTimeValue(originalTimestamp) === timeValue
  ) {
    return originalTimestamp;
  }
  const timestamp = new Date(`${dateValue}T${timeValue}:00`).getTime();
  return Number.isNaN(timestamp) ? null : timestamp;
}

export function formatTimelineDuration(durationMs: number): string {
  const totalMinutes = Math.max(0, Math.round(durationMs / 60_000));
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;
  if (hours === 0) {
    return `${minutes} мин`;
  }
  return minutes === 0 ? `${hours} ч` : `${hours} ч ${minutes} мин`;
}

export function isSameOrderCollisionDetail(
  value: unknown,
): value is SameOrderCollisionDetail {
  if (
    typeof value !== "object"
    || value === null
    || !("code" in value)
    || value.code !== "same_order_time_overlap"
    || !("message" in value)
    || typeof value.message !== "string"
    || !("collision" in value)
    || typeof value.collision !== "object"
    || value.collision === null
  ) {
    return false;
  }

  const collision = value.collision;
  return (
    "session_id" in collision
    && typeof collision.session_id === "number"
    && "label" in collision
    && typeof collision.label === "string"
    && "started_at" in collision
    && typeof collision.started_at === "number"
    && "ended_at" in collision
    && (typeof collision.ended_at === "number" || collision.ended_at === null)
  );
}

export function formatSameOrderCollisionMessage(
  detail: SameOrderCollisionDetail,
  options: CollisionFormatOptions = {},
): string {
  const formatter = new Intl.DateTimeFormat(options.locale ?? "ru-RU", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: options.timeZone,
  });
  const formatTimestamp = (timestamp: number | null): string => (
    timestamp === null ? "сейчас" : formatter.format(new Date(timestamp))
  );
  return (
    `${detail.message} Конфликт: «${detail.collision.label}» `
    + `(${formatTimestamp(detail.collision.started_at)}–`
    + `${formatTimestamp(detail.collision.ended_at)}).`
  );
}
