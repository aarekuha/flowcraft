<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import {
  fetchPlanningSettings,
  updatePlanningSettings,
} from "@/shared/api/planning";

import {
  fetchCalendarStatus,
  refreshProductionCalendar,
  type CalendarStatus,
} from "@/shared/api/productionCalendar";

const showPersonalWorkReport = ref(true);
const calendarStatus = ref<CalendarStatus | null>(null);
const calendarLoading = ref(false);
const calendarUpdating = ref(false);
const calendarError = ref("");
const calendarMessage = ref("");
const calendarUpdateLabel = computed(() => {
  if (calendarUpdating.value) return "Загрузка календаря...";
  if (calendarLoading.value) return "Загрузка даты актуализации...";
  if (!calendarStatus.value) return "Загрузить календарь · дата актуализации неизвестна";
  if (calendarStatus.value.imported_at === null) {
    return "Загрузить календарь · данные не загружены";
  }
  const formatted = new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "short", timeStyle: "short", timeZone: "Europe/Moscow",
  }).format(calendarStatus.value.imported_at);
  return `Обновить календарь · актуализирован ${formatted} МСК`;
});

async function loadCalendarStatus() {
  calendarLoading.value = true;
  try {
    calendarStatus.value = await fetchCalendarStatus();
  } catch (loadError) {
    calendarError.value = getErrorMessage(loadError, "Не удалось загрузить дату актуализации.");
  } finally {
    calendarLoading.value = false;
  }
}

async function updateCalendar() {
  if (calendarUpdating.value) return;
  calendarUpdating.value = true;
  calendarError.value = "";
  calendarMessage.value = "";
  try {
    calendarStatus.value = await refreshProductionCalendar();
    calendarMessage.value = "Календарь успешно актуализирован.";
  } catch (updateError) {
    calendarError.value = getErrorMessage(updateError, "Не удалось обновить календарь.");
  } finally {
    calendarUpdating.value = false;
  }
}

const emit = defineEmits<{
  saved: [showPersonalWorkReport: boolean];
}>();

const baseRate = ref(350);
const displayOffsetDays = ref(2);
const preparationHours = ref(1);
const horizonMonths = ref<1 | 3 | 6 | 12>(3);
const baseline = ref("");
const loading = ref(true);
const saving = ref(false);
const error = ref("");

const signature = computed(() => JSON.stringify({
  showPersonalWorkReport: showPersonalWorkReport.value,
  baseRate: baseRate.value,
  displayOffsetDays: displayOffsetDays.value,
  preparationHours: preparationHours.value,
  horizonMonths: horizonMonths.value,
}));
const hasChanges = computed(
  () => !loading.value && signature.value !== baseline.value,
);
const formError = computed(() => {
  if (!Number.isFinite(baseRate.value) || baseRate.value < 0 || baseRate.value > 1000000) return "Базовая ставка должна быть от 0 до 1 000 000 рублей в час";
  if (!Number.isInteger(displayOffsetDays.value) || displayOffsetDays.value < 0) {
    return "Смещение должно быть целым неотрицательным числом дней.";
  }
  if (
    !Number.isFinite(preparationHours.value)
    || preparationHours.value < 0
    || !Number.isInteger(preparationHours.value * 3600)
  ) {
    return "Время подготовки должно быть неотрицательным и задаваться с точностью до секунды.";
  }
  return "";
});

onMounted(() => {
  void loadSettings();
  void loadCalendarStatus();
});

async function loadSettings() {
  loading.value = true;
  error.value = "";
  try {
    const settings = await fetchPlanningSettings();
    showPersonalWorkReport.value = settings.showPersonalWorkReport;
    baseRate.value = settings.baseRateCents / 100;
    displayOffsetDays.value = settings.displayOffsetDays;
    preparationHours.value = settings.preparationSeconds / 3600;
    horizonMonths.value = settings.horizonMonths;
    baseline.value = signature.value;
  } catch (loadError) {
    error.value = getErrorMessage(loadError, "Не удалось загрузить настройки.");
  } finally {
    loading.value = false;
  }
}

async function save() {
  if (!hasChanges.value || formError.value || saving.value) {
    return;
  }
  saving.value = true;
  error.value = "";
  try {
    const settings = await updatePlanningSettings({
      show_personal_work_report: showPersonalWorkReport.value,
      base_rate_cents: Math.round(baseRate.value * 100),
      display_offset_days: displayOffsetDays.value,
      preparation_seconds: Math.round(preparationHours.value * 3600),
      horizon_months: horizonMonths.value,
    });
    showPersonalWorkReport.value = settings.showPersonalWorkReport;
    baseRate.value = settings.baseRateCents / 100;
    displayOffsetDays.value = settings.displayOffsetDays;
    preparationHours.value = settings.preparationSeconds / 3600;
    horizonMonths.value = settings.horizonMonths;
    baseline.value = signature.value;
    emit("saved", showPersonalWorkReport.value);
  } catch (saveError) {
    error.value = getErrorMessage(saveError, "Не удалось сохранить настройки.");
  } finally {
    saving.value = false;
  }
}

function getErrorMessage(value: unknown, fallback: string): string {
  return value instanceof Error && value.message ? value.message : fallback;
}
</script>

