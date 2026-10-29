import assert from "node:assert/strict";
import test from "node:test";

import {
  buildTimelineRows,
  buildTimelineTicks,
  combineLocalDateTime,
  formatSameOrderCollisionMessage,
  getCrossOrderOverlapSessionIds,
  getEffectiveOrderLinks,
  getTimelineBlockStyle,
  isSameOrderCollisionDetail,
  toLocalDateValue,
  toLocalTimeValue,
} from "../src/shared/lib/workTimeTimeline.ts";

test("projects allocated sessions into order rows", function testAllocatedRows() {
  `
  Проверяем строки распределённой операции:
  - передать одну сессию с положительным временем двух заказов и нулевой связью
  - создать по одному блоку только в строках заказов с распределённым временем
  `;

  const session = {
    id: 7,
    timerType: "operation",
    orderId: 10,
    orderNumber: "10",
    hasAllocations: true,
    allocations: [
      { orderId: 10, orderNumber: "10", allocatedSeconds: 40 },
      { orderId: 11, orderNumber: "10/2", allocatedSeconds: 20 },
      { orderId: 12, orderNumber: "10/3", allocatedSeconds: 0 },
    ],
  };
  const rows = buildTimelineRows([session]);

  assert.deepEqual(
    rows.map((row) => ({
      key: row.key,
      label: row.label,
      entries: row.entries.map((entry) => ({
        key: entry.key,
        sessionId: entry.session.id,
        allocatedSeconds: entry.allocatedSeconds,
      })),
    })),
    [
      {
        key: "order-10",
        label: "Заказ 10",
        entries: [{ key: "7:order-10", sessionId: 7, allocatedSeconds: 40 }],
      },
      {
        key: "order-11",
        label: "Заказ 10/2",
        entries: [{ key: "7:order-11", sessionId: 7, allocatedSeconds: 20 }],
      },
    ],
  );
});

test("clips timeline blocks to the visible period", function testTimelineBlock() {
  `
  Проверяем геометрию блока временной шкалы:
  - передать операцию, начинающуюся до видимого диапазона
  - обрезать блок по левой границе и рассчитать половину ширины
  `;

  assert.deepEqual(getTimelineBlockStyle(0, 15_000, 5_000, 25_000), {
    left: "0%",
    width: "50%",
  });
});

test("builds hourly ticks inside the range", function testTimelineTicks() {
  `
  Проверяем часовую шкалу:
  - передать диапазон с неполным первым часом
  - начать отметки со следующего полного часа
  `;

  const start = new Date(2026, 9, 20, 9, 30).getTime();
  const end = new Date(2026, 9, 20, 12, 0).getTime();
  const ticks = buildTimelineTicks(start, end);

  assert.deepEqual(ticks.map((item) => item.timeLabel), ["10:00", "11:00"]);
  assert.equal(ticks[0].leftPercent, 20);
});

test("preserves seconds when minute fields are unchanged", function testSeconds() {
  `
  Проверяем сохранение точности существующей сессии:
  - передать исходное время с секундами и неизменённые поля даты и минут
  - вернуть исходный timestamp без округления
  `;

  const original = new Date(2026, 9, 20, 10, 15, 37, 450).getTime();
  assert.equal(
    combineLocalDateTime(
      toLocalDateValue(original),
      toLocalTimeValue(original),
      original,
    ),
    original,
  );
});

test("marks overlaps only between different orders", function testOrderOverlaps() {
  `
  Проверяем предупреждения о пересечении заказов:
  - передать пересекающиеся операции разных заказов и служебный таймер
  - выделить только две производственные операции
  `;

  const warningIds = getCrossOrderOverlapSessionIds(
    [
      {
        id: 1,
        timerType: "operation",
        orderId: 10,
        orderNumber: "10",
        hasAllocations: false,
        allocations: [],
        startedAt: 1_000,
        endedAt: 5_000,
      },
      {
        id: 2,
        timerType: "operation",
        orderId: 11,
        orderNumber: "11",
        hasAllocations: false,
        allocations: [],
        startedAt: 4_000,
        endedAt: 6_000,
      },
      {
        id: 3,
        timerType: "break",
        orderId: null,
        orderNumber: null,
        hasAllocations: false,
        allocations: [],
        startedAt: 2_000,
        endedAt: 3_000,
      },
      {
        id: 4,
        timerType: "operation",
        orderId: 20,
        orderNumber: "20",
        hasAllocations: false,
        allocations: [],
        startedAt: 11_000,
        endedAt: 15_000,
      },
      {
        id: 5,
        timerType: "operation",
        orderId: 20,
        orderNumber: "20",
        hasAllocations: false,
        allocations: [],
        startedAt: 14_000,
        endedAt: 16_000,
      },
    ],
    10_000,
  );

  assert.deepEqual([...warningIds].sort(), [1, 2]);
});

