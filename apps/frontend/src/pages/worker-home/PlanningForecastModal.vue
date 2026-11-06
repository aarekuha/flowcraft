<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import {
  fetchPlanningOrderForecastDetail,
  type PlanningOrderForecastDetail,
} from "@/shared/api/planning";
import {
  formatPlanningDate,
  formatPlanningDuration,
  getPlanningIssueLabel,
} from "@/shared/lib/productionPlanning";

const props = defineProps<{
  orderId: number;
}>();

const emit = defineEmits<{
  close: [];
}>();

const detail = ref<PlanningOrderForecastDetail | null>(null);
const loading = ref(true);
const error = ref("");

const operationNameById = computed(() => new Map(
  (detail.value?.operations ?? []).map((operation) => [
    operation.operationId,
    operation.operationName,
  ]),
));

onMounted(() => {
  void loadDetail();
});

async function loadDetail() {
  loading.value = true;
  error.value = "";
  try {
    detail.value = await fetchPlanningOrderForecastDetail(props.orderId);
  } catch (loadError) {
    error.value = getErrorMessage(
      loadError,
      "Не удалось загрузить расшифровку расчёта.",
    );
  } finally {
    loading.value = false;
  }
}

function getStageLabel(stageStart: number, stageEnd: number): string {
  return stageStart === stageEnd
    ? String(stageStart)
    : `${stageStart}–${stageEnd}`;
}

function getStatusLabel(status: string): string {
  const labels: Record<string, string> = {
    planned: "Запланирована",
    completed: "Выполнена по нормативу",
    unplanned: "Не запланирована",
    quality_control: "На ОТК",
  };
  return labels[status] ?? status;
}

function getStandardTimeSourceLabel(source: string): string {
  const labels: Record<string, string> = {
    manual: "ручной",
    statistical: "по статистике",
    missing: "не определён",
  };
  return labels[source] ?? source;
}

function close() {
  emit("close");
}

function getErrorMessage(value: unknown, fallback: string): string {
  return value instanceof Error && value.message ? value.message : fallback;
}
</script>

