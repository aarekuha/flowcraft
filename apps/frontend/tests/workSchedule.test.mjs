import assert from "node:assert/strict";
import test from "node:test";

import {
  getDateRange,
  getMonthDates,
  getScheduleSelection,
  getScheduleWorkerRange,
  isWeekendDate,
} from "../src/shared/lib/workSchedule.ts";

test("builds inclusive ranges in either direction", function dateRanges() {
  `
  Проверяем выбор календарного диапазона:
  - включить начальный и конечный дни
  - поддержать обратный порядок выбора
  - считать повторный выбор одного дня однодневным диапазоном
  `;

  assert.deepEqual(getDateRange("2026-11-02", "2026-11-05"), [
    "2026-11-02",
    "2026-11-03",
    "2026-11-04",
    "2026-11-05",
  ]);
  assert.deepEqual(getDateRange("2026-11-05", "2026-11-02"), [
    "2026-11-02",
    "2026-11-03",
    "2026-11-04",
    "2026-11-05",
  ]);
  assert.deepEqual(getDateRange("2026-11-05", "2026-11-05"), [
    "2026-11-05",
  ]);
});

test("preserves gaps when editing existing schedule ranges", function scheduleGaps() {
  `
  Проверяем редактирование нескольких заполненных диапазонов:
  - выбрать только существующие рабочие дни
  - сохранить незаполненные промежутки между диапазонами
  `;

  const existingDates = new Set([
    "2026-11-02",
    "2026-11-03",
    "2026-11-09",
    "2026-11-10",
  ]);

  assert.deepEqual(
    getScheduleSelection(
      "2026-11-02",
      "2026-11-10",
      existingDates,
      true,
    ),
    ["2026-11-02", "2026-11-03", "2026-11-09", "2026-11-10"],
  );
  assert.equal(
    getScheduleSelection(
      "2026-11-04",
      "2026-11-06",
      existingDates,
      false,
    ).length,
    3,
  );
});

test("builds month columns and detects weekends", function monthCalendar() {
  `
  Проверяем календарные столбцы месяца:
  - создать все даты выбранного месяца
  - определить субботу и будний день без UTC-сдвига
  `;

  const dates = getMonthDates("2026-11", 30);

  assert.equal(dates.length, 30);
  assert.equal(dates[0], "2026-11-01");
  assert.equal(dates.at(-1), "2026-11-30");
  assert.equal(isWeekendDate("2026-11-07"), true);
  assert.equal(isWeekendDate("2026-11-09"), false);
});


test("selects the entire period with Shift including gaps and weekends", function fullPeriod() {
  `
  Проверяем выбор периода отсутствия с Shift:
  - начать выбор с заполненного рабочего дня
  - включить пустые дни и выходные в прямом и обратном диапазоне
  `;

  const existingDates = new Set(["2026-11-06", "2026-11-09"]);
  const expected = ["2026-11-06", "2026-11-07", "2026-11-08", "2026-11-09"];
  assert.deepEqual(
    getScheduleSelection("2026-11-06", "2026-11-09", existingDates, true, true),
    expected,
  );
  assert.deepEqual(
    getScheduleSelection("2026-11-09", "2026-11-06", existingDates, true, true),
    expected,
  );
});


test("selects employee rows in visible order in both directions", function workerRange() {
  `
  Проверяем диапазон сотрудников:
  - учитывать порядок строк, а не идентификаторы сотрудников
  - включить обе границы и промежуточные строки в любом направлении
  - не выбирать строки при отсутствии границы
  `;
  const workers = [9, 2, 7, 1].map((userId) => ({ userId }));
  assert.deepEqual(getScheduleWorkerRange(workers, 2, 1), workers.slice(1));
  assert.deepEqual(getScheduleWorkerRange(workers, 1, 2), workers.slice(1));
  assert.deepEqual(getScheduleWorkerRange(workers, 7, 7), [workers[2]]);
  assert.deepEqual(getScheduleWorkerRange([...workers].reverse(), 9, 7), [workers[2], workers[1], workers[0]]);
  assert.deepEqual(getScheduleWorkerRange(workers, 999, 2), []);
});
