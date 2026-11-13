<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import { vEscapeClose } from "./escapeClose";

import {
  deleteWorkSchedule,
  fetchWorkSchedule,
  updateWorkSchedule,
  type WorkScheduleMonth,
  type WorkScheduleWorker,
  type WorkScheduleDay,
  type WorkSchedulePeriodType,
} from "@/shared/api/planning";
import {
  getMonthDates,
  getScheduleSelection,
  getScheduleWorkerRange,
  isWeekendDate,
} from "@/shared/lib/workSchedule";

const props = defineProps<{ readonly?: boolean }>();

type SelectionAnchor = {
  userId: number;
  workDate: string;
  editExistingOnly: boolean;
  customHours: boolean;
};

type ScheduleSelection = {
  worker: WorkScheduleWorker;
  workDates: string[];
};

type ScheduleEditor = {
  selections: ScheduleSelection[];
  mode: "create" | "edit";
  hours: number;
  periodType: WorkSchedulePeriodType;
};

const periodLabels: Record<WorkSchedulePeriodType, string> = {
  work: "Работа",
  sick_leave: "Больничный",
  vacation: "Отпуск",
  absence: "Прогул",
};
const periodMarks: Record<WorkSchedulePeriodType, string> = {
  work: "",
  sick_leave: "Б",
  vacation: "О",
  absence: "П",
};

const emit = defineEmits<{
  close: [];
}>();

const month = ref(getCurrentMonth());
const calendar = ref<WorkScheduleMonth | null>(null);
const sortDirection = ref<"asc" | "desc">("asc");
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const selectionAnchor = ref<SelectionAnchor | null>(null);
const editor = ref<ScheduleEditor | null>(null);

const monthDates = computed(() =>
  getMonthDates(month.value, calendar.value?.daysInMonth ?? 0),
);
const productionDays = computed(() => new Map(
  (calendar.value?.productionCalendar?.days ?? []).map((day) => [day.calendar_date, day]),
));

function isCalendarDayOff(workDate: string): boolean {
  const day = productionDays.value.get(workDate);
  return day ? !day.is_working : isWeekendDate(workDate);
}

function calendarDayLabel(workDate: string): string {
  const day = productionDays.value.get(workDate);
  if (!day) return "Производственный календарь за этот год не загружен";
  if (day.is_shortened) return `Сокращённый рабочий день: ${day.name ?? ""}`;
  return day.name ?? (day.is_working ? "Рабочий день" : "Выходной день");
}

const sortedWorkers = computed(() => {
  const workers = [...(calendar.value?.workers ?? [])];
  return workers.sort((left, right) => {
    const result = left.userName.localeCompare(right.userName, "ru");
    return sortDirection.value === "asc" ? result : -result;
  });
});
const scheduleByWorker = computed(() => {
  const result = new Map<number, Map<string, WorkScheduleDay>>();
  for (const worker of calendar.value?.workers ?? []) {
    result.set(
      worker.userId,
      new Map(
        worker.days.map((day) => [day.workDate, day]),
      ),
    );
  }
  return result;
});
const editorError = computed(() => {
  if (editor.value === null || editor.value.periodType !== "work") {
    return "";
  }
  return Number.isFinite(editor.value.hours)
    && editor.value.hours >= 1
    && editor.value.hours <= 16
    && Number.isInteger(editor.value.hours * 3600)
    ? ""
    : "Количество часов должно быть от 1 до 16 с точностью до секунды.";
});

onMounted(() => {
  void loadCalendar();
});

watch(month, () => {
  selectionAnchor.value = null;
  editor.value = null;
  void loadCalendar();
});

async function loadCalendar() {
  loading.value = true;
  error.value = "";
  try {
    calendar.value = await fetchWorkSchedule(month.value);
  } catch (loadError) {
    error.value = getErrorMessage(loadError, "Не удалось загрузить график.");
  } finally {
    loading.value = false;
  }
}

