import assert from "node:assert/strict";
import test from "node:test";

import {
  moveProductOperation,
  removeProductStage,
  resolveProductStageFromPointer,
  resizeProductOperation,
} from "../src/shared/lib/productStages.ts";

test("moves an operation and preserves its stage width", function moveOperation() {
  `
  Проверяем перемещение операции между этапами:
  - сохранить ширину смежной операции
  - не вывести диапазон за последний этап
  `;

  const operations = [{ id: 1, stageStart: 1, stageEnd: 2 }];

  assert.deepEqual(moveProductOperation(operations, 1, 3, 4), [
    { id: 1, stageStart: 3, stageEnd: 4 },
  ]);
  assert.deepEqual(moveProductOperation(operations, 1, 4, 4), [
    { id: 1, stageStart: 3, stageEnd: 4 },
  ]);
});

test("removes a stage and shifts all affected operations", function removeStage() {
  `
  Проверяем удаление этапа:
  - сдвинуть вправо расположенные операции влево
  - сократить пересекающую удалённый этап операцию
  - перенести операцию удалённого этапа на предыдущий
  `;

  const operations = [
    { id: 1, stageStart: 1, stageEnd: 1 },
    { id: 2, stageStart: 2, stageEnd: 3 },
    { id: 3, stageStart: 3, stageEnd: 3 },
  ];

  assert.deepEqual(removeProductStage(operations, 2, 3), [
    { id: 1, stageStart: 1, stageEnd: 1 },
    { id: 2, stageStart: 2, stageEnd: 2 },
    { id: 3, stageStart: 2, stageEnd: 2 },
  ]);
  assert.deepEqual(
    removeProductStage([{ id: 4, stageStart: 2, stageEnd: 2 }], 2, 3),
    [{ id: 4, stageStart: 1, stageEnd: 1 }],
  );
  assert.deepEqual(
    removeProductStage(
      [
        { id: 5, stageStart: 1, stageEnd: 2 },
        { id: 6, stageStart: 3, stageEnd: 3 },
      ],
      1,
      3,
    ),
    [
      { id: 5, stageStart: 1, stageEnd: 1 },
      { id: 6, stageStart: 2, stageEnd: 2 },
    ],
  );
  assert.deepEqual(
    removeProductStage(
      [
        { id: 7, stageStart: 2, stageEnd: 3 },
        { id: 8, stageStart: 3, stageEnd: 3 },
      ],
      3,
      3,
    ),
    [
      { id: 7, stageStart: 2, stageEnd: 2 },
      { id: 8, stageStart: 2, stageEnd: 2 },
    ],
  );
  const singleStage = [{ id: 9, stageStart: 1, stageEnd: 1 }];
  assert.equal(removeProductStage(singleStage, 1, 1), singleStage);
});

test("resizes either boundary without inverting the range", function resizeOperation() {
  `
  Проверяем растягивание смежной операции:
  - изменить левую и правую границы
  - не допустить инверсию диапазона
  `;

  const operations = [{ id: 1, stageStart: 2, stageEnd: 3 }];

  assert.deepEqual(resizeProductOperation(operations, 1, "start", 1), [
    { id: 1, stageStart: 1, stageEnd: 3 },
  ]);
  assert.deepEqual(resizeProductOperation(operations, 1, "start", 4), [
    { id: 1, stageStart: 3, stageEnd: 3 },
  ]);
  assert.deepEqual(resizeProductOperation(operations, 1, "end", 1), [
    { id: 1, stageStart: 2, stageEnd: 2 },
  ]);
});

test("resolves stages by aligned block boundaries", function resolveStage() {
  `
  Проверяем привязку блока к визуальным границам этапов:
  - учитывать захват за левую, центральную и правую часть блока
  - различать левую и правую границы на стыке этапов
  - сохранять расчёт при смещённых и неодинаковых ячейках
  `;

  const cellBounds = [
    { stage: 1, left: -80, right: 20 },
    { stage: 2, left: 20, right: 170 },
    { stage: 3, left: 170, right: 270 },
  ];

  assert.equal(resolveProductStageFromPointer(cellBounds, 35, 10, "start"), 2);
  assert.equal(resolveProductStageFromPointer(cellBounds, 95, 70, "start"), 2);
  assert.equal(resolveProductStageFromPointer(cellBounds, 165, 140, "start"), 2);
  assert.equal(resolveProductStageFromPointer(cellBounds, 170, 0, "start"), 3);
  assert.equal(resolveProductStageFromPointer(cellBounds, 170, 0, "end"), 2);
});
