import assert from "node:assert/strict";
import test from "node:test";

import { formatOrderDuration } from "../src/shared/lib/duration.ts";

test("formats stored order seconds for display", () => {
  assert.equal(formatOrderDuration(0), "0 сек");
  assert.equal(formatOrderDuration(59), "59 сек");
  assert.equal(formatOrderDuration(60), "1 мин");
  assert.equal(formatOrderDuration(61), "1 мин 1 сек");
  assert.equal(formatOrderDuration(3_661), "1 ч 1 мин 1 сек");
});