<template>
  <div class="forecast-backdrop" @click.self="close">
    <section
      class="forecast-modal"
      role="dialog"
      aria-modal="true"
      aria-labelledby="forecast-modal-title"
    >
      <header class="forecast-head">
        <div>
          <p>Планирование производства</p>
          <h2 id="forecast-modal-title">
            Расшифровка расчёта<span v-if="detail"> · {{ detail.orderNumber }}</span>
          </h2>
        </div>
        <button type="button" class="forecast-button" @click="close">
          Закрыть
        </button>
      </header>

      <p v-if="error" class="forecast-message forecast-message--error">
        {{ error }}
      </p>
      <p v-if="loading" class="forecast-message">Загрузка расчёта...</p>

      <template v-else-if="detail">
        <div class="forecast-summary">
          <article>
            <span>Изделие</span>
            <strong>{{ detail.productName }}</strong>
          </article>
          <article>
            <span>Плановая дата сдачи</span>
            <strong>{{ formatPlanningDate(detail.manualCompletionDate) }}</strong>
          </article>
          <article>
            <span>Ресурсное завершение</span>
            <strong>{{ formatPlanningDate(detail.resourceFinishDate) }}</strong>
          </article>
          <article>
            <span>Расчётная дата готовности</span>
            <strong>{{ formatPlanningDate(detail.calculatedFinishDate) }}</strong>
          </article>
        </div>

        <div v-if="detail.issueCodes.length > 0" class="forecast-issues">
          <strong>Причины отсутствия прогноза</strong>
          <ul>
            <li v-for="issueCode in detail.issueCodes" :key="issueCode">
              {{ getPlanningIssueLabel(issueCode) }}
            </li>
          </ul>
        </div>

        <section class="forecast-section">
          <h3>Операции</h3>
          <p v-if="detail.operations.length === 0" class="forecast-message">
            Производственные операции для этого заказа не планируются.
          </p>
          <div v-else class="forecast-table-wrap">
            <table class="forecast-table">
              <thead>
                <tr>
                  <th>Операция</th>
                  <th>Этап</th>
                  <th>Норматив</th>
                  <th>Факт</th>
                  <th>Остаток</th>
                  <th>Подготовка</th>
                  <th>Начало</th>
                  <th>Завершение</th>
                  <th>Статус</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="operation in detail.operations" :key="operation.operationId">
                  <td>
                    <strong>{{ operation.operationName }}</strong>
                    <small v-for="issueCode in operation.issueCodes" :key="issueCode">
                      {{ getPlanningIssueLabel(issueCode) }}
                    </small>
                  </td>
                  <td>{{ getStageLabel(operation.stageStart, operation.stageEnd) }}</td>
                  <td>
                    <span>{{ formatPlanningDuration(operation.workloadSeconds) }}</span>
                    <small v-if="operation.standardTimeSeconds !== null">
                      {{ formatPlanningDuration(operation.standardTimeSeconds) }} на изделие ·
                      {{ getStandardTimeSourceLabel(operation.standardTimeSource) }}
                    </small>
                    <small v-else>
                      {{ getStandardTimeSourceLabel(operation.standardTimeSource) }}
                    </small>
                  </td>
                  <td>{{ formatPlanningDuration(operation.actualSeconds) }}</td>
                  <td>{{ formatPlanningDuration(operation.remainingSeconds) }}</td>
                  <td>{{ formatPlanningDuration(operation.preparationSeconds) }}</td>
                  <td>{{ formatPlanningDate(operation.firstPlannedDate) }}</td>
                  <td>{{ formatPlanningDate(operation.lastPlannedDate) }}</td>
                  <td>{{ getStatusLabel(operation.status) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section v-if="detail.allocations.length > 0" class="forecast-section">
          <h3>Распределение по сотрудникам и дням</h3>
          <div class="forecast-table-wrap">
            <table class="forecast-table">
              <thead>
                <tr>
                  <th>Дата</th>
                  <th>Исполнитель</th>
                  <th>Операция</th>
                  <th>Работа</th>
                  <th>Подготовка</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="(allocation, index) in detail.allocations"
                  :key="`${allocation.workDate}-${allocation.userId}-${allocation.operationId}-${index}`"
                >
                  <td>{{ formatPlanningDate(allocation.workDate) }}</td>
                  <td>{{ allocation.userName }}</td>
                  <td>{{ operationNameById.get(allocation.operationId) ?? "—" }}</td>
                  <td>{{ formatPlanningDuration(allocation.workSeconds) }}</td>
                  <td>{{ formatPlanningDuration(allocation.preparationSeconds) }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>
    </section>
  </div>
</template>

<style scoped>
.forecast-backdrop {
  position: fixed;
  inset: 0;
  z-index: 138;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(23, 31, 42, 0.58);
}

.forecast-modal {
  width: min(1180px, 96vw);
  max-height: calc(100dvh - 40px);
  overflow: auto;
  padding: 24px;
  border-radius: 18px;
  background: #fff;
  box-shadow: 0 24px 70px rgba(15, 27, 39, 0.28);
  color: #1f2a33;
}

.forecast-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}

.forecast-head p,
.forecast-head h2,
.forecast-section h3 {
  margin: 0;
}

.forecast-head p,
.forecast-summary span,
.forecast-table small {
  color: #65727d;
}

.forecast-button {
  min-height: 44px;
  padding: 9px 15px;
  border: 1px solid #c7d1da;
  border-radius: 9px;
  background: #fff;
  color: inherit;
  font: inherit;
  cursor: pointer;
}

.forecast-message {
  margin: 20px 0 0;
  padding: 12px 14px;
  border-radius: 10px;
  background: #eef3f6;
}

.forecast-message--error {
  background: #fff0f0;
  color: #a12d2d;
}

.forecast-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-top: 20px;
}

.forecast-summary article {
  display: grid;
  gap: 6px;
  padding: 14px;
  border: 1px solid #dce4e9;
  border-radius: 12px;
  background: #f8fafb;
}

.forecast-issues {
  margin-top: 16px;
  padding: 14px 16px;
  border-radius: 12px;
  background: #fff7e7;
  color: #70511d;
}

.forecast-issues ul {
  margin: 8px 0 0;
  padding-left: 20px;
}

.forecast-section {
  display: grid;
  gap: 12px;
  margin-top: 24px;
}

.forecast-table-wrap {
  overflow: auto;
  border: 1px solid #dce4e9;
  border-radius: 12px;
}

.forecast-table {
  width: 100%;
  border-collapse: collapse;
  white-space: nowrap;
}

.forecast-table th,
.forecast-table td {
  padding: 11px 12px;
  border-bottom: 1px solid #e4eaee;
  text-align: left;
  vertical-align: top;
}

.forecast-table th {
  position: sticky;
  top: 0;
  background: #f2f6f8;
  z-index: 1;
}

.forecast-table td:first-child {
  white-space: normal;
  min-width: 180px;
}

.forecast-table small {
  display: block;
  margin-top: 4px;
}

@media (max-width: 760px) {
  .forecast-backdrop {
    align-items: start;
    padding: 12px;
  }

  .forecast-modal {
    width: calc(100vw - 24px);
    max-height: calc(100dvh - 24px);
    padding: 18px;
  }

  .forecast-head {
    align-items: stretch;
    flex-direction: column;
  }

  .forecast-summary {
    grid-template-columns: 1fr;
  }
}
</style>
