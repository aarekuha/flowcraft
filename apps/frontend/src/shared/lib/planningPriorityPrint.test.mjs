import assert from "node:assert/strict";
import test from "node:test";
import { buildPriorityPrintHtml } from "./planningPriorityPrint.ts";

test("prints current queue order and forecast values with escaped text", () => {
  `Проверяем печатную таблицу приоритетов:
  - сохранить порядок очереди и значения всех рабочих столбцов
  - вывести текст названий без выполнения HTML
  - повторять заголовок таблицы при печати нескольких страниц`;
  const html = buildPriorityPrintHtml([
    [1, "9629", 'Изделие <script>alert("x")</script>', "Кожа & цвет", 25, "В работе", "20.11.2026", "18.11.2026"],
    [2, "9582", "Обложка", "—", 5, "Крой", "—", "Не рассчитано"],
  ]);
  assert.ok(html.indexOf("9629") < html.indexOf("9582"));
  assert.ok(html.includes("&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;"));
  assert.ok(!html.includes("<script>"));
  assert.ok(html.includes("Кожа &amp; цвет"));
  assert.ok(html.includes("<td>25</td><td>В работе</td><td>20.11.2026</td><td>18.11.2026</td>"));
  assert.ok(html.includes("Плановая дата сдачи"));
  assert.ok(html.includes("<td>Крой</td><td>—</td><td>Не рассчитано</td>"));
  assert.ok(html.includes("table-header-group"));
  assert.ok(!html.includes("<input"));
  assert.ok(!html.includes("<button"));
});