<template>
  <div class="settings-layout">
    <section class="settings-card settings-main">
      <header class="settings-card__head"><h3>Расчёт и планирование</h3><p>Расценки операций и прогноз готовности заказов</p></header>
      <p v-if="error" class="settings-message settings-message--error" role="alert">{{ error }}</p>
      <p v-if="loading" class="settings-message">Загрузка настроек…</p>
      <div v-else class="settings-fields">
        <label><span>Базовая ставка, ₽/час</span><input v-model.number="baseRate" type="number" min="0" max="1000000" step="0.01"><small>Изменение ставки пересчитывает стоимость операций, включая расчёты прошлых месяцев.</small></label>
        <label><span>Горизонт расчёта</span><select v-model.number="horizonMonths"><option :value="1">1 месяц</option><option :value="3">3 месяца</option><option :value="6">6 месяцев</option><option :value="12">12 месяцев</option></select><small>Период прогнозирования загрузки.</small></label>
        <label><span>Смещение даты, дней</span><input v-model.number="displayOffsetDays" type="number" min="0" step="1"><small>Прибавляется только к отображаемой расчётной дате.</small></label>
        <label><span>Подготовка операции, часов</span><input v-model.number="preparationHours" type="number" min="0" step="0.25"><small>Начисляется один раз до начала операции.</small></label>
      </div>
      <section v-if="!loading" class="settings-interface">
        <h3>Личный кабинет</h3>
        <label class="settings-toggle"><input v-model="showPersonalWorkReport" type="checkbox"><span><strong>Мой расчёт за месяц</strong><small>Показывать сотрудникам ссылку на персональный расчёт.</small></span></label>
      </section>
      <p v-if="!loading && formError" class="settings-message settings-message--error">{{ formError }}</p>
      <footer class="settings-actions"><span v-if="hasChanges">Есть несохранённые изменения</span><button type="button" class="fc-button fc-button--primary" :disabled="!hasChanges || Boolean(formError) || saving" @click="save">{{ saving ? "Сохранение…" : "Сохранить изменения" }}</button></footer>
    </section>
    <div class="settings-side">
      <section class="settings-card">
        <header class="settings-card__head"><h3>Производственный календарь</h3><p>Праздники и нормы рабочего времени</p></header>
        <p class="settings-note">Россия · пятидневная 40-часовая неделя<br>Источник: calendar.kuzyak.in</p>
        <p v-if="calendarStatus?.years.length" class="settings-years">Сохранённые годы: {{ calendarStatus.years.join(", ") }}</p>
        <p class="settings-note">Загрузить текущий год и доступные последующие годы.</p>
        <button type="button" class="fc-button calendar-update" :disabled="calendarLoading || calendarUpdating" @click="updateCalendar">{{ calendarUpdateLabel }}</button>
        <p v-if="calendarError" class="settings-message settings-message--error" role="alert">{{ calendarError }}</p>
        <p v-if="calendarMessage" class="settings-message" role="status">{{ calendarMessage }}</p>
      </section>
      <slot />
    </div>
  </div>
</template>

<style scoped>
.settings-layout { display: grid; grid-template-columns: minmax(0, 1.35fr) minmax(320px, 1fr); gap: 20px; align-items: start; }
.settings-card { min-width: 0; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 18px; padding: 24px; }
.settings-card__head { margin-bottom: 24px; }
h3 { margin: 0; font-size: 1.05rem; font-weight: 700; }
.settings-card__head p, .settings-note { margin: 6px 0 0; color: var(--color-text-secondary); font-size: .875rem; line-height: 1.6; }
.settings-fields { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 24px 20px; }
.settings-fields label { display: flex; flex-direction: column; gap: 8px; font-size: .875rem; font-weight: 600; }
.settings-fields input, .settings-fields select { width: 100%; min-width: 0; min-height: 44px; padding: 10px 12px; border: 1px solid var(--color-border); border-radius: 10px; background: var(--color-surface); color: inherit; font: inherit; }
.settings-fields input:focus-visible, .settings-fields select:focus-visible, .settings-toggle input:focus-visible { outline: 2px solid var(--color-primary); outline-offset: 2px; }
small { display: block; color: var(--color-text-secondary); font-size: .8rem; font-weight: 400; line-height: 1.6; }
.settings-interface { margin-top: 28px; padding-top: 24px; border-top: 1px solid var(--color-border); }
.settings-toggle { display: flex; align-items: flex-start; gap: 12px; margin-top: 16px; cursor: pointer; }
.settings-toggle input { width: 18px; height: 18px; margin: 3px 0 0; flex-shrink: 0; accent-color: var(--color-primary); }
.settings-toggle strong { font-size: .875rem; font-weight: 600; }
.settings-toggle small { margin-top: 4px; }
.settings-actions { display: flex; flex-wrap: wrap; align-items: center; justify-content: flex-end; gap: 12px; margin-top: 28px; padding-top: 20px; border-top: 1px solid var(--color-border); }
.settings-actions span { flex: 1; color: var(--color-text-secondary); font-size: .8rem; }
.settings-side { display: grid; gap: 20px; min-width: 0; }
.settings-years { font-size: .875rem; margin: 16px 0; }
.calendar-update { margin-top: 18px; width: 100%; white-space: normal; }
.settings-message { padding: 12px; border-radius: 10px; background: var(--color-surface-soft); color: var(--color-text-secondary); font-size: .875rem; }
.settings-message--error { background: #fbeaea; color: #8e2f2f; }
@media (max-width: 1100px) { .settings-layout { grid-template-columns: minmax(0, 1fr); } }
@media (max-width: 600px) { .settings-card { padding: 18px; } .settings-fields { grid-template-columns: minmax(0, 1fr); gap: 20px; } .settings-actions { align-items: stretch; flex-direction: column; } }
</style>
