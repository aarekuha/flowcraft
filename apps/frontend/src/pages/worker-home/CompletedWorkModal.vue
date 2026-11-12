<script setup lang="ts">
import { ref, watch, computed, onUnmounted } from "vue";
import { vEscapeClose } from "./escapeClose";
import { downloadWorkReport, getWorkReport, money, setMonthlyBonusSelection, type WorkReport, getPersonalWorkReport, unlockPersonalWorkReport, type PersonalWorkReport, setMonthlyPiecework } from "@/shared/api/completedWork";

const props = defineProps<{ userId: number; personal?: boolean }>();
defineEmits<{ close: [] }>();
const today = new Date();
const year = ref(today.getFullYear());
const month = ref(today.getMonth() + 1);
const months = Array.from({ length: 12 }, (_, index) => new Date(2026, index, 1).toLocaleString("ru-RU", { month: "long" }));
const report = ref<WorkReport | PersonalWorkReport | null>(null);
const adminReport = computed(() => report.value && "bonuses" in report.value ? report.value as WorkReport : null);
const password = ref("");
const accessToken = ref("");
let accessTimeout: ReturnType<typeof setTimeout> | undefined;
function lockPersonalReport() {
  generation += 1;
  accessToken.value = "";
  password.value = "";
  report.value = null;
  busy.value = false;
}
async function unlock() {
  if (busy.value) return;
  const request = generation;
  busy.value = true;
  error.value = "";
  try {
    const access = await unlockPersonalWorkReport(password.value);
    if (request !== generation) return;
    accessToken.value = access.token;
    if (accessTimeout) clearTimeout(accessTimeout);
    accessTimeout = setTimeout(lockPersonalReport, Math.max(0, access.expires_at - Date.now()));
    await load();
  } catch (cause) {
    if (request === generation) error.value = cause instanceof Error ? cause.message : "Не удалось проверить пароль";
  } finally { password.value = ""; busy.value = false; }
}
onUnmounted(() => {
  if (accessTimeout) clearTimeout(accessTimeout);
  lockPersonalReport();
});
const busy = ref(false);
const printing = ref(false);
const savingBonus = ref(false);
const savingPiecework = ref(false);
const pieceworkInput = ref<string | number>("");
const savedPieceworkInput = computed(() => report.value
  ? (report.value.payable_piecework_cents / 100).toFixed(2) : "");
const pieceworkDirty = computed(() => pieceworkInput.value !== savedPieceworkInput.value);
watch(report, () => { pieceworkInput.value = savedPieceworkInput.value; });
async function savePiecework(reset = false) {
  const current = adminReport.value;
  if (!current || savingPiecework.value || savingBonus.value || busy.value || printing.value) return;
  const text = String(pieceworkInput.value).trim().replace(",", ".");
  const cents = Math.round(Number(text) * 100);
  if (!reset && (!/^\d+(?:\.\d{1,2})?$/.test(text) || !Number.isSafeInteger(cents))) {
    error.value = "Указать неотрицательную сумму с точностью до копеек.";
    return;
  }
  const request = generation;
  savingPiecework.value = true;
  error.value = "";
  try {
    const result = await setMonthlyPiecework(current.user_id, current.year, current.month, reset ? null : cents);
    if (request === generation) report.value = result;
  } catch (cause) {
    if (request === generation) error.value = cause instanceof Error ? cause.message : "Не удалось сохранить сделку";
  } finally { savingPiecework.value = false; }
}

