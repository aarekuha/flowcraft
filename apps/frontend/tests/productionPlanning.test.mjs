import assert from "node:assert/strict";
import test from "node:test";

import {
  formatPlanningDate,
  formatPlanningDuration,
  getPlanningForecastLabel,
  getPlanningIssueLabel,
} from "../src/shared/lib/productionPlanning.ts";

test("formats planning dates and durations", function planningFormats() {
  `
  Проверяем форматирование календарных результатов:
  - не сдвигать календарную дату через часовой пояс
  - отображать часы и минуты без секунд
  `;

  assert.equal(formatPlanningDate("2026-11-05"), "05.11.2026");
  assert.equal(formatPlanningDate(null), "—");
  assert.equal(formatPlanningDuration(5_460), "1 ч 31 мин");
  assert.equal(formatPlanningDuration(59), "59 сек");
});

test("explains unavailable planning forecasts", function planningIssues() {
  `
  Проверяем объяснение отсутствующей даты:
  - показывать специальное сообщение для выхода за горизонт
  - расшифровывать известные причины
  - сохранять диагностический код неизвестной ошибки
  `;

  assert.equal(
    getPlanningForecastLabel(createForecast(["outside_horizon"])),
    "Выходит за пределы периода",
  );
  assert.equal(
    getPlanningIssueLabel("no_skilled_assignee"),
    "У назначенных исполнителей нет требуемого навыка",
  );
  assert.equal(
    getPlanningIssueLabel("unexpected_issue"),
    "Ошибка данных: unexpected_issue",
  );
});

test("prefers calculated date over diagnostic messages", function planningDate() {
  `
  Проверяем приоритет опубликованного прогноза:
  - передать рассчитанную дату вместе с технической диагностикой
  - показать дату как основной результат
  `;

  const forecast = createForecast(["outside_horizon"]);
  forecast.calculatedFinishDate = "2026-12-01";

  assert.equal(getPlanningForecastLabel(forecast), "01.12.2026");
});

function createForecast(issueCodes) {
  return {
    orderId: 1,
    orderNumber: "10001",
    productName: "Изделие",
    manualCompletionDate: null,
    resourceFinishDate: null,
    calculatedFinishDate: null,
    status: "unplanned",
    issueCodes,
  };
}
