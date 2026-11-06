import assert from "node:assert/strict";
import test from "node:test";

import {
  canSelectWorkerForOperation,
  workerHasOperationSkill,
} from "../src/shared/lib/assignmentSkills.ts";

test("filters new assignments by skill and preserves current worker", function skillFilter() {
  `
  Проверяем фильтрацию исполнителей по навыку:
  - разрешить нового исполнителя только с навыком операции
  - оставить выбранного исполнителя после удаления навыка
  - запретить новое назначение операции без справочной связи
  `;

  const skilled = { id: 1, skillOperationCatalogEntryIds: [10] };
  const unskilled = { id: 2, skillOperationCatalogEntryIds: [] };

  assert.equal(canSelectWorkerForOperation(skilled, 10, null), true);
  assert.equal(canSelectWorkerForOperation(unskilled, 10, null), false);
  assert.equal(canSelectWorkerForOperation(unskilled, 10, 2), true);
  assert.equal(canSelectWorkerForOperation(skilled, null, null), false);
  assert.equal(workerHasOperationSkill(skilled, 10), true);
  assert.equal(workerHasOperationSkill(unskilled, 10), false);
});
