import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import * as vue from "vue";

const sourceText = fs.readFileSync(new URL("./BitrixPanel.vue", import.meta.url), "utf8").split('<script setup lang="ts">')[1].split("</script>")[0];
const source = ts.createSourceFile("bitrix.ts", sourceText, ts.ScriptTarget.Latest, true);
const script = source.statements.filter(node => !ts.isImportDeclaration(node)).map(node => node.getText(source)).join("\n");
function setup() {
  const calls = [];
  const data = {
    items: [
      { id: 10, name: "Товар А", present: true, active: true, mapped_product_id: null },
      { id: 11, name: "Товар Б", present: true, active: false, mapped_product_id: null },
      { id: 12, name: "Занят", present: true, active: true, mapped_product_id: 2 },
    ],
    products: [{ id: 1, name: "Изделие", version: "2", bitrix_ids: [] }], metadata: {},
  };
  let unmount;
  const context = {
    ...vue, defineProps: () => ({}), onMounted: () => {}, onBeforeUnmount: callback => { unmount = callback; },
    fetchBitrixCatalog: async () => structuredClone(data),
    cancelBitrixSync: async job => { calls.push(job); },
    fetchBitrixStatus: async () => ({ configured: true, syncing: false, job_id: null }),
    saveBitrixSettings: async value => { calls.push(value); return { configured: true, syncing: false }; },
    saveBitrixMapping: async (id, ids) => { calls.push([id, [...ids]]); data.products[0].bitrix_ids = [...ids]; },
    clearTimeout, setTimeout,
  };
  const code = ts.transpileModule(script + "\n({ catalog, drafts, webhook, loadCatalog, options, addMapping, saveRow, saveSettings, status, products, mappingFilter, productSearch, cancelSync, cancelling });", {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText;
  const app = vm.runInNewContext(code, context);
  return { app, data, calls, unmount: () => unmount() };
}

test("mapping selection preserves unsaved edits across catalog refresh", async () => {
  `Проверяем выбор нескольких товаров:
  - исключить занятые ID и сохранить выбранные ID при обновлении каталога
  - передать выбранные ID при сохранении строки`;
  const { app, calls, unmount } = setup();
  try {
    await app.loadCatalog();
    const product = app.catalog.value.products[0];
    assert.deepEqual(Array.from(app.options(product), item => item.id), [10, 11]);
    app.addMapping(1, 10);
    app.addMapping(1, 11);
    await app.loadCatalog();
    assert.deepEqual(Array.from(app.drafts.value[1]), [10, 11]);
    await app.saveRow(app.catalog.value.products[0]);
    assert.deepEqual(calls, [[1, [10, 11]]]);
  } finally { unmount(); }
});

test("webhook input clears after successful save and on unmount", async () => {
  `Проверяем очистку секретного поля:
  - отправить введённое значение и показать только признак настройки
  - очистить оставшееся значение при закрытии раздела`;
  const { app, calls, unmount } = setup();
  app.webhook.value = "test-secret";
  await app.saveSettings();
  assert.deepEqual(calls, ["test-secret"]);
  assert.equal(app.webhook.value, "");
  assert.equal(app.status.value.configured, true);
  app.webhook.value = "replacement";
  unmount();
  assert.equal(app.webhook.value, "");
});


test("mapping filters distinguish mapped, unneeded and pending products", () => {
  `Проверяем фильтрацию сопоставлений:
  - разделить сопоставленные изделия, исключённые из сопоставления и ожидающие связи
  - совместить выбранный статус с поиском`;
  const { app, unmount } = setup();
  try {
    app.catalog.value.products = [
      { id: 1, name: "Сумка", version: "1", bitrix_ids: [10], mapping_not_required: false },
      { id: 2, name: "Ремень", version: "1", bitrix_ids: [], mapping_not_required: true },
      { id: 3, name: "Чехол", version: "1", bitrix_ids: [], mapping_not_required: false },
    ];
    for (const [filter, id] of [["mapped", 1], ["not-required", 2], ["unmapped", 3]]) {
      app.mappingFilter.value = filter;
      assert.deepEqual(Array.from(app.products.value, product => product.id), [id]);
    }
    app.productSearch.value = "Сумка";
    assert.equal(app.products.value.length, 0);
    app.mappingFilter.value = "mapped";
    assert.equal(app.products.value[0].id, 1);
  } finally { unmount(); }
});


test("cancel sends the observed job ID and refreshes status", async () => {
  `Проверяем кнопку прерывания:
  - отправить идентификатор текущего задания
  - обновить состояние после отмены и снять блокировку кнопки`;
  const { app, calls, unmount } = setup();
  try {
    app.status.value = { configured: true, syncing: true, job_id: "job-1" };
    await app.cancelSync();
    assert.deepEqual(calls, ["job-1"]);
    assert.equal(app.status.value.syncing, false);
    assert.equal(app.cancelling.value, false);
  } finally { unmount(); }
});
