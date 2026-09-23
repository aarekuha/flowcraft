import assert from "node:assert/strict";
import test from "node:test";

import {
  clearReportFilterIds,
  formatReportCompletionDate,
  formatReportDay,
  formatReportMonth,
  formatReportProductName,
  matchesReportFilter,
  toggleReportFilterId,
} from "../src/shared/lib/reportFormatting.ts";

test("formats report periods with Russian month names and a short year", () => {
  assert.equal(formatReportMonth("2026-09"), "Сентябрь 26");
  assert.equal(formatReportDay("2026-09-22"), "22.09.26");
  assert.equal(
    formatReportCompletionDate(Date.UTC(2026, 8, 22, 12)),
    "22.09.26",
  );
});

test("formats a product name with its version", () => {
  assert.equal(formatReportProductName("Сумка City", "1.2"), "Сумка City (1.2)");
});

test("matches report filter values by a case-insensitive partial query", () => {
  assert.equal(matchesReportFilter("Сумка City (1.2)", "city"), true);
  assert.equal(matchesReportFilter("Ирина Соколова", "  СОКОЛ  "), true);
  assert.equal(matchesReportFilter("Пошив", "крой"), false);
});

test("toggles multiple values and clears them when all is selected", () => {
  assert.deepEqual(toggleReportFilterId([2], 4), [2, 4]);
  assert.deepEqual(toggleReportFilterId([2, 4], 2), [4]);
  assert.deepEqual(clearReportFilterIds(), []);
});
