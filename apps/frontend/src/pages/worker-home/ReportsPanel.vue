<script setup lang="ts">
import { computed, onMounted, ref } from "vue";

import type { ProductSummary } from "@/shared/api/products";
import {
  downloadProductQuantityReport,
  downloadProductTimeReport,
  downloadOrderBatchReport,
  fetchProductQuantityReport,
  fetchProductTimeReport,
  fetchOrderBatchReport,
  fetchReportFilterOptions,
  type ProductQuantityReport,
  type ProductTimeReport,
  type ReportFilters,
  type ReportFilterOptions,
  type OrderBatchReport,
} from "@/shared/api/reports";

type ReportTab = "products" | "product-time" | "order-batches";

const props = defineProps<{
  products: ProductSummary[];
}>();

const activeReport = ref<ReportTab>("products");
const dateTo = ref(toDateInput(new Date()));
const dateFrom = ref(toDateInput(addDays(new Date(), -29)));
const productId = ref("");
const workerUserId = ref("");
const operationCatalogEntryId = ref("");
const orderNumber = ref("");
const productQuantityReport = ref<ProductQuantityReport | null>(null);
const productTimeReport = ref<ProductTimeReport | null>(null);
const orderBatchReport = ref<OrderBatchReport | null>(null);
const orderBatchPage = ref(1);
const loading = ref(false);
const exportLoading = ref(false);
const error = ref("");
const filterOptionsError = ref("");
const filterOptions = ref<ReportFilterOptions>({ workers: [], operations: [] });

const sortedProducts = computed(() =>
  [...props.products].sort((left, right) => left.name.localeCompare(right.name, "ru")),
);
const workers = computed(() =>
  [...filterOptions.value.workers]
    .sort((left, right) => left.name.localeCompare(right.name, "ru")),
);
const sortedOperations = computed(() =>
  [...filterOptions.value.operations].sort((left, right) => left.name.localeCompare(right.name, "ru")),
);
const periodError = computed(() => {
  if (!dateFrom.value || !dateTo.value) {
    return "Укажите начало и окончание периода.";
  }
  if (dateFrom.value > dateTo.value) {
    return "Дата начала периода не должна быть позже даты окончания.";
  }
  const durationDays = Math.floor(
    (new Date(`${dateTo.value}T00:00:00Z`).getTime() -
      new Date(`${dateFrom.value}T00:00:00Z`).getTime()) /
      86_400_000,
  ) + 1;
  return durationDays > 366 ? "Период отчета не должен превышать 366 дней." : "";
});

onMounted(() => {
  void loadFilterOptions();
  void loadReport();
});

async function loadFilterOptions() {
  filterOptionsError.value = "";
  try {
    filterOptions.value = await fetchReportFilterOptions();
  } catch (reportError) {
    filterOptionsError.value = getErrorMessage(
      reportError,
      "Не удалось загрузить варианты фильтров.",
    );
  }
}

async function selectReport(report: ReportTab) {
  if (activeReport.value === report) {
    return;
  }
  activeReport.value = report;
  orderBatchPage.value = 1;
  error.value = "";
  await loadReport();
}

async function loadReport() {
  if (periodError.value) {
    error.value = periodError.value;
    return;
  }
  loading.value = true;
  error.value = "";
  try {
    if (activeReport.value === "products") {
      productQuantityReport.value = await fetchProductQuantityReport(getFilters());
    } else if (activeReport.value === "product-time") {
      productTimeReport.value = await fetchProductTimeReport(getFilters());
    } else {
      orderBatchReport.value = await fetchOrderBatchReport(getFilters());
    }
  } catch (reportError) {
    error.value = getErrorMessage(reportError, "Не удалось загрузить отчет.");
  } finally {
    loading.value = false;
  }
}

async function showReport() {
  if (activeReport.value === "order-batches") {
    orderBatchPage.value = 1;
  }
  await loadReport();
}

