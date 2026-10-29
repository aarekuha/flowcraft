import assert from "node:assert/strict";
import test from "node:test";

import { sortAssignmentsForPrint } from "../src/shared/lib/workOrderPrint.ts";

test("orders operation types for printing and preserves group order", function testPrintOrder() {
  `
  Проверяем приоритет операций в печатной форме:
  - передать обычные, смежные и операции кроя вперемешку
  - вывести крой, обычные и смежные операции с исходным порядком внутри групп
  `;

  const assignments = [
    { id: 1, operationKind: "regular" },
    { id: 2, operationKind: "cutting" },
    { id: 3, operationKind: "adjacent" },
    { id: 4, operationKind: "cutting" },
    { id: 5, operationKind: "regular" },
  ];

  assert.deepEqual(
    sortAssignmentsForPrint(assignments).map((assignment) => assignment.id),
    [2, 4, 1, 5, 3],
  );
  assert.deepEqual(assignments.map((assignment) => assignment.id), [1, 2, 3, 4, 5]);
});
