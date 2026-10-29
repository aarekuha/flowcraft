import assert from "node:assert/strict";
import test from "node:test";

import { resolveAdminWorkTimeFormPolicy } from "../src/shared/lib/adminWorkTimePolicy.ts";

test("keeps saving available during advisory overlap check", function testAdvisoryCheck() {
  `
  Проверяем неблокирующую проверку пересечений разных заказов:
  - передать валидную изменённую форму с незавершённой проверкой предупреждения
  - разрешить сохранение и сохранить признак выполняющейся проверки
  `;

  const policy = resolveAdminWorkTimeFormPolicy({
    editorActive: true,
    editable: true,
    dirty: true,
    hasBlockingError: false,
    saving: false,
    advisoryOverlapCheckPending: true,
  });

  assert.deepEqual(policy, {
    canSave: true,
    advisoryOverlapCheckPending: true,
  });
});

test("blocks saving on form collision", function testBlockingCollision() {
  `
  Проверяем блокирующую ошибку формы:
  - передать изменённую форму с коллизией внутри заказа
  - запретить сохранение независимо от состояния предупреждающей проверки
  `;

  const policy = resolveAdminWorkTimeFormPolicy({
    editorActive: true,
    editable: true,
    dirty: true,
    hasBlockingError: true,
    saving: false,
    advisoryOverlapCheckPending: false,
  });

  assert.equal(policy.canSave, false);
});
