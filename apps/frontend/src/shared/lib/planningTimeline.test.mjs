import assert from "node:assert/strict";
import test from "node:test";
import { layoutTimeline, projectTimeline, toggleOrderFocus, zoomTimeline, timelineDay, orderColor, defaultTimelineRange, timelineRangeView, findTimelineOrders } from "./planningTimeline.ts";

const item = (order, operation, start, end, catalog = operation) => ({ order_id: order, order_number: String(order), operation_id: operation, operation_catalog_entry_id: catalog, operation_name: `Операция ${catalog}`, first_planned_date: start, last_planned_date: end, status: "planned", issue_codes: [], product_name: "Изделие", product_version: "1" });

test("overlapping orders use separate lanes and include the final day", () => {
  `Проверяем дорожки операций:
  - разместить пересекающиеся заказы раздельно, а следующий день на свободной дорожке
  - включить последний день в ширину блока`;
  const layout = layoutTimeline([item(1, 1, "2026-11-01", "2026-11-02"), item(2, 1, "2026-11-02", "2026-11-03"), item(3, 1, "2026-11-03", "2026-11-03")]);
  assert.equal(layout.groups.length, 1);
  assert.equal(layout.lanes, 2);
  assert.equal(layout.blocks[0].lane, layout.blocks[2].lane);
  assert.notEqual(layout.blocks[0].lane, layout.blocks[1].lane);
  assert.equal(layout.blocks[0].end, timelineDay("2026-11-03"));
});

test("order focus fits all operations and restores the exact previous viewport", () => {
  `Проверяем фокус на заказе:
  - включить все операции выбранного заказа по обеим осям
  - при смене заказа и повторном клике вернуть исходный масштаб`;
  const layout = layoutTimeline([item(1, 1, "2026-11-01", "2026-11-03"), item(2, 1, "2026-11-10", "2026-11-12"), item(1, 2, "2026-11-20", "2026-11-23")]);
  const original = zoomTimeline(layout.bounds, .5, layout.bounds);
  let state = { view: original, previous: null, orderId: null };
  state = toggleOrderFocus(layout, 1, state);
  for (const block of layout.blocks.filter(block => block.item.order_id === 1)) {
    assert.ok(state.view.start <= block.start && state.view.end >= block.end);
    assert.ok(state.view.rowStart <= block.lane && state.view.rowEnd > block.lane);
  }
  state = toggleOrderFocus(layout, 2, state);
  state = toggleOrderFocus(layout, 2, state);
  assert.deepEqual(state.view, original);
  assert.equal(state.orderId, null);
});

test("zoom stays within data bounds and missing dates do not become blocks", () => {
  `Проверяем пределы масштаба и отсутствие дат:
  - не строить блок без запланированных дат
  - ограничить приближение одним днём и отдаление полным периодом`;
  const layout = layoutTimeline([item(1, 1, "2026-11-01", "2026-11-01"), item(2, 2, null, null)]);
  assert.equal(layout.blocks.length, 1);
  const close = zoomTimeline(layout.bounds, .0001, layout.bounds);
  assert.equal(close.end - close.start, 1);
  assert.deepEqual(zoomTimeline(close, 10000, layout.bounds), layout.bounds);
  assert.notEqual(orderColor(1), orderColor(2));
  assert.equal(orderColor(1), orderColor(1));
});


test("default range includes the current and next calendar month across years", () => {
  `Проверяем начальный диапазон графика:
  - охватить текущий месяц целиком и следующий месяц
  - корректно перейти из декабря в январь следующего года`;
  assert.deepEqual(defaultTimelineRange(new Date(2026, 10, 13)), { from: "2026-11-01", to: "2026-12-31" });
  assert.deepEqual(defaultTimelineRange(new Date(2026, 11, 24)), { from: "2026-12-01", to: "2027-01-31" });
});

