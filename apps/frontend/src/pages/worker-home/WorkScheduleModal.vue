<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";

import {
  deleteWorkSchedule,
  fetchWorkSchedule,
  updateWorkSchedule,
  type WorkScheduleMonth,
  type WorkScheduleWorker,
} from "@/shared/api/planning";
import {
  getMonthDates,
  getScheduleSelection,
  isWeekendDate,
} from "@/shared/lib/workSchedule";

type SelectionAnchor = {
  userId: number;
  workDate: string;
  editExistingOnly: boolean;
  customHours: boolean;
};

type ScheduleEditor = {
  userId: number;
  userName: string;
  workDates: string[];
  mode: "create" | "edit";
  hours: number;
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
const sortedWorkers = computed(() => {
  const workers = [...(calendar.value?.workers ?? [])];
  return workers.sort((left, right) => {
    const result = left.userName.localeCompare(right.userName, "ru");
    return sortDirection.value === "asc" ? result : -result;
  });
});
const scheduleByWorker = computed(() => {
  const result = new Map<number, Map<string, number>>();
  for (const worker of calendar.value?.workers ?? []) {
    result.set(
      worker.userId,
      new Map(
        worker.days.map((day) => [day.workDate, day.availableSeconds]),
      ),
    );
  }
  return result;
});
const editorError = computed(() => {
  if (editor.value === null) {
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
  if (saving.value) {
    return;
  }
  const availableSeconds = getAvailableSeconds(worker.userId, workDate);
  const anchor = selectionAnchor.value;
  if (anchor === null || anchor.userId !== worker.userId) {
    selectionAnchor.value = {
      userId: worker.userId,
      workDate,
      editExistingOnly: availableSeconds !== null,
      customHours: event.shiftKey,
    };
    return;
  }

  const existingDates = new Set(worker.days.map((day) => day.workDate));
  const selectedDates = getScheduleSelection(
    anchor.workDate,
    workDate,
    existingDates,
    anchor.editExistingOnly,
  );
  selectionAnchor.value = null;
  if (selectedDates.length === 0) {
    return;
  }
  if (anchor.editExistingOnly || anchor.customHours || event.shiftKey) {
    editor.value = {
      userId: worker.userId,
      userName: worker.userName,
      workDates: selectedDates,
      mode: anchor.editExistingOnly ? "edit" : "create",
      hours: getCommonHours(worker, selectedDates) ?? 8,
    };
    return;
  }
  await saveDates(worker.userId, selectedDates, 8);
}

function getCommonHours(
  worker: WorkScheduleWorker,
  workDates: string[],
): number | null {
  const values = new Set(
    workDates.flatMap((workDate) => {
      const day = worker.days.find((item) => item.workDate === workDate);
      return day ? [day.availableSeconds / 3600] : [];
    }),
  );
  return values.size === 1 ? [...values][0] : null;
}

async function saveEditor() {
  if (editor.value === null || editorError.value || saving.value) {
    return;
  }
  await saveDates(
    editor.value.userId,
    editor.value.workDates,
    editor.value.hours,
  );
  if (!error.value) {
    editor.value = null;
  }
}

async function saveDates(userId: number, workDates: string[], hours: number) {
  saving.value = true;
  error.value = "";
  try {
    await updateWorkSchedule({
      user_id: userId,
      work_dates: workDates,
      available_seconds: Math.round(hours * 3600),
    });
    await loadCalendar();
  } catch (saveError) {
    error.value = getErrorMessage(saveError, "Не удалось сохранить рабочие дни.");
  } finally {
    saving.value = false;
  }
}

async function deleteEditorDates() {
  if (editor.value === null || editor.value.mode !== "edit" || saving.value) {
    return;
  }
  saving.value = true;
  error.value = "";
  try {
    await deleteWorkSchedule({
      user_id: editor.value.userId,
      work_dates: editor.value.workDates,
    });
    editor.value = null;
    await loadCalendar();
  } catch (deleteError) {
    error.value = getErrorMessage(deleteError, "Не удалось удалить рабочие дни.");
  } finally {
    saving.value = false;
  }
}

function getAvailableSeconds(userId: number, workDate: string): number | null {
  return scheduleByWorker.value.get(userId)?.get(workDate) ?? null;
}

function getHours(userId: number, workDate: string): string {
  const seconds = getAvailableSeconds(userId, workDate);
  return seconds === null ? "" : String(seconds / 3600);
}

function formatDateHeader(workDate: string): string {
  return `${workDate.slice(8, 10)}.${workDate.slice(5, 7)}`;
}

function isSelectedAnchor(userId: number, workDate: string): boolean {
  return selectionAnchor.value?.userId === userId
    && selectionAnchor.value.workDate === workDate;
}

function toggleSort() {
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
    <section class="schedule-modal" role="dialog" aria-modal="true">
      <header class="schedule-modal__head">
        <div>
          <p>Планирование производства</p>
          <h2>График работы сотрудников</h2>
        </div>
        <button type="button" class="schedule-button" @click="close">Закрыть</button>
      </header>

      <div class="schedule-toolbar">
        <label>
          <span>Месяц</span>
          <input v-model="month" type="month" />
        </label>
        <button type="button" class="schedule-button" @click="toggleSort">
          ФИО {{ sortDirection === "asc" ? "А–Я" : "Я–А" }}
        </button>
        <p>
          Выбрать начало и конец диапазона. Shift открывает ввод часов;
          обычный новый диапазон сохраняется по 8 часов.
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
                :class="{ 'schedule-table__weekend': isWeekendDate(workDate) }"
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
                  'schedule-table__weekend': isWeekendDate(workDate),
                  'schedule-table__working': getAvailableSeconds(worker.userId, workDate) !== null,
                  'schedule-table__selected': isSelectedAnchor(worker.userId, workDate),
                }"
              >
                <button
                  type="button"
                  :aria-label="`${worker.userName}, ${formatDateHeader(workDate)}`"
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

      <p v-if="selectionAnchor" class="schedule-selection-hint">
        Выбрано начало {{ formatDateHeader(selectionAnchor.workDate) }}.
        Выбрать окончание диапазона в строке того же сотрудника.
      </p>

      <div v-if="editor" class="schedule-editor-backdrop">
        <section class="schedule-editor" role="dialog" aria-modal="true">
          <h3>{{ editor.mode === "edit" ? "Изменить рабочие дни" : "Добавить рабочие дни" }}</h3>
          <p>
            {{ editor.userName }} · выбрано дней: {{ editor.workDates.length }}
          </p>
          <label>
            <span>Часов в каждый выбранный день</span>
            <input v-model.number="editor.hours" type="number" min="1" max="16" step="0.25" />
          </label>
          <p v-if="editorError" class="schedule-message schedule-message--error">
            {{ editorError }}
          </p>
          <div class="schedule-editor__actions">
            <button
              type="button"
              class="schedule-button schedule-button--primary"
              :disabled="Boolean(editorError) || saving"
              @click="saveEditor"
            >
              Сохранить
            </button>
            <button
              v-if="editor.mode === 'edit'"
              type="button"
              class="schedule-button schedule-button--danger"
              :disabled="saving"
              @click="deleteEditorDates"
            >
              Удалить выбранные дни
            </button>
            <button
              type="button"
              class="schedule-button"
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
.schedule-editor input {
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

.schedule-table .schedule-table__selected {
  outline: 3px solid #2f6ea3;
  outline-offset: -3px;
}

.schedule-table td button {
  width: 100%;
  height: 100%;
  border: 0;
  background: transparent;
  color: #1f2a33;
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