async function exportReport() {
  if (periodError.value) {
    error.value = periodError.value;
    return;
  }
  exportLoading.value = true;
  error.value = "";
  try {
    let result: { blob: Blob; filename: string };
    if (activeReport.value === "products") {
      result = await downloadProductQuantityReport(getFilters());
    } else if (activeReport.value === "product-time") {
      result = await downloadProductTimeReport(getFilters());
    } else {
      result = await downloadOrderBatchReport(getFilters());
    }
    const url = URL.createObjectURL(result.blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = result.filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  } catch (reportError) {
    error.value = getErrorMessage(reportError, "Не удалось выгрузить отчет.");
  } finally {
    exportLoading.value = false;
  }
}

function getFilters(): ReportFilters {
  const filters: ReportFilters = {
    dateFrom: dateFrom.value,
    dateTo: dateTo.value,
  };
  const selectedProductId = Number.parseInt(productId.value, 10);
  const selectedWorkerId = Number.parseInt(workerUserId.value, 10);
  const selectedOperationId = Number.parseInt(operationCatalogEntryId.value, 10);
  if (Number.isInteger(selectedProductId)) {
    filters.productId = selectedProductId;
  }
  if (activeReport.value !== "products" && Number.isInteger(selectedWorkerId)) {
    filters.workerUserId = selectedWorkerId;
  }
  if (activeReport.value === "order-batches" && Number.isInteger(selectedOperationId)) {
    filters.operationCatalogEntryId = selectedOperationId;
  }
  if (activeReport.value !== "products" && orderNumber.value.trim()) {
    filters.orderNumber = orderNumber.value.trim();
  }
  if (activeReport.value === "order-batches") {
    filters.page = orderBatchPage.value;
    filters.pageSize = 20;
  }
  return filters;
}

async function selectOrderBatchPage(page: number) {
  if (page < 1 || page === orderBatchPage.value || page > (orderBatchReport.value?.pages ?? 1)) {
    return;
  }
  orderBatchPage.value = page;
  await loadReport();
}

function formatMonth(value: string): string {
  const [year, month] = value.split("-");
  return `${month}.${year}`;
}

function formatDay(value: string): string {
  const [year, month, day] = value.split("-");
  return `${day}.${month}.${year}`;
}

function formatDuration(totalMs: number): string {
  const totalSeconds = Math.max(0, Math.floor(totalMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return [hours, minutes, seconds]
    .map((value) => String(value).padStart(2, "0"))
    .join(":");
}

function formatPercentage(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatCompletionDate(value: number): string {
  return new Intl.DateTimeFormat("ru-RU", { dateStyle: "short" }).format(new Date(value));
}

function toDateInput(value: Date): string {
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function addDays(value: Date, days: number): Date {
  const result = new Date(value);
  result.setDate(result.getDate() + days);
  return result;
}

function getErrorMessage(value: unknown, fallback: string): string {
  return value instanceof Error ? value.message : fallback;
}
</script>

<template>
  <article class="reports-panel">
    <div class="reports-panel__head">
      <div>
        <span class="reports-panel__eyebrow">Производственные данные</span>
        <h2>Отчеты</h2>
      </div>
      <div class="reports-tabs" role="tablist" aria-label="Виды отчетов">
        <button
          type="button"
          class="reports-tab"
          :class="{ 'reports-tab--active': activeReport === 'products' }"
          @click="void selectReport('products')"
        >
          По изделиям
        </button>
        <button
          type="button"
          class="reports-tab"
          :class="{ 'reports-tab--active': activeReport === 'product-time' }"
          @click="void selectReport('product-time')"
        >
          Время по изделиям и операциям
        </button>
        <button
          type="button"
          class="reports-tab"
          :class="{ 'reports-tab--active': activeReport === 'order-batches' }"
          @click="void selectReport('order-batches')"
        >
          По партиям
        </button>
      </div>
    </div>

    <div class="reports-filters">
      <label class="reports-field">
        <span>С</span>
        <input v-model="dateFrom" type="date" />
      </label>
      <label class="reports-field">
        <span>По</span>
        <input v-model="dateTo" type="date" />
      </label>
      <label class="reports-field">
        <span>Изделие</span>
        <select v-model="productId">
          <option value="">Все изделия</option>
          <option v-for="product in sortedProducts" :key="product.id" :value="String(product.id)">
            {{ product.name }}
          </option>
        </select>
      </label>
      <label v-if="activeReport !== 'products'" class="reports-field">
        <span>Исполнитель</span>
        <select v-model="workerUserId">
          <option value="">Все исполнители</option>
          <option v-for="worker in workers" :key="worker.id" :value="String(worker.id)">
            {{ worker.name }}{{ worker.isDeleted ? " (удалён)" : !worker.isActive ? " (неактивен)" : "" }}
          </option>
        </select>
      </label>
      <label v-if="activeReport === 'order-batches'" class="reports-field">
        <span>Операция</span>
        <select v-model="operationCatalogEntryId">
          <option value="">Все операции</option>
          <option
            v-for="operation in sortedOperations"
            :key="operation.id"
            :value="String(operation.id)"
          >
            {{ operation.name }}{{ operation.isActive ? "" : " (неактивна)" }}
          </option>
        </select>
      </label>
      <label v-if="activeReport !== 'products'" class="reports-field">
        <span>Номер заказа</span>
        <input v-model="orderNumber" type="text" placeholder="Например, FC-0101" />
      </label>
      <div class="reports-actions">
        <button type="button" class="reports-button" :disabled="loading" @click="void showReport()">
          {{ loading ? "Загрузка..." : "Показать" }}
        </button>
        <button
          type="button"
          class="reports-button reports-button--secondary"
          :disabled="loading || exportLoading"
          @click="void exportReport()"
        >
          {{ exportLoading ? "Выгрузка..." : "XLSX" }}
        </button>
      </div>
    </div>

    <div v-if="error || filterOptionsError" class="reports-message reports-message--error">
      {{ error || filterOptionsError }}
    </div>
    <div v-else-if="loading" class="reports-message">Загрузка отчета...</div>

    <template v-else-if="activeReport === 'products' && productQuantityReport">
      <div v-if="productQuantityReport.items.length === 0" class="reports-message">
        За выбранный период завершенных заказов нет.
      </div>
      <template v-else>
        <section class="report-section">
          <h3>Количество изделий по месяцам</h3>
          <div class="report-table-wrap">
            <table class="report-table">
              <thead><tr><th>Изделие</th><th v-for="month in productQuantityReport.months" :key="month">{{ formatMonth(month) }}</th><th>Итого</th></tr></thead>
              <tbody><tr v-for="item in productQuantityReport.items" :key="item.productId"><td>{{ item.productName }}</td><td v-for="(value, index) in item.monthQuantities" :key="productQuantityReport.months[index]">{{ value }}</td><td>{{ item.totalQuantity }}</td></tr></tbody>
              <tfoot><tr><th>Итого</th><td v-for="(value, index) in productQuantityReport.totalByMonth" :key="productQuantityReport.months[index]">{{ value }}</td><td>{{ productQuantityReport.totalQuantity }}</td></tr></tfoot>
            </table>
          </div>
        </section>
        <section class="report-section">
          <h3>Количество изделий по дням</h3>
          <div class="report-table-wrap">
            <table class="report-table">
              <thead><tr><th>Изделие</th><th v-for="day in productQuantityReport.days" :key="day">{{ formatDay(day) }}</th><th>Итого</th></tr></thead>
              <tbody><tr v-for="item in productQuantityReport.items" :key="item.productId"><td>{{ item.productName }}</td><td v-for="(value, index) in item.dayQuantities" :key="productQuantityReport.days[index]">{{ value }}</td><td>{{ item.totalQuantity }}</td></tr></tbody>
              <tfoot><tr><th>Итого</th><td v-for="(value, index) in productQuantityReport.totalByDay" :key="productQuantityReport.days[index]">{{ value }}</td><td>{{ productQuantityReport.totalQuantity }}</td></tr></tfoot>
            </table>
          </div>
        </section>
      </template>
    </template>

    <template v-else-if="activeReport === 'product-time' && productTimeReport">
      <div v-if="productTimeReport.products.length === 0" class="reports-message">
        За выбранный период завершенных таймеров операций нет.
      </div>
      <template v-else>
        <section v-for="product in productTimeReport.products" :key="product.productId" class="report-section">
          <h3>{{ product.productName }}</h3>
          <div class="report-table-wrap">
            <table class="report-table report-table--time">
              <thead><tr><th>Операция</th><th>Исполнитель</th><th v-for="day in productTimeReport.days" :key="day">{{ formatDay(day) }}</th><th>Среднее за период</th><th>% от общего времени</th></tr></thead>
              <tbody><tr v-for="item in product.rows" :key="`${item.operationId ?? 'deleted'}:${item.workerUserId}`"><td>{{ item.operationName }}</td><td>{{ item.workerUserName }}</td><td v-for="(value, index) in item.dailyAverageMs" :key="productTimeReport.days[index]">{{ formatDuration(value) }}</td><td>{{ formatDuration(item.averageMs) }}</td><td>{{ formatPercentage(item.shareOfProductTime) }}</td></tr></tbody>
              <tfoot><tr><th colspan="2">Итого</th><td v-for="(value, index) in product.dailyAverageMs" :key="productTimeReport.days[index]">{{ formatDuration(value) }}</td><td>{{ formatDuration(product.averageMs) }}</td><td>100%</td></tr></tfoot>
            </table>
          </div>
        </section>
      </template>
    </template>

    <template v-else-if="activeReport === 'order-batches' && orderBatchReport">
      <div v-if="orderBatchReport.items.length === 0" class="reports-message">
        За выбранный период завершенных заказов нет.
      </div>
      <section v-else class="report-section">
        <div class="report-section__head">
          <h3>Время по партиям</h3>
          <span>Найдено заказов: {{ orderBatchReport.total }}</span>
        </div>
        <div class="report-table-wrap">
          <table class="report-table report-table--batches">
            <thead>
              <tr>
                <th>Партия</th>
                <th>ФИО</th>
                <th>Изделие / вид кожи</th>
                <th>Операция</th>
                <th>Сдано, шт.</th>
                <th>Затрачено времени</th>
                <th>Время на 1 шт.</th>
              </tr>
            </thead>
            <tbody>
              <template v-for="order in orderBatchReport.items" :key="order.orderId">
                <tr class="report-batch-total">
                  <th scope="row">{{ order.orderNumber }}</th>
                  <td>Общее время</td>
                  <td>
                    {{ order.productName }}
                    <span v-if="order.leatherTypeName"> / {{ order.leatherTypeName }}</span>
                    <small>Завершен {{ formatCompletionDate(order.completedAt) }}</small>
                  </td>
                  <td>—</td>
                  <td>{{ order.submittedQuantity }}</td>
                  <td>{{ formatDuration(order.totalElapsedMs) }}</td>
                  <td>{{ formatDuration(order.averageMs) }}</td>
                </tr>
                <tr
                  v-for="detail in order.details"
                  :key="`${order.orderId}:${detail.operationId ?? 'deleted'}:${detail.workerUserId ?? 'empty'}`"
                >
                  <td>{{ order.orderNumber }}</td>
                  <td>{{ detail.workerUserName }}</td>
                  <td>
                    {{ order.productName }}
                    <span v-if="order.leatherTypeName"> / {{ order.leatherTypeName }}</span>
                  </td>
                  <td>{{ detail.operationName }}</td>
                  <td>{{ order.submittedQuantity }}</td>
                  <td>{{ formatDuration(detail.elapsedMs) }}</td>
                  <td>{{ formatDuration(detail.averageMs) }}</td>
                </tr>
                <tr class="report-batch-spacer" aria-hidden="true">
                  <td colspan="7"></td>
                </tr>
              </template>
            </tbody>
          </table>
        </div>
        <div v-if="orderBatchReport.pages > 1" class="reports-pagination">
          <button
            type="button"
            class="reports-button reports-button--secondary"
            :disabled="loading || orderBatchReport.page <= 1"
            @click="void selectOrderBatchPage(orderBatchReport.page - 1)"
          >
            Назад
          </button>
          <span>Страница {{ orderBatchReport.page }} из {{ orderBatchReport.pages }}</span>
          <button
            type="button"
            class="reports-button reports-button--secondary"
            :disabled="loading || orderBatchReport.page >= orderBatchReport.pages"
            @click="void selectOrderBatchPage(orderBatchReport.page + 1)"
          >
            Далее
          </button>
        </div>
      </section>
    </template>
  </article>
</template>

<style scoped>
.reports-panel {
  display: grid;
  gap: 22px;
  padding: 24px;
  border: 1px solid var(--color-border);
  border-radius: 24px;
  background: var(--color-surface);
}

.reports-panel__head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 18px;
}

.reports-panel__head h2,
.report-section h3 {
  margin: 0;
}

.reports-panel__eyebrow {
  display: block;
  margin-bottom: 6px;
  color: var(--color-text-secondary);
  font-size: 0.78rem;
  font-weight: 800;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.reports-tabs {
  display: flex;
  gap: 8px;
  padding: 6px;
  border-radius: 16px;
  background: var(--color-surface-soft);
}

.reports-tab,
.reports-button {
  min-height: 42px;
  padding: 10px 16px;
  border: 0;
  border-radius: 12px;
  font: inherit;
  font-weight: 700;
  cursor: pointer;
}

.reports-tab {
  color: var(--color-text-secondary);
  background: transparent;
}

.reports-tab--active,
.reports-button {
  color: #fff;
  background: var(--color-primary);
}

.reports-filters {
  display: flex;
  align-items: flex-end;
  flex-wrap: wrap;
  gap: 12px;
}

.reports-field {
  display: grid;
  gap: 6px;
  min-width: 160px;
}

.reports-field span {
  color: var(--color-text-secondary);
  font-size: 0.82rem;
  font-weight: 700;
}

.reports-field input,
.reports-field select {
  min-height: 42px;
  padding: 9px 12px;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  color: var(--color-text);
  background: var(--color-surface);
  font: inherit;
}

.reports-actions {
  display: flex;
  gap: 8px;
}

.reports-button:disabled {
  cursor: not-allowed;
  opacity: 0.6;
}

.reports-button--secondary {
  color: var(--color-primary);
  background: var(--color-surface-soft);
}

.reports-message {
  padding: 18px;
  border-radius: 14px;
  color: var(--color-text-secondary);
  background: var(--color-surface-soft);
}

.reports-message--error {
  color: var(--color-danger);
}

.report-section {
  display: grid;
  gap: 12px;
  min-width: 0;
}

.report-section__head,
.reports-pagination {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.report-section__head span,
.reports-pagination span {
  color: var(--color-text-secondary);
  font-weight: 700;
}

.report-table-wrap {
  max-width: 100%;
  overflow-x: auto;
  border: 1px solid var(--color-border);
  border-radius: 16px;
}

.report-table {
  width: max-content;
  min-width: 100%;
  border-collapse: collapse;
}

.report-table th,
.report-table td {
  padding: 11px 13px;
  border-bottom: 1px solid var(--color-border);
  text-align: right;
  white-space: nowrap;
}

.report-table th:first-child,
.report-table td:first-child,
.report-table--time th:nth-child(2),
.report-table--time td:nth-child(2) {
  position: sticky;
  left: 0;
  text-align: left;
  background: var(--color-surface);
}

.report-table--time th:nth-child(2),
.report-table--time td:nth-child(2) {
  position: static;
}

.report-table thead th {
  color: var(--color-text-secondary);
  background: var(--color-surface-soft);
}

.report-table tfoot th,
.report-table tfoot td {
  border-bottom: 0;
  color: var(--color-text);
  background: var(--color-surface-soft);
  font-weight: 800;
}

.report-table--batches td:nth-child(1),
.report-table--batches th:nth-child(1),
.report-table--batches td:nth-child(2),
.report-table--batches th:nth-child(2),
.report-table--batches td:nth-child(3),
.report-table--batches th:nth-child(3),
.report-table--batches td:nth-child(4),
.report-table--batches th:nth-child(4) {
  text-align: left;
}

.report-table--batches small {
  display: block;
  margin-top: 4px;
  color: var(--color-text-secondary);
}

.report-table--batches .report-batch-total th,
.report-table--batches .report-batch-total td {
  background: var(--color-surface-soft);
  font-weight: 800;
}

.report-table--batches .report-batch-spacer td {
  height: 10px;
  padding: 0;
  border: 0;
  background: var(--color-surface);
}

.reports-pagination {
  justify-content: flex-end;
}

@media (max-width: 760px) {
  .reports-panel {
    padding: 18px;
  }

  .reports-panel__head,
  .reports-tabs,
  .reports-filters,
  .reports-actions {
    align-items: stretch;
    flex-direction: column;
  }

  .report-section__head,
  .reports-pagination {
    align-items: stretch;
    flex-direction: column;
  }

  .reports-field,
  .reports-button {
    width: 100%;
  }
}
</style>
