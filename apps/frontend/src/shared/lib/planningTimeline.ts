import type { PlanningTimelineItem } from "../api/planningTimeline";

const DAY_MS = 86400000;
export const timelineDay = (value: string): number => Date.parse(`${value}T00:00:00Z`) / DAY_MS;
export const dayDate = (day: number): Date => new Date(day * DAY_MS);
export type TimelineView = { start: number; end: number; rowStart: number; rowEnd: number };
export type PlannedBlock = { key: string; item: PlanningTimelineItem; start: number; end: number; lane: number };
export type OperationGroup = { key: string; name: string; firstLane: number; laneCount: number };
export type TimelineLayout = { blocks: PlannedBlock[]; groups: OperationGroup[]; lanes: number; bounds: TimelineView };

export function layoutTimeline(items: PlanningTimelineItem[]): TimelineLayout {
  const grouped = new Map<string, { name: string; items: PlannedBlock[] }>();
  for (const item of items) {
    if (!item.first_planned_date || !item.last_planned_date) continue;
    const start = timelineDay(item.first_planned_date);
    const end = timelineDay(item.last_planned_date) + 1;
    if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) continue;
    const key = item.operation_catalog_entry_id === null ? `name:${item.operation_name}` : `catalog:${item.operation_catalog_entry_id}`;
    const group = grouped.get(key) ?? { name: item.operation_name, items: [] };
    group.items.push({ key: `${item.order_id}:${item.operation_id}`, item, start, end, lane: 0 });
    grouped.set(key, group);
  }
  const groups: OperationGroup[] = [];
  const blocks: PlannedBlock[] = [];
  let lanes = 0;
  for (const [key, group] of [...grouped].sort((a, b) => a[1].name.localeCompare(b[1].name, "ru"))) {
    const ends: number[] = [];
    group.items.sort((a, b) => a.start - b.start || a.end - b.end || a.item.order_id - b.item.order_id || a.item.operation_id - b.item.operation_id);
    for (const block of group.items) {
      let lane = ends.findIndex(end => end <= block.start);
      if (lane < 0) lane = ends.length;
      ends[lane] = block.end;
      block.lane = lanes + lane;
      blocks.push(block);
    }
    groups.push({ key, name: group.name, firstLane: lanes, laneCount: ends.length });
    lanes += ends.length;
  }
  const today = Math.floor(Date.now() / DAY_MS);
  const first = blocks.reduce((value, block) => Math.min(value, block.start), Infinity);
  const last = blocks.reduce((value, block) => Math.max(value, block.end), -Infinity);
  return { blocks, groups, lanes, bounds: { start: blocks.length ? first - 1 : today, end: blocks.length ? last + 1 : today + 7, rowStart: 0, rowEnd: Math.max(lanes, 1) } };
}

export function focusOrder(layout: TimelineLayout, orderId: number): TimelineView | null {
  const blocks = layout.blocks.filter(block => block.item.order_id === orderId);
  if (!blocks.length) return null;
  return {
    start: Math.min(...blocks.map(block => block.start)) - 1,
    end: Math.max(...blocks.map(block => block.end)) + 1,
    rowStart: Math.min(...blocks.map(block => block.lane)),
    rowEnd: Math.max(...blocks.map(block => block.lane)) + 1,
  };
}

export function toggleOrderFocus(layout: TimelineLayout, orderId: number, current: { view: TimelineView; orderId: number | null; previous: TimelineView | null }) {
  if (current.orderId === orderId) return { view: { ...(current.previous ?? layout.bounds) }, orderId: null, previous: null };
  const view = focusOrder(layout, orderId);
  return view ? { view, orderId, previous: { ...(current.previous ?? current.view) } } : current;
}

export function zoomTimeline(view: TimelineView, factor: number, bounds: TimelineView): TimelineView {
  const span = Math.min(bounds.end - bounds.start, Math.max(1, (view.end - view.start) * factor));
  const start = Math.max(bounds.start, Math.min(bounds.end - span, (view.start + view.end - span) / 2));
  return { ...view, start, end: start + span };
}

export function orderColor(orderId: number): string {
  return `hsl(${(orderId * 137.508) % 360} 58% 38%)`;
}

export function defaultTimelineRange(now = new Date()): { from: string; to: string } {
  const format = (date: Date) => `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
  return { from: format(new Date(now.getFullYear(), now.getMonth(), 1)), to: format(new Date(now.getFullYear(), now.getMonth() + 2, 0)) };
}

export function timelineRangeView(layout: TimelineLayout, from: string, to: string): TimelineView | null {
  const start = timelineDay(from);
  const last = timelineDay(to);
  if (!Number.isFinite(start) || !Number.isFinite(last) || last < start) return null;
  if (dayDate(start).toISOString().slice(0, 10) !== from || dayDate(last).toISOString().slice(0, 10) !== to) return null;
  return { start, end: last + 1, rowStart: 0, rowEnd: Math.max(layout.lanes, 1) };
}

export function findTimelineOrders(items: PlanningTimelineItem[], query: string) {
  const needle = query.trim().toLocaleLowerCase("ru");
  if (!needle) return [];
  const orders = new Map<number, { id: number; number: string; product: string; hasDates: boolean }>();
  for (const item of items) {
    if (!item.order_number.toLocaleLowerCase("ru").includes(needle)) continue;
    const order = orders.get(item.order_id) ?? { id: item.order_id, number: item.order_number, product: `${item.product_name} · ${item.product_version}`, hasDates: false };
    order.hasDates ||= item.first_planned_date !== null && item.last_planned_date !== null;
    orders.set(item.order_id, order);
  }
  return [...orders.values()].sort((a, b) => Number(b.number.toLocaleLowerCase("ru") === needle) - Number(a.number.toLocaleLowerCase("ru") === needle) || a.number.localeCompare(b.number, "ru", { numeric: true }));
}

export function projectTimeline(layout: TimelineLayout, view: TimelineView, orderId: number | null, rowHeight = 40) {
  const selectedLanes = new Set(layout.blocks.filter(block => block.item.order_id === orderId).map(block => block.lane));
  const groups: Array<OperationGroup & { top: number }> = [];
  const blocks: Array<PlannedBlock & { top: number; height: number }> = [];
  let height = 0;
  for (const group of layout.groups) {
    const groupBlocks = layout.blocks.filter(block => block.lane >= group.firstLane && block.lane < group.firstLane + group.laneCount);
    if (orderId !== null && !groupBlocks.some(block => block.item.order_id === orderId)) continue;
    if (orderId === null && (group.firstLane >= view.rowEnd || group.firstLane + group.laneCount <= view.rowStart)) continue;
    const visible = groupBlocks.filter(block => block.end > view.start && block.start < view.end);
    const activeLanes = new Set(visible.map(block => block.lane));
    groups.push({ ...group, top: height });
    for (let lane = group.firstLane; lane < group.firstLane + group.laneCount; lane++) {
      if (orderId === null && (lane < view.rowStart || lane >= view.rowEnd)) continue;
      if (orderId !== null && !activeLanes.has(lane) && !selectedLanes.has(lane)) continue;
      const laneHeight = orderId === null || selectedLanes.has(lane) ? rowHeight : rowHeight / 5;
      for (const block of visible.filter(block => block.lane === lane)) {
        const blockHeight = rowHeight * .8 / (orderId === null || block.item.order_id === orderId ? 1 : 5);
        blocks.push({ ...block, top: height + (laneHeight - blockHeight) / 2, height: blockHeight });
      }
      height += laneHeight;
    }
  }
  return { groups, blocks, height: Math.max(rowHeight, height) };
}
