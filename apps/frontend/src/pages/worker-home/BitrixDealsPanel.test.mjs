import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import * as vue from "vue";

const text = fs.readFileSync(new URL("./BitrixDealsPanel.vue", import.meta.url), "utf8").split('<script setup lang="ts">')[1].split("</script>")[0];
const source = ts.createSourceFile("deals.ts", text, ts.ScriptTarget.Latest, true);
const script = source.statements.filter(node => !ts.isImportDeclaration(node)).map(node => node.getText(source)).join("\n");
function setup() {
  const queries = [];
  const details = [];
  let unmount;
  const code = ts.transpileModule(script + "\n({ search, state, category, page, data, selected, detailOpen, load, openDetail, closeDetail });", {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText;
  const app = vm.runInNewContext(code, {
    ...vue, onMounted: () => {}, onBeforeUnmount: callback => { unmount = callback; },
    URLSearchParams, setTimeout, clearTimeout,
    fetchBitrixDeals: query => new Promise(resolve => queries.push({ query: query.toString(), resolve })),
    fetchBitrixDeal: id => new Promise(resolve => details.push({ id, resolve })),
  });
  return { app, queries, details, unmount: () => unmount() };
}

test("deal filters reach API and older responses cannot replace current results", async () => {
  `Проверяем фильтрацию списка:
  - передать поиск, воронку и состояние в API
  - сохранить результат последнего запроса при обратном порядке ответов`;
  const { app, queries, unmount } = setup();
  try {
    const old = app.load();
    app.search.value = "Муза";
    app.category.value = "2";
    app.state.value = "closed";
    await vue.nextTick();
    const current = app.load();
    const query = new URLSearchParams(queries[1].query);
    assert.equal(query.get("search"), "Муза");
    assert.equal(query.get("category_id"), "2");
    assert.equal(query.get("state"), "closed");
    queries[1].resolve({ items: [{ id: 2 }], total: 1, page_size: 25, metadata: {} });
    await current;
    queries[0].resolve({ items: [{ id: 1 }], total: 1, page_size: 25, metadata: {} });
    await old;
    assert.equal(app.data.value.items[0].id, 2);
  } finally { unmount(); }
});

test("closing a deal while loading does not reopen its details", async () => {
  `Проверяем закрытие карточки во время загрузки:
  - открыть сделку и закрыть форму до ответа сервера
  - не отображать полученный после закрытия ответ`;
  const { app, details, unmount } = setup();
  try {
    const pending = app.openDetail(199719);
    app.closeDetail();
    details[0].resolve({ id: 199719, fields: {}, product_rows: [] });
    await pending;
    assert.equal(app.detailOpen.value, false);
    assert.equal(app.selected.value, null);
  } finally { unmount(); }
});
