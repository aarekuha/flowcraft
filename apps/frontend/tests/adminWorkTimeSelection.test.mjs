import assert from "node:assert/strict";
import test from "node:test";

import { resolveWorkerListChange } from "../src/shared/lib/adminWorkTimeSelection.ts";

test("keeps dirty worker context when reset is rejected", function testRejectedReset() {
  `
  Проверяем отказ от сброса контекста исполнителя:
  - исключить выбранного исполнителя из нового списка
  - отклонить удаление несохранённых изменений
  - запретить применение списка и сохранить признак исчезнувшего исполнителя
  `;

  const change = resolveWorkerListChange(7, [{ id: 8 }], () => false);

  assert.deepEqual(change, {
    canApply: false,
    selectedWorkerMissing: true,
  });
});

test("applies worker list without confirmation when selection remains", function testPreservedSelection() {
  `
  Проверяем сохранение выбранного исполнителя после фильтрации:
  - оставить выбранного исполнителя в новом списке
  - не запрашивать сброс несохранённых изменений
  - разрешить применение нового списка
  `;

  let confirmationRequested = false;
  const change = resolveWorkerListChange(7, [{ id: 7 }], () => {
    confirmationRequested = true;
    return false;
  });

  assert.deepEqual(change, {
    canApply: true,
    selectedWorkerMissing: false,
  });
  assert.equal(confirmationRequested, false);
});