test("uses effective allocated orders for overlap warnings", function testAllocatedOverlaps() {
  `
  Проверяем предупреждения распределённых операций:
  - оставить исходный заказ с нулевым временем и распределить время другой части
  - сравнить с пересекающейся операцией исходного заказа
  - выделить обе сессии по их эффективным заказам
  `;

  const allocatedSession = {
    id: 10,
    timerType: "operation",
    orderId: 100,
    orderNumber: "100",
    hasAllocations: true,
    allocations: [
      { orderId: 100, orderNumber: "100", allocatedSeconds: 0 },
      { orderId: 101, orderNumber: "100/2", allocatedSeconds: 60 },
    ],
    startedAt: 1_000,
    endedAt: 5_000,
  };
  const sourceOrderSession = {
    id: 11,
    timerType: "operation",
    orderId: 100,
    orderNumber: "100",
    hasAllocations: false,
    allocations: [],
    startedAt: 2_000,
    endedAt: 4_000,
  };

  assert.deepEqual(getEffectiveOrderLinks(allocatedSession), [
    { orderId: 101, orderNumber: "100/2", allocatedSeconds: 60 },
  ]);
  assert.deepEqual(
    [...getCrossOrderOverlapSessionIds([allocatedSession, sourceOrderSession])].sort(),
    [10, 11],
  );
  assert.deepEqual(
    buildTimelineRows([allocatedSession, sourceOrderSession]).map((row) => row.key),
    ["order-100", "order-101"],
  );
});

test("shows zero-only allocations without restoring effective order", function testZeroAllocations() {
  `
  Проверяем отображение операции при нулевом распределении:
  - передать распределённую сессию без положительных секунд
  - не возвращать исходный orderId как актуальную связь
  - создать отдельную строку с исходным номером заказа
  `;

  const session = {
    id: 12,
    timerType: "operation",
    orderId: 100,
    orderNumber: "100",
    hasAllocations: true,
    allocations: [
      { orderId: 100, orderNumber: "100", allocatedSeconds: 0 },
    ],
    startedAt: 1_000,
    endedAt: 2_000,
  };

  assert.deepEqual(getEffectiveOrderLinks(session), []);
  assert.deepEqual(
    buildTimelineRows([session]).map((row) => ({
      key: row.key,
      label: row.label,
      entries: row.entries.map((entry) => ({
        key: entry.key,
        sessionId: entry.session.id,
        allocatedSeconds: entry.allocatedSeconds,
      })),
    })),
    [
      {
        key: "unallocated-order-100",
        label: "Заказ 100 · без распределённого времени",
        entries: [
          {
            key: "12:unallocated-order-100",
            sessionId: 12,
            allocatedSeconds: 0,
          },
        ],
      },
    ],
  );
  assert.deepEqual([...getCrossOrderOverlapSessionIds([session])], []);
});

test("shows operation without available order", function testMissingOrder() {
  `
  Проверяем отображение операции без доступного заказа:
  - передать производственную сессию без orderId и распределений
  - создать отдельную диагностическую строку
  - сохранить сессию доступной для выбора на графике
  `;

  const session = {
    id: 13,
    timerType: "operation",
    orderId: null,
    orderNumber: null,
    hasAllocations: false,
    allocations: [],
    startedAt: 1_000,
    endedAt: 2_000,
  };

  const rows = buildTimelineRows([session]);

  assert.equal(rows[0].key, "operation-without-order");
  assert.equal(rows[0].label, "Операции без доступного заказа");
  assert.equal(rows[0].entries[0].session.id, 13);
});

test("formats collision timestamps in the client timezone", function testCollisionTime() {
  `
  Проверяем форматирование коллизии:
  - передать UTC timestamp без готовой строки времени
  - отобразить время в заданном часовом поясе клиента
  `;

  const detail = {
    code: "same_order_time_overlap",
    message: "В заказе уже есть пересекающийся интервал.",
    collision: {
      session_id: 7,
      label: "Пошив",
      started_at: Date.UTC(2026, 9, 20, 9),
      ended_at: Date.UTC(2026, 9, 20, 10),
    },
  };

  assert.equal(isSameOrderCollisionDetail(detail), true);
  const message = formatSameOrderCollisionMessage(detail, {
    locale: "ru-RU",
    timeZone: "Europe/Moscow",
  });
  assert.match(message, /Пошив/);
  assert.match(message, /12:00/);
  assert.match(message, /13:00/);
});