async function selectDate(
  worker: WorkScheduleWorker,
  workDate: string,
  event: MouseEvent,
) {
  if (props.readonly || saving.value || loading.value) {
    return;
  }
  const availableSeconds = getAvailableSeconds(worker.userId, workDate);
  const anchor = selectionAnchor.value;
  if (anchor === null) {
    selectionAnchor.value = {
      userId: worker.userId,
      workDate,
      editExistingOnly: availableSeconds !== null,
      customHours: event.shiftKey,
    };
    return;
  }

  const selectedWorkers = getScheduleWorkerRange(
    sortedWorkers.value, anchor.userId, worker.userId,
  );
  const selections = selectedWorkers.map((selectedWorker) => ({
    worker: selectedWorker,
    workDates: getScheduleSelection(
      anchor.workDate,
      workDate,
      new Set(selectedWorker.days.map((day) => day.workDate)),
      anchor.editExistingOnly,
      anchor.customHours || event.shiftKey,
    ),
  })).filter((selection) => selection.workDates.length > 0);
  selectionAnchor.value = null;
  if (selections.length === 0) {
    return;
  }
  if (anchor.editExistingOnly || anchor.customHours || event.shiftKey || selectedWorkers.length > 1) {
    editor.value = {
      selections,
      mode: anchor.editExistingOnly ? "edit" : "create",
      hours: getCommonHours(selections) || 8,
      periodType: getCommonPeriodType(selections),
    };
    return;
  }
  await saveDates(selections, 8);
}

function getCommonPeriodType(selections: ScheduleSelection[]): WorkSchedulePeriodType {
  const values = new Set(selections.flatMap(({ worker, workDates }) =>
    workDates.map((workDate) =>
      worker.days.find((day) => day.workDate === workDate)?.periodType ?? "work",
    ),
  ));
  return values.size === 1 ? [...values][0] : "work";
}

function getCommonHours(selections: ScheduleSelection[]): number | null {
  const values = new Set(selections.flatMap(({ worker, workDates }) =>
    workDates.flatMap((workDate) => {
      const day = worker.days.find((item) => item.workDate === workDate);
      return day ? [day.availableSeconds / 3600] : [];
    }),
  ));
  return values.size === 1 ? [...values][0] : null;
}

async function saveEditor() {
  if (props.readonly) return;
  if (editor.value === null || editorError.value || saving.value) {
    return;
  }
  await saveDates(
    editor.value.selections,
    editor.value.hours,
    editor.value.periodType,
  );
  if (!error.value) {
    editor.value = null;
  }
}

async function saveDates(
  selections: ScheduleSelection[],
  hours: number,
  periodType: WorkSchedulePeriodType = "work",
) {
  if (props.readonly) return;
  saving.value = true;
  error.value = "";
  try {
    await updateWorkSchedule(selections.map(({ worker, workDates }) => ({
      user_id: worker.userId,
      work_dates: workDates,
      available_seconds: periodType === "work" ? Math.round(hours * 3600) : 0,
      period_type: periodType,
    })));
    await loadCalendar();
  } catch (saveError) {
    error.value = getErrorMessage(saveError, "Не удалось сохранить период.");
  } finally {
    saving.value = false;
  }
}

async function deleteEditorDates() {
  if (props.readonly) return;
  if (editor.value === null || editor.value.mode !== "edit" || saving.value) {
    return;
  }
  saving.value = true;
  error.value = "";
  try {
    await deleteWorkSchedule(editor.value.selections.map(({ worker, workDates }) => ({
      user_id: worker.userId,
      work_dates: workDates,
    })));
    editor.value = null;
    await loadCalendar();
  } catch (deleteError) {
    error.value = getErrorMessage(deleteError, "Не удалось удалить период.");
  } finally {
    saving.value = false;
  }
}

function getAvailableSeconds(userId: number, workDate: string): number | null {
  return getDay(userId, workDate)?.availableSeconds ?? null;
}

function getDay(userId: number, workDate: string): WorkScheduleDay | undefined {
  return scheduleByWorker.value.get(userId)?.get(workDate);
}

function getDayLabel(userId: number, workDate: string): string {
  const day = getDay(userId, workDate);
  if (!day) return "Нет записи";
  return day.periodType === "work"
    ? `Работа: ${day.availableSeconds / 3600} ч`
    : periodLabels[day.periodType];
}

