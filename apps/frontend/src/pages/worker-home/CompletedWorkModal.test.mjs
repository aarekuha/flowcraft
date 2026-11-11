import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';
import { ref, vModelText } from 'vue';

const script = fs.readFileSync(new URL('./CompletedWorkModal.vue', import.meta.url), 'utf8')
  .split('<script setup lang="ts">')[1].split('</script>')[0];
const source = ts.createSourceFile('report.ts', script, ts.ScriptTarget.Latest, true);
const saveFunction = source.statements.find(node =>
  ts.isFunctionDeclaration(node) && node.name?.text === 'savePiecework');

function form(value) {
  const calls = [];
  const state = {
    adminReport: ref({ user_id: 7, year: 2026, month: 11 }),
    savingPiecework: ref(false), savingBonus: ref(false), busy: ref(false),
    printing: ref(false), pieceworkInput: ref('123.45'), error: ref(''),
    generation: 1, report: ref(null),
    setMonthlyPiecework: async (...args) => {
      calls.push(args);
      return { payable_piecework_cents: args[3] };
    },
  };
  const listeners = {};
  const input = { value, addEventListener: (name, listener) => { listeners[name] = listener; } };
  vModelText.created(input, { modifiers: {} }, {
    props: { type: 'number', 'onUpdate:modelValue': value => { state.pieceworkInput.value = value; } },
  });
  listeners.input({ target: input });
  const code = ts.transpileModule(saveFunction.getText(source), {
    compilerOptions: { target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const save = vm.runInNewContext(code + '\nsavePiecework;', state);
  return { state, calls, save };
}

for (const [value, cents] of [['210.50', 21050], ['0', 0]]) {
  test(`saves numeric input ${value}`, async function testNumericPiecework() {
    `
    Проверяем сохранение из числового поля Vue:
    - передать введённую сумму через реальную директиву v-model
    - отправить сумму в копейках для выбранного сотрудника и месяца
    - обновить отчёт и снять блокировку сохранения
    `;
    const f = form(value);
    assert.equal(typeof f.state.pieceworkInput.value, 'number');
    await f.save();
    assert.deepEqual(f.calls, [[7, 2026, 11, cents]]);
    assert.equal(f.state.report.value.payable_piecework_cents, cents);
    assert.equal(f.state.savingPiecework.value, false);
  });
}

test('resets numeric input and rejects an empty amount', async function testResetAndEmpty() {
  `
  Проверяем сброс и пустую сумму:
  - отправить null при возврате к системному расчёту после числового ввода
  - не отправлять запрос сохранения для пустой суммы
  `;
  const reset = form('210');
  await reset.save(true);
  assert.deepEqual(reset.calls, [[7, 2026, 11, null]]);
  const empty = form('');
  await empty.save();
  assert.equal(empty.calls.length, 0);
  assert.ok(empty.state.error.value);
});
