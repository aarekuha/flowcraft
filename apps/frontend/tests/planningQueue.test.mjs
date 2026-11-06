import assert from "node:assert/strict";
import test from "node:test";

import {
  getPlanningQueueNeighbors,
  movePlanningQueueItem,
} from "../src/shared/lib/planningQueue.ts";

const items = [
  createItem(1, 1),
  createItem(2, 2),
  createItem(3, 3),
  createItem(4, 4),
];

test("moves an order around an occupied position", function moveQueueItem() {
  `
  Проверить локальное перемещение заказа:
  - вставить заказ перед занятым местом
  - сдвинуть остальные позиции
  - перенумеровать отображаемые приоритеты
  `;

  const reordered = movePlanningQueueItem(items, 4, 2, false);

  assert.deepEqual(
    reordered.map((item) => [item.orderId, item.position]),
    [
      [1, 1],
      [4, 2],
      [2, 3],
      [3, 4],
    ],
  );
});

test("builds adjacent order ids for a drag save", function queueNeighbors() {
  `
  Проверить контракт сохранения перетаскивания:
  - вернуть двух соседей для средней позиции
  - вернуть пустую левую границу для первого заказа
  - вернуть пустую правую границу для последнего заказа
  `;

  assert.deepEqual(getPlanningQueueNeighbors(items, 2), {
    beforeOrderId: 1,
    afterOrderId: 3,
  });
  assert.deepEqual(getPlanningQueueNeighbors(items, 1), {
    beforeOrderId: null,
    afterOrderId: 2,
  });
  assert.deepEqual(getPlanningQueueNeighbors(items, 4), {
    beforeOrderId: 3,
    afterOrderId: null,
  });
});

function createItem(orderId, position) {
  return {
    orderId,
    position,
    orderNumber: `ORDER-${orderId}`,
    productName: "Изделие",
    leatherTypeName: null,
    quantity: 1,
    stage: "created",
  };
}
