import assert from "node:assert/strict";
import test from "node:test";

import {
  getDateRange,
  getMonthDates,
  getScheduleSelection,
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
