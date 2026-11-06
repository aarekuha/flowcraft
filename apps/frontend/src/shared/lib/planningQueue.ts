import type { PlanningQueueItem } from "@/shared/api/planning";

export type PlanningQueueNeighbors = {
  beforeOrderId: number | null;
  afterOrderId: number | null;
};

export function movePlanningQueueItem(
  items: PlanningQueueItem[],
  orderId: number,
  targetOrderId: number,
  placeAfterTarget: boolean,
): PlanningQueueItem[] {
  const movingIndex = items.findIndex((item) => item.orderId === orderId);
  const targetIndex = items.findIndex((item) => item.orderId === targetOrderId);
  if (movingIndex < 0 || targetIndex < 0 || movingIndex === targetIndex) {
    return items;
  }

  const reordered = [...items];
  const [movingItem] = reordered.splice(movingIndex, 1);
  let insertionIndex = targetIndex + (placeAfterTarget ? 1 : 0);
  if (movingIndex < insertionIndex) {
    insertionIndex -= 1;
  }
  reordered.splice(insertionIndex, 0, movingItem);
  return reordered.map((item, index) => ({ ...item, position: index + 1 }));
}

export function getPlanningQueueNeighbors(
  items: PlanningQueueItem[],
  orderId: number,
): PlanningQueueNeighbors | null {
  const index = items.findIndex((item) => item.orderId === orderId);
  if (index < 0) {
    return null;
  }
  return {
    beforeOrderId: index > 0 ? items[index - 1].orderId : null,
    afterOrderId: index + 1 < items.length ? items[index + 1].orderId : null,
  };
}
