import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";
import * as vue from "vue";

const sourceText = fs.readFileSync(new URL("./BitrixProductPicker.vue", import.meta.url), "utf8").split('<script setup lang="ts">')[1].split("</script>")[0];
const source = ts.createSourceFile("picker.ts", sourceText, ts.ScriptTarget.Latest, true);
const script = source.statements.filter(node => !ts.isImportDeclaration(node)).map(node => node.getText(source)).join("\n");
function setup() {
  const events = [];
  const props = vue.reactive({ items: [{ id: 10, name: "Ремень", active: true }, { id: 11, name: "Обложка Лондон", active: true }], productId: 1, disabled: false });
  const code = ts.transpileModule(script + "\n({ query, matches, opened, search, choose, keydown, outside, blur, root, open });", {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText;
  const app = vm.runInNewContext(code, {
    ...vue, onMounted: () => {}, onBeforeUnmount: () => {},
    defineProps: () => props, defineEmits: () => (...args) => events.push(args),
  });
  return { app, events, props };
}
const key = value => ({ key: value, preventDefault() {}, stopPropagation() {} });

test("search by partial name or ID and add using Enter", async () => {
  `Проверяем единое поле поиска и выбора:
  - найти товар по части названия без учёта регистра и по ID
  - добавить найденный товар клавишей Enter и очистить поле`;
  const { app, events } = setup();
  app.query.value = "ЛОНД";
  app.search();
  await vue.nextTick();
  assert.deepEqual(Array.from(app.matches.value, item => item.id), [11]);
  await app.keydown(key("Enter"));
  assert.deepEqual(events, [["select", 11]]);
  assert.equal(app.query.value, "");
  assert.equal(app.opened.value, false);
  app.query.value = "10";
  assert.deepEqual(Array.from(app.matches.value, item => item.id), [10]);
});

test("arrows choose options and Escape or outside focus closes list", async () => {
  `Проверяем управление списком:
  - выбрать второй товар стрелками и подтвердить Enter
  - закрыть список по Esc, клику и переходу фокуса вне поля`;
  const { app, events } = setup();
  app.open();
  await app.keydown(key("ArrowDown"));
  await app.keydown(key("Enter"));
  assert.deepEqual(events, [["select", 11]]);
  app.open();
  await app.keydown(key("Escape"));
  assert.equal(app.opened.value, false);
  app.open();
  app.root.value = { contains: node => node === "inside" };
  app.outside({ target: "inside" });
  assert.equal(app.opened.value, true);
  app.outside({ target: "outside" });
  assert.equal(app.opened.value, false);
  app.open();
  app.blur({ relatedTarget: "outside" });
  assert.equal(app.opened.value, false);
});

test("no selection for empty results or disabled picker", async () => {
  `Проверяем отсутствие ошибочного выбора:
  - не добавлять товар при пустой выдаче
  - не открывать список и не отправлять выбор при блокировке`;
  const { app, events, props } = setup();
  app.query.value = "нет такого товара";
  app.search();
  await app.keydown(key("Enter"));
  assert.deepEqual(events, []);
  props.disabled = true;
  await vue.nextTick();
  app.open();
  app.choose(props.items[0]);
  assert.equal(app.opened.value, false);
  assert.deepEqual(events, []);
});
