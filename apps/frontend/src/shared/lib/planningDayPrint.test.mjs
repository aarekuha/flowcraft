import assert from "node:assert/strict";
import test from "node:test";
import { planningDayRows, buildPlanningDayPrintHtml, sortPlanningDay } from "./planningDayPrint.ts";

const day = (workers = []) => ({
  work_date: "2026-11-16", calculation: { is_stale: true },
  items: [{ order_number: "100", product_name: "Кошелёк", product_version: "2", leather_type_name: "Флотер", quantity: 10, operation_name: "Пошив", worker_names: workers }],
});

test("daily rows include six columns and assigned workers", () => {
  `Проверяем данные дневной формы и печати:
  - показать шесть полей и отсутствие назначений
  - перечислить всех назначенных исполнителей в одной строке`;
  assert.deepEqual(planningDayRows(day()), [["100", "Кошелёк · 2", "Флотер", 10, "Пошив", "не назначен"]]);
  assert.equal(planningDayRows(day(["Анна", "Иван"]))[0][5], "Анна, Иван");
});

test("daily print escapes content and identifies date and stale data", () => {
  `Проверяем печатный документ:
  - экранировать текст полей и исполнителей
  - показать выбранную дату и предупреждение об устаревшем расчёте`;
  const data = day(["<script>bad</script>"]);
  data.items[0].product_name = 'A&B <img src=x>';
  const html = buildPlanningDayPrintHtml(data);
  assert.ok(html.includes("16.11.2026"));
  assert.ok(html.includes("исходные данные изменились"));
  assert.ok(html.includes("A&amp;B &lt;img src=x&gt;"));
  assert.ok(html.includes("&lt;script&gt;bad&lt;/script&gt;"));
  assert.ok(!html.includes("<script>"));
  assert.equal((html.match(/<th>/g) || []).length, 6);
});


test("printing leaves unassigned workers blank", () => {
  `Проверяем отсутствие исполнителя при печати:
  - сохранить подпись в экранной таблице и оставить пустую ячейку на бумаге`;
  assert.equal(planningDayRows(day())[0][5], "не назначен");
  const html = buildPlanningDayPrintHtml(day());
  assert.ok(!html.includes("не назначен"));
  assert.ok(html.includes("<td>Пошив</td><td></td>"));
});

for (const key of ["order_number", "product_name", "operation_name", "worker_names"]) {
  test(`sort ${key} in both directions and preserve print order`, () => {
    `Проверяем сортировку дневной таблицы:
    - упорядочить номера естественным образом, названия и исполнителей по алфавиту
    - сохранить обратный порядок в печати и исходные данные без изменений`;
    const data = day();
    const field = (value) => key === "worker_names" ? [value] : value;
    data.items = [
      { ...data.items[0], order_number: "ROW_A", [key]: field(key === "order_number" ? "10" : "Я") },
      { ...data.items[0], order_number: "ROW_B", [key]: field(key === "order_number" ? "2" : "А") },
    ];
    const sorted = sortPlanningDay(data, key);
    assert.equal(sorted.items[0], data.items[1]);
    assert.equal(sortPlanningDay(data, key, true).items[0], data.items[0]);
    assert.notEqual(sorted.items, data.items);
    const html = buildPlanningDayPrintHtml(sorted);
    const first = sorted.items[0].order_number;
    const second = sorted.items[1].order_number;
    assert.ok(html.indexOf(`<td>${first}</td>`) < html.indexOf(`<td>${second}</td>`));
  });
}
