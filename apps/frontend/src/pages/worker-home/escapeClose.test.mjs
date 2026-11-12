import assert from 'node:assert/strict';
import fs from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';
import ts from 'typescript';

const source = fs.readFileSync(new URL('./escapeClose.ts', import.meta.url), 'utf8');
const compiled = ts.transpileModule(source, {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;

function setup() {
  const listeners = new Set();
  const window = {
    addEventListener: (_, callback) => listeners.add(callback),
    removeEventListener: (_, callback) => listeners.delete(callback),
    getComputedStyle: element => ({ zIndex: String(element.zIndex) }),
  };
  const context = { exports: {}, window, Node: { DOCUMENT_POSITION_FOLLOWING: 4 } };
  vm.runInNewContext(compiled, context);
  const directive = context.exports.vEscapeClose;
  const element = (order, zIndex = 0, parentElement = null) => ({
    order, zIndex, parentElement, isConnected: true,
    getClientRects: () => [1],
    compareDocumentPosition: other => order < other.order ? 4 : 2,
  });
  const key = (options = {}) => {
    const event = {
      key: 'Escape', defaultPrevented: false, repeat: false, isComposing: false,
      preventDefault() { this.defaultPrevented = true; },
      stopImmediatePropagation() { this.stopped = true; },
      ...options,
    };
    for (const callback of listeners) callback(event);
    return event;
  };
  return { directive, element, key, listeners };
}

test('Escape closes only the top dialog without requiring focus inside it', () => {
  `Проверяем закрытие верхней формы:
  - два окна имеют разные слои, фокус вне форм
  - Escape закрывает верхнее окно и не передаётся обработчику родителя
  - удержание клавиши не закрывает следующее окно`;
  const { directive, element, key, listeners } = setup();
  const lower = element(2), upper = element(1, 140);
  const closed = [];
  directive.mounted(lower, { value: () => closed.push('lower') });
  directive.mounted(upper, { value: () => { closed.push('upper'); directive.unmounted(upper); } });
  assert.equal(listeners.size, 1);
  const event = key();
  assert.deepEqual(closed, ['upper']);
  assert.equal(event.defaultPrevented, true);
  assert.equal(event.stopped, true);
  key({ repeat: true });
  assert.deepEqual(closed, ['upper']);
  key();
  assert.deepEqual(closed, ['upper', 'lower']);
  directive.unmounted(lower);
  assert.equal(listeners.size, 0);
});

test('Escape cancels confirmation while preserving the edited parent form', () => {
  `Проверяем сохранение несохранённых изменений:
  - закрытие родителя открывает подтверждение
  - повторный Escape отменяет только подтверждение
  - следующая попытка закрытия снова требует подтверждения`;
  const { directive, element, key } = setup();
  const parent = element(1, 130), confirmation = element(2, 0, parent);
  let confirmOpen = false;
  let requests = 0;
  directive.mounted(parent, { value: () => {
    requests++;
    confirmOpen = true;
    directive.mounted(confirmation, { value: () => {
      confirmOpen = false;
      directive.unmounted(confirmation);
    } });
  } });
  key();
  assert.equal(confirmOpen, true);
  key();
  assert.equal(confirmOpen, false);
  assert.equal(requests, 1);
  key();
  assert.equal(confirmOpen, true);
  assert.equal(requests, 2);
});

test('Hidden dialogs and other keys are ignored and callback updates take effect', () => {
  `Проверяем жизненный цикл обработчика:
  - скрытая форма не перехватывает клавишу, другие клавиши игнорируются
  - после обновления вызывается текущий обработчик
  - запрещённое закрытие верхней формы не закрывает родителя`;
  const { directive, element, key } = setup();
  const parent = element(1), child = element(2);
  let closed = 0;
  directive.mounted(parent, { value: () => closed++ });
  directive.mounted(child, { value: () => {} });
  key();
  assert.equal(closed, 0);
  child.getClientRects = () => [];
  key({ key: 'Enter' });
  assert.equal(closed, 0);
  directive.updated(parent, { value: () => { closed += 10; } });
  key();
  assert.equal(closed, 10);
});