const error = ref("");
let generation = 0;
async function load() {
  const request = ++generation;
  report.value = null;
  error.value = "";
  if (props.personal && !accessToken.value) { busy.value = false; return; }
  if (!Number.isInteger(year.value) || year.value < 2000 || year.value > 9998) { busy.value = false; return; }
  busy.value = true;
  try {
    const result = props.personal
      ? await getPersonalWorkReport(accessToken.value, year.value, month.value)
      : await getWorkReport(props.userId, year.value, month.value);
    if (request === generation) report.value = result;
  } catch (cause) {
    if (request === generation) {
      if (props.personal && cause instanceof Error && "status" in cause && cause.status === 403) {
        lockPersonalReport();
      }
      error.value = cause instanceof Error ? cause.message : "Не удалось загрузить расчёт";
    }
  }
  finally { if (request === generation) busy.value = false; }
}
async function changeBonus(bonusId: number, event: Event) {
  const checkbox = event.target as HTMLInputElement;
  const current = adminReport.value;
  if (props.personal || !current || savingBonus.value || savingPiecework.value || pieceworkDirty.value || busy.value || printing.value) return;
  const selected = checkbox.checked;
  checkbox.checked = current.bonuses.find((bonus) => bonus.id === bonusId)?.selected ?? true;
  const request = generation;
  savingBonus.value = true;
  error.value = "";
  try {
    const result = await setMonthlyBonusSelection(
      current.user_id, current.year, current.month, bonusId, selected,
    );
    if (request === generation) report.value = result;
  } catch (cause) {
    if (request === generation) {
      await load();
      error.value = cause instanceof Error ? cause.message : "Не удалось сохранить выбор премии";
    }
  } finally { savingBonus.value = false; }
}
async function print() {
  if (props.personal || !report.value || savingPiecework.value || pieceworkDirty.value) return;
  printing.value = true;
  error.value = "";
  try { await downloadWorkReport(props.userId, report.value.year, report.value.month); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "Не удалось скачать XLSX"; }
  finally { printing.value = false; }
}
function quantity(value: string) { return Number(value).toLocaleString("ru-RU", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
function day(value: number) { return new Date(value).toLocaleDateString("ru-RU", { timeZone: "Europe/Moscow" }); }
watch([year, month, () => props.userId], load, { immediate: true });
</script>

<template>
  <div class="work-overlay" @click.self="$emit('close')">
    <section v-escape-close="() => $emit('close')" class="work-dialog card-shell" role="dialog" aria-modal="true" aria-label="Расчёт выполненной работы" tabindex="-1">
      <header class="card-heading"><h2>Расчёт выполненной работы</h2><button type="button" @click="$emit('close')">Закрыть</button></header>
      <div class="card-scroll">
        <form v-if="personal && !accessToken" class="password-gate" @submit.prevent="unlock">
          <p>Для просмотра личного расчёта требуется пароль текущего пользователя.</p>
          <label>Пароль <input v-model="password" type="password" autocomplete="current-password" maxlength="255" required :disabled="busy" autofocus /></label>
          <button type="submit" :disabled="busy || !password">{{ busy ? 'Проверка…' : 'Открыть расчёт' }}</button>
        </form>
        <div v-else class="controls">
          <label>Месяц <select v-model="month" :disabled="printing || savingBonus || savingPiecework"><option v-for="(name, index) in months" :key="index" :value="index + 1">{{ name }}</option></select></label>
          <label>Год <input v-model.number="year" type="number" min="2000" max="9998" :disabled="printing || savingBonus || savingPiecework" /></label>
        </div>
        <p v-if="error" role="alert">{{ error }}</p><p v-if="busy">Расчёт…</p>
        <template v-if="report">
          <h3>{{ report.user_name }}</h3>
          <div class="summary"><span>Рабочих дней по графику: <b>{{ report.work_days }}</b></span><span>Часов по графику: <b>{{ report.work_hours }}</b></span><span>Больничных дней: <b>{{ report.sick_days }}</b></span><span>Дней отпуска: <b>{{ report.vacation_days }}</b></span><span>Дней прогулов: <b>{{ report.absence_days }}</b></span></div>
          <p v-if="report.items.some((item) => item.amount_cents === null)" role="alert">Расчёт неполный: отсутствуют расценки операций. Для полного расчёта требуется указать расценки.</p>
          <div class="table-scroll"><table>
          <thead><tr><th>Номер заказа</th><th>Дата сдачи</th><th>Изделие и версия</th><th>Операция</th><th>Количество изделий</th><th>Расценка, ₽</th><th>Начисление, ₽</th></tr></thead>
          <tbody><tr v-for="item in report.items" :key="`${item.order_id}-${item.operation_id}`"><td>{{ item.order_number }}</td><td>{{ day(item.completed_at) }}</td><td>{{ item.product_name }} · {{ item.product_version }}</td><td>{{ item.operation_name }}</td><td>{{ quantity(item.quantity) }}</td><td>{{ item.price_cents === null ? 'Не задана' : money(item.price_cents) }}</td><td>{{ money(item.amount_cents) }}</td></tr></tbody>
          <tfoot><tr><th colspan="4">Итого</th><th>{{ quantity(report.total_quantity) }}</th><td></td><th>{{ money(report.piecework_cents) }}</th></tr></tfoot>
          </table></div>
          <p v-if="!report.items.length">За выбранный месяц нет выполненных заказов с учтённым временем сотрудника.</p>
          <p class="hint">В итоговом количестве каждый заказ учтён один раз — по наибольшему количеству изделий среди операций сотрудника.</p>
          <template v-if="!personal && adminReport">
            <h3>Премии</h3>
            <p class="hint">В расчёт и XLSX входят только отмеченные премии. Выбор сохраняется для сотрудника за выбранный месяц.</p>
            <p v-if="savingBonus" role="status">Сохранение выбора премии…</p>
            <table class="bonuses">
              <thead><tr><th>Учитывать</th><th>Наименование</th><th>Сумма, ₽</th></tr></thead>
              <tbody>
                <tr v-for="bonus in adminReport.bonuses" :key="bonus.id" :class="{ 'bonus-excluded': !bonus.selected }">
                  <td><input type="checkbox" :checked="bonus.selected" :disabled="busy || printing || savingBonus || savingPiecework || pieceworkDirty" :aria-label="`Учитывать премию ${bonus.name}`" @change="changeBonus(bonus.id, $event)" /></td>
                  <td>{{ bonus.name }}</td><td>{{ money(bonus.amount_cents) }}</td>
                </tr>
              </tbody>
              <tfoot><tr><th colspan="2">Итого премий</th><th>{{ money(adminReport.bonuses_cents) }}</th></tr></tfoot>
            </table>
            <p v-if="!adminReport.bonuses.length">Премии не назначены.</p>
            <p>Системный расчёт сделки: <b>{{ money(report.piecework_cents) }} ₽</b></p>
            <form id="piecework-dialog-form" class="controls" @submit.prevent="savePiecework()">
              <label>Сделка к выплате, ₽
                <input v-model="pieceworkInput" type="number" min="0" step="0.01" required
                  :disabled="busy || printing || savingBonus || savingPiecework" />
              </label>
            </form>
            <p class="hint">{{ report.manual_piecework_cents === null ? 'Используется системный расчёт.' : 'Сохранена ручная сумма за выбранный месяц.' }}{{ pieceworkDirty ? ' Изменения суммы ещё не сохранены.' : '' }}</p>
            <p class="payout">Итого к выплате: <b>{{ money(adminReport.payout_cents) }} ₽</b></p>
          </template>
          <p v-if="personal">Сделка: <b>{{ money(report.payable_piecework_cents) }} ₽</b></p>
        </template>

      </div>

      <footer v-if="!personal || accessToken" class="controls card-actions">
        <template v-if="report && !personal && adminReport">
          <button type="submit" form="piecework-dialog-form" :disabled="busy || printing || savingBonus || savingPiecework || !pieceworkDirty">{{ savingPiecework ? 'Сохранение…' : 'Сохранить сделку' }}</button>
          <button type="button" :disabled="busy || printing || savingBonus || savingPiecework || report.manual_piecework_cents === null" @click="savePiecework(true)">Использовать системный расчёт</button>
          <button v-if="pieceworkDirty" type="button" :disabled="savingPiecework" @click="pieceworkInput = savedPieceworkInput">Отменить ввод</button>
        </template>
        <button :disabled="busy || printing || savingBonus || savingPiecework" @click="load">Пересчитать</button>
        <button v-if="!personal" :disabled="!report || printing || busy || savingBonus || savingPiecework || pieceworkDirty" @click="print">{{ printing ? 'Подготовка…' : 'Распечатать · XLSX' }}</button>
      </footer>
    </section>
  </div>
</template>

<style scoped>
.work-overlay { position: fixed; inset: 0; z-index: 120; background: #0f172a88; display: grid; place-items: center; padding: 20px; }
.work-dialog { background: white; color: #0f172a; padding: 24px; border-radius: 18px; width: min(1280px, 100%); max-height: 92vh; overflow: auto; box-sizing: border-box; }
header, .controls, .summary { display: flex; flex-wrap: wrap; align-items: center; gap: 16px; }
header { justify-content: space-between; }
.summary { padding: 16px; background: #f1f5f9; border-radius: 10px; }
input, select, button { padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 8px; font: inherit; }
input { width: 100px; } button { cursor: pointer; } button:disabled { opacity: .5; cursor: default; }
.card-actions { padding-top: 12px; }
.table-scroll { overflow-x: auto; margin-top: 20px; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 10px 8px; text-align: left; border-bottom: 1px solid #e2e8f0; }
tfoot { background: #eff6ff; } .bonuses { max-width: 650px; }
.bonuses input[type="checkbox"] { width: 18px; height: 18px; padding: 0; cursor: pointer; }
.bonus-excluded td:not(:first-child) { color: #64748b; }
.password-gate { display: grid; gap: 16px; max-width: 420px; }
.password-gate input { width: 100%; box-sizing: border-box; margin-top: 8px; }
.hint { color: #64748b; font-size: 13px; } .payout { font-size: 20px; }
[role="alert"] { color: #b91c1c; }
</style>
