import assert from "node:assert/strict";
import test from "node:test";

import {
  formatStandardTimeInput,
  parseStandardTimeInput,
} from "../src/shared/lib/standardTime.ts";

test("parses valid standard time input", () => {
  assert.equal(parseStandardTimeInput("01:30"), 90);
  assert.equal(parseStandardTimeInput("120:05"), 7_205);
  assert.equal(parseStandardTimeInput(""), null);
});

test("rejects incomplete and invalid standard time input", () => {
  assert.equal(parseStandardTimeInput("1"), undefined);
  assert.equal(parseStandardTimeInput("01:60"), undefined);
  assert.equal(parseStandardTimeInput("text"), undefined);
});

test("formats standard time for the controlled input", () => {
  assert.equal(formatStandardTimeInput(90), "01:30");
  assert.equal(formatStandardTimeInput(7_205), "120:05");
  assert.equal(formatStandardTimeInput(null), "");
});