test("selected dates show empty January and focus returns to the selected range", () => {
  `Проверяем период за пределами рассчитанных операций:
  - показать январь даже при завершении прогноза в декабре
  - найти декабрьский заказ и вернуть выбранный январь повторным кликом`;
  const layout = layoutTimeline([item(42, 1, "2026-12-28", "2026-12-30")]);
  const january = timelineRangeView(layout, "2027-01-01", "2027-01-31");
  assert.equal(january.start, timelineDay("2027-01-01"));
  assert.equal(january.end, timelineDay("2027-02-01"));
  let state = { view: january, orderId: null, previous: null };
  state = toggleOrderFocus(layout, 42, state);
  assert.ok(state.view.start < january.start);
  state = toggleOrderFocus(layout, 42, state);
  assert.deepEqual(state.view, january);
  assert.equal(timelineRangeView(layout, "2027-02-01", "2027-01-01"), null);
  assert.equal(timelineRangeView(layout, "", "2027-01-01"), null);
  assert.equal(timelineRangeView(layout, "2027-02-30", "2027-03-01"), null);
});

test("order search deduplicates operations and prioritizes exact numbers", () => {
  `Проверяем поиск по полному и частичному номеру:
  - вернуть каждый заказ один раз и точное совпадение первым
  - сохранить признак отсутствия рассчитанных дат`;
  const matches = findTimelineOrders([item(123, 1, "2027-01-01", "2027-01-02"), item(12, 1, null, null), item(123, 2, "2027-01-04", "2027-01-05")], " 12 ");
  assert.deepEqual(matches.map(order => order.id), [12, 123]);
  assert.equal(matches[0].hasDates, false);
  assert.equal(matches[1].hasDates, true);
  assert.deepEqual(findTimelineOrders([], "12"), []);
});


test("focused projection hides unrelated operations and shrinks other orders fivefold", () => {
  `Проверяем компактное отображение выбранного заказа:
  - убрать операции, отсутствующие в выбранном заказе
  - уменьшить чужие блоки и дорожки в пять раз, сохранив выбранные
  - после снятия фокуса восстановить полный набор строк`;
  const layout = layoutTimeline([
    item(1, 1, "2026-11-01", "2026-11-03"),
    item(2, 1, "2026-11-02", "2026-11-03"),
    item(1, 3, "2026-11-04", "2026-11-06"),
    item(2, 2, "2026-11-02", "2026-11-05"),
  ]);
  const original = projectTimeline(layout, layout.bounds, null);
  const state = toggleOrderFocus(layout, 1, { view: layout.bounds, orderId: null, previous: null });
  const focused = projectTimeline(layout, state.view, state.orderId);
  assert.deepEqual(focused.groups.map(group => group.name), ["Операция 1", "Операция 3"]);
  const selected = focused.blocks.find(block => block.item.order_id === 1);
  const other = focused.blocks.find(block => block.item.order_id === 2);
  assert.equal(selected.height / other.height, 5);
  assert.equal(focused.height, 40 + 8 + 40);
  assert.equal(focused.blocks.filter(block => block.item.order_id === 1).length, 2);
  const restored = toggleOrderFocus(layout, 1, state);
  assert.deepEqual(projectTimeline(layout, restored.view, restored.orderId), original);
});

test("other blocks sharing a selected lane remain compact without shrinking selected blocks", () => {
  `Проверяем общую дорожку непересекающихся заказов:
  - сохранить высоту выбранного блока на общей дорожке
  - уменьшить чужой блок без изменения его временных границ`;
  const layout = layoutTimeline([item(1, 1, "2026-11-01", "2026-11-01"), item(2, 1, "2026-11-02", "2026-11-02")]);
  const projected = projectTimeline(layout, layout.bounds, 1);
  assert.equal(projected.height, 40);
  assert.equal(projected.blocks[0].height, 32);
  assert.equal(projected.blocks[1].height, 6.4);
  assert.equal(projected.blocks[1].start, timelineDay("2026-11-02"));
});
