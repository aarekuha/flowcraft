import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import vm from "node:vm";
import ts from "typescript";

const text = fs.readFileSync(new URL("./WorkerHomePage.vue", import.meta.url), "utf8").split('<script setup lang="ts">')[1].split("</script>")[0];
const source = ts.createSourceFile("pricing.ts", text, ts.ScriptTarget.Latest, true);
const names = ["formatCoefficient", "calculatedOperationPrice", "serializeOperationCostUpdates"];
const functions = source.statements.filter(node => ts.isFunctionDeclaration(node) && names.includes(node.name?.text)).map(node => node.getText(source)).join("\n");
const script = ts.transpileModule(functions + "\n({ formatCoefficient, calculatedOperationPrice, serializeOperationCostUpdates });", { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText;
const app = vm.runInNewContext(script, { pricingBaseRateCents: { value: 35000 } });

test("coefficient keeps four decimals and price rounds up to kopecks", () => {
  `Проверяем отображение коэффициента и стоимости:
  - сохранить завершающие нули коэффициента
  - округлить расчётную цену вверх до копейки, без времени показать ноль`;
  assert.equal(app.formatCoefficient(12500), "1.2500");
  assert.equal(app.formatCoefficient(10000), "1.0000");
  assert.equal(app.calculatedOperationPrice({ coefficientUnits: 12500, statisticalTimeSeconds: 61 }), "7,42");
  assert.equal(app.calculatedOperationPrice({ coefficientUnits: 12500, statisticalTimeSeconds: null }), "0,00");
});

test("product updates send coefficient instead of manually entered price", () => {
  `Проверяем сохранение коэффициента:
  - отправить коэффициент и ручную норму времени
  - не отправлять рассчитанную цену как редактируемое поле`;
  const result = app.serializeOperationCostUpdates([{ id: 1, coefficientUnits: 12345, priceCents: 900, standardTimeSeconds: 30, children: [] }]);
  assert.equal(result[0].coefficient_units, 12345);
  assert.equal(result[0].standard_time_seconds, 30);
  assert.equal("price_cents" in result[0], false);
});

test("manual time immediately overrides statistics in displayed price", () => {
  `Проверяем стоимость при изменении ручной нормы:
  - использовать шесть минут вместо статистики и показать 35 рублей
  - после очистки нормы использовать статистику, при явном нуле показать ноль`;
  const row = { coefficientUnits: 10000, standardTimeSeconds: 360, statisticalTimeSeconds: 61 };
  assert.equal(app.calculatedOperationPrice(row), "35,00");
  row.standardTimeSeconds = null;
  assert.equal(app.calculatedOperationPrice(row), "5,94");
  row.standardTimeSeconds = 0;
  assert.equal(app.calculatedOperationPrice(row), "0,00");
});


test("coefficient input preserves sequential typing until blur", () => {
  `Проверяем последовательный ввод коэффициента:
  - набрать 1.01, 1.012 и 1.0123 без добавления нулей во время ввода
  - дополнить дробную часть нулями только после выхода из поля`;
  const inputFunctions = ["formatCoefficient", "updateOperationPrice", "handleOperationPriceInput", "getOperationCoefficientInput", "normalizeOperationCoefficientInput"];
  const inputScript = source.statements.filter(node => ts.isFunctionDeclaration(node) && inputFunctions.includes(node.name?.text)).map(node => node.getText(source)).join("\n");
  class Input { value = ""; }
  const tree = { value: [{ id: 1, coefficientUnits: 10000, children: [] }] };
  const api = vm.runInNewContext(ts.transpileModule(inputScript + "\n({ handleOperationPriceInput, getOperationCoefficientInput, normalizeOperationCoefficientInput });", { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, {
    HTMLInputElement: Input, isViewMode: { value: true }, canManagePlanningSettings: { value: true },
    operationCoefficientInputs: { value: {} }, operationTree: tree,
    flatOperationRows: { get value() { return tree.value; } },
  });
  const target = new Input();
  for (const value of ["1.01", "1.012", "1.0123"]) {
    target.value = value;
    api.handleOperationPriceInput(1, { target });
    assert.equal(api.getOperationCoefficientInput(tree.value[0]), value);
    assert.equal(target.value, value);
  }
  assert.equal(tree.value[0].coefficientUnits, 10123);
  target.value = "1,2";
  api.handleOperationPriceInput(1, { target });
  assert.equal(api.getOperationCoefficientInput(tree.value[0]), "1,2");
  api.normalizeOperationCoefficientInput(1, { target });
  assert.equal(target.value, "1.2000");
});