function getHours(userId: number, workDate: string): string {
  const day = getDay(userId, workDate);
  if (!day) return "";
  return day.periodType === "work"
    ? String(day.availableSeconds / 3600)
    : periodMarks[day.periodType];
}

function formatDateHeader(workDate: string): string {
  return `${workDate.slice(8, 10)}.${workDate.slice(5, 7)}`;
}

function isSelectedAnchor(userId: number, workDate: string): boolean {
  return selectionAnchor.value?.userId === userId
    && selectionAnchor.value.workDate === workDate;
}

function toggleSort() {
  selectionAnchor.value = null;
  sortDirection.value = sortDirection.value === "asc" ? "desc" : "asc";
}

function close() {
  if (!saving.value) {
    emit("close");
  }
}

function getCurrentMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}`;
}

function getErrorMessage(value: unknown, fallback: string): string {
  return value instanceof Error && value.message ? value.message : fallback;
}
</script>

<template>
  <div class="schedule-backdrop" @click.self="close">
    <section v-escape-close="close" class="schedule-modal card-shell" role="dialog" aria-modal="true">
      <header class="schedule-modal__head card-heading">
        <div>
          <p>Планирование производства</p>
          <h2>График работы сотрудников</h2>
        </div>
        <button type="button" class="schedule-button fc-button" @click="close">Закрыть</button>
      </header>
      <div class="card-scroll">

        <div class="schedule-toolbar">
          <label>
            <span>Месяц</span>
            <input v-model="month" type="month" />
          </label>
          <button type="button" class="schedule-button fc-button" @click="toggleSort">
          ФИО {{ sortDirection === "asc" ? "А–Я" : "Я–А" }}
          </button>
          <p v-if="!props.readonly">
          Выбрать начало и конец диапазона. Shift открывает выбор типа периода и часов для всего диапазона;
          новый диапазон в одной строке без Shift сохраняется по 8 часов.
          Выбор границ на разных строках открывает редактирование для всех сотрудников между ними.
          </p>
        </div>

        <p v-if="error" class="schedule-message schedule-message--error">{{ error }}</p>
        <p v-if="loading" class="schedule-message">Загрузка графика...</p>

        <div v-else class="schedule-table-wrap">
          <table class="schedule-table">
            <thead>
              <tr>
                <th class="schedule-table__name">ФИО</th>
                <th
                  v-for="workDate in monthDates"
                  :key="workDate"
                  :title="calendarDayLabel(workDate)"
                  :class="{
                    'schedule-table__weekend': isCalendarDayOff(workDate),
                    'schedule-table__holiday': productionDays.get(workDate)?.is_holiday,
                  }"
                >
                {{ formatDateHeader(workDate) }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="worker in sortedWorkers" :key="worker.userId">
                <th class="schedule-table__name">{{ worker.userName }}</th>
                <td
                  v-for="workDate in monthDates"
                  :key="workDate"
                  :class="{
                    'schedule-table__weekend': isCalendarDayOff(workDate),
                    'schedule-table__holiday': productionDays.get(workDate)?.is_holiday,
                    'schedule-table__working': getDay(worker.userId, workDate)?.periodType === 'work',
                    'schedule-table__sick': getDay(worker.userId, workDate)?.periodType === 'sick_leave',
                    'schedule-table__vacation': getDay(worker.userId, workDate)?.periodType === 'vacation',
                    'schedule-table__absence': getDay(worker.userId, workDate)?.periodType === 'absence',
                    'schedule-table__selected': isSelectedAnchor(worker.userId, workDate),
                  }"
                >
                  <button
                    type="button"
                    :aria-label="`${worker.userName}, ${formatDateHeader(workDate)}, ${getDayLabel(worker.userId, workDate)}`"
                    :title="`${getDayLabel(worker.userId, workDate)} · ${calendarDayLabel(workDate)}`"
                    :disabled="saving"
                    @click="selectDate(worker, workDate, $event)"
                  >
                  {{ getHours(worker.userId, workDate) }}
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-if="sortedWorkers.length === 0" class="schedule-message">
          Активные исполнители не найдены.
          </p>
        </div>

        <p v-if="calendar && !calendar.productionCalendar" class="schedule-message">
        Производственный календарь за {{ month.slice(0, 4) }} год не загружен.
        Отображаются обычные субботы и воскресенья.
        </p>
        <p v-else-if="calendar?.productionCalendar" class="schedule-calendar-summary">
        По производственному календарю: рабочих дней — {{ calendar.productionCalendar.summary.working_days }},
        нерабочих — {{ calendar.productionCalendar.summary.non_working_days }},
        сокращённых — {{ calendar.productionCalendar.summary.shortened_days }}.
        Норма при 40-часовой неделе — {{ calendar.productionCalendar.summary.working_hours }} ч.
        </p>
        <div class="schedule-legend" aria-label="Обозначения графика">
          <span class="schedule-legend__holiday">Праздничный день</span>
          <span class="schedule-legend__sick">Б — больничный</span>
          <span class="schedule-legend__vacation">О — отпуск</span>
          <span class="schedule-legend__absence">П — прогул</span>
        </div>

        <p v-if="selectionAnchor" class="schedule-selection-hint">
        Выбрано начало {{ formatDateHeader(selectionAnchor.workDate) }}.
        Выбрать окончание диапазона. При выборе другой строки включить всех сотрудников между строками.
        </p>

      </div>

      <div v-if="editor" class="schedule-editor-backdrop">
        <section v-escape-close="() => { if (!saving) editor = null }" class="schedule-editor card-shell" role="dialog" aria-modal="true">
          <h3 class="card-heading">{{ editor.mode === "edit" ? "Изменить период" : "Добавить период" }}</h3>
          <div class="card-scroll">
            <p>Выбрано сотрудников: {{ editor.selections.length }}</p>
            <p v-for="selection in editor.selections" :key="selection.worker.userId">
              {{ selection.worker.userName }} ·
              {{ formatDateHeader(selection.workDates[0]) }}–{{ formatDateHeader(selection.workDates[selection.workDates.length - 1]) }} ·
              дней: {{ selection.workDates.length }}
            </p>
            <label>
              <span>Тип периода</span>
              <select v-model="editor.periodType">
                <option v-for="(label, value) in periodLabels" :key="value" :value="value">
                {{ label }}
                </option>
              </select>
            </label>
            <label>
              <span>Часов в каждый выбранный день</span>
              <input
                v-if="editor.periodType === 'work'"
                v-model.number="editor.hours"
                type="number"
                min="1"
                max="16"
                step="0.25"
              />
              <input v-else type="number" :value="0" disabled />
            </label>
            <p v-if="editor.periodType !== 'work'">
            Отсутствие на полный день. Доступность для планирования — 0 часов.
            </p>
            <p>Сохранение заменит записи выбранных дней.</p>
            <p v-if="editorError" class="schedule-message schedule-message--error">
            {{ editorError }}
            </p>

          </div>

          <div class="schedule-editor__actions card-actions">
            <button
              type="button"
              class="schedule-button schedule-button--primary fc-button fc-button--primary"
              :disabled="Boolean(editorError) || saving"
              @click="saveEditor"
            >
              Сохранить
            </button>
            <button
              v-if="editor.mode === 'edit'"
              type="button"
              class="schedule-button schedule-button--danger fc-button fc-button--danger"
              :disabled="saving"
              @click="deleteEditorDates"
            >
              Удалить выбранные дни
            </button>
            <button
              type="button"
              class="schedule-button fc-button"
              :disabled="saving"
              @click="editor = null"
            >
              Отменить
            </button>
          </div>
        </section>
      </div>
    </section>
  </div>
</template>

<style scoped>
.schedule-backdrop,
.schedule-editor-backdrop {
  position: fixed;
  inset: 0;
  z-index: 135;
  display: grid;
  place-items: center;
  padding: 18px;
  background: rgba(23, 31, 42, 0.58);
}

.schedule-modal {
  position: relative;
  display: flex;
  flex-direction: column;
  width: min(1540px, 97vw);
  max-height: 95vh;
  padding: 22px;
  overflow: hidden;
  border-radius: 18px;
  background: #fff;
  color: #1f2a33;
  box-shadow: 0 24px 70px rgba(15, 27, 39, 0.28);
}

.schedule-modal__head,
.schedule-toolbar,
.schedule-editor__actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.schedule-modal__head p,
.schedule-modal__head h2,
.schedule-toolbar p,
.schedule-editor h3,
.schedule-editor p {
  margin: 0;
}

.schedule-modal__head p,
.schedule-toolbar p,
.schedule-selection-hint,
.schedule-editor p {
  color: #65727d;
}

.schedule-toolbar {
  margin: 16px 0 12px;
}

.schedule-toolbar label,
.schedule-editor label {
  display: grid;
  gap: 5px;
  font-weight: 650;
}

.schedule-toolbar input,
.schedule-editor input,
.schedule-editor select {
  min-height: 44px;
  padding: 8px 10px;
  border: 1px solid #c7d1da;
  border-radius: 9px;
  font: inherit;
}

.schedule-button {
  min-height: 44px;
  padding: 9px 15px;
  border: 1px solid #c7d1da;
  border-radius: 9px;
  background: #fff;
  color: #263746;
  cursor: pointer;
}

.schedule-button--primary {
  border-color: #2f6ea3;
  background: #2f6ea3;
  color: #fff;
}

.schedule-button--danger {
  border-color: #a94444;
  color: #8e2f2f;
}

.schedule-button:disabled,
.schedule-table button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.schedule-message {
  margin: 10px 0;
  padding: 12px;
  border-radius: 9px;
  background: #eef3f7;
  color: #5f6b76;
}

.schedule-message--error {
  background: #fbeaea;
  color: #8e2f2f;
}

.schedule-table-wrap {
  flex: 1;
  overflow: auto;
  border: 1px solid #d6dee6;
  border-radius: 11px;
}

.schedule-table {
  width: max-content;
  min-width: 100%;
  border-collapse: separate;
  border-spacing: 0;
}

.schedule-table th,
.schedule-table td {
  min-width: 48px;
  height: 48px;
  padding: 0;
  border-right: 1px solid #d6dee6;
  border-bottom: 1px solid #d6dee6;
  background: #f7f9fb;
  text-align: center;
}

.schedule-table thead th {
  position: sticky;
  top: 0;
  z-index: 3;
  background: #e9eef3;
  font-size: 12px;
}

.schedule-table .schedule-table__name {
  position: sticky;
  left: 0;
  z-index: 2;
  min-width: 220px;
  padding: 0 12px;
  background: #fff;
  text-align: left;
}

.schedule-table thead .schedule-table__name {
  z-index: 5;
  background: #e9eef3;
}

.schedule-table .schedule-table__weekend {
  background: #e1e5e9;
}

.schedule-table .schedule-table__working {
  background: #fff;
}

.schedule-table .schedule-table__sick,
.schedule-legend__sick {
  background: #fee2e2;
  color: #991b1b;
}

.schedule-table .schedule-table__vacation,
.schedule-legend__vacation {
  background: #dbeafe;
  color: #1e40af;
}

.schedule-table .schedule-table__absence,
.schedule-legend__absence {
  background: #ffedd5;
  color: #9a3412;
}

.schedule-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.schedule-legend span {
  padding: 4px 8px;
  border-radius: 4px;
}

.schedule-table .schedule-table__holiday,
.schedule-legend__holiday {
  box-shadow: inset 0 0 0 2px #dbeafe;
}

.schedule-calendar-summary {
  color: #65727d;
  font-size: 14px;
}

.schedule-table .schedule-table__selected {
  outline: 3px solid #2f6ea3;
  outline-offset: -3px;
}

.schedule-table td button {
  width: 100%;
  height: 100%;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.schedule-selection-hint {
  margin: 12px 0 0;
}

.schedule-editor-backdrop {
  z-index: 145;
  border-radius: 18px;
}

.schedule-editor {
  width: min(560px, 92vw);
  padding: 22px;
  border-radius: 14px;
  background: #fff;
}

.schedule-editor label {
  margin: 18px 0;
}

@media (max-width: 760px) {
  .schedule-backdrop {
    padding: 6px;
  }

  .schedule-modal {
    width: 100%;
    max-height: 98vh;
    padding: 12px;
  }

  .schedule-modal__head,
  .schedule-toolbar,
  .schedule-editor__actions {
    align-items: stretch;
    flex-direction: column;
  }
}
</style>
