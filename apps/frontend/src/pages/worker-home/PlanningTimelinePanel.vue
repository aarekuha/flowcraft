<script setup lang="ts">
import { computed, onMounted, ref, onBeforeUnmount, watch, nextTick } from "vue";
import { fetchPlanningTimeline, type PlanningTimeline } from "@/shared/api/planningTimeline";
import { dayDate, layoutTimeline, projectTimeline, defaultTimelineRange, timelineRangeView, findTimelineOrders, orderColor, toggleOrderFocus, zoomTimeline, type PlannedBlock, type TimelineView } from "@/shared/lib/planningTimeline";
import { getPlanningIssueLabel, getPlanningIssueHint } from "@/shared/lib/productionPlanning";

const data = ref<PlanningTimeline | null>(null);
const loading = ref(false);
const error = ref("");
const initialRange = defaultTimelineRange();
const dateFrom = ref(initialRange.from);
const dateTo = ref(initialRange.to);
const appliedRange = ref({ ...initialRange });
const searchElement = ref<HTMLElement | null>(null);
const orderQuery = ref("");
const searchOpen = ref(false);
const searchMessage = ref("");
const orderMatches = computed(() => findTimelineOrders(data.value?.items ?? [], orderQuery.value));
const layout = computed(() => layoutTimeline(data.value?.items ?? []));
const focus = ref<{ view: TimelineView; orderId: number | null; previous: TimelineView | null }>({ view: layout.value.bounds, orderId: null, previous: null });
const view = computed(() => focus.value.view);
const rangeError = computed(() => timelineRangeView(layout.value, dateFrom.value, dateTo.value) ? "" : "Указать корректные даты: начало не позже окончания.");
const selectedView = computed(() => timelineRangeView(layout.value, appliedRange.value.from, appliedRange.value.to) ?? layout.value.bounds);
const navigationBounds = computed(() => focus.value.orderId === null ? selectedView.value : {
  ...layout.value.bounds,
  start: Math.min(layout.value.bounds.start, selectedView.value.start),
  end: Math.max(layout.value.bounds.end, selectedView.value.end),
});
const missing = computed(() => (data.value?.items ?? []).filter(item => !item.first_planned_date || !item.last_planned_date));
const focusMissing = computed(() => missing.value.filter(item => item.order_id === focus.value.orderId).length);
const focusedOrder = computed(() => data.value?.items.find(item => item.order_id === focus.value.orderId));
const chartElement = ref<HTMLElement | null>(null);
const previousScrollTop = ref(0);
const viewportWidth = ref(1200);
const viewportHeight = ref(600);
let resizeObserver: ResizeObserver | null = null;
const projection = computed(() => projectTimeline(layout.value, view.value, focus.value.orderId));
const graphHeight = computed(() => projection.value.height);
const chartLeft = computed(() => Math.min(320, viewportWidth.value * .35));
const chartWidth = computed(() => Math.max(1, viewportWidth.value - chartLeft.value));
const x = (day: number) => chartLeft.value + (day - view.value.start) / (view.value.end - view.value.start) * chartWidth.value;
const dateLabel = (day: number) => dayDate(day).toLocaleDateString("ru-RU", { timeZone: "UTC", day: "2-digit", month: "2-digit", year: "numeric" });
const ticks = computed(() => {
  const span = view.value.end - view.value.start;
  const step = Math.max(1, Math.ceil(span / Math.max(1, Math.floor(chartWidth.value / 110))));
  const values = [];
  for (let day = Math.ceil(view.value.start); day < view.value.end; day += step) values.push(day);
  return values;
});
const visibleGroups = computed(() => projection.value.groups.map((group, index, groups) => ({
  ...group,
  height: (groups[index + 1]?.top ?? projection.value.height) - group.top,
  blocks: projection.value.blocks.filter(block => block.lane >= group.firstLane && block.lane < group.firstLane + group.laneCount),
})));
const visibleBlocks = computed(() => projection.value.blocks);
const blockX = (block: PlannedBlock) => x(Math.max(block.start, view.value.start));
const blockWidth = (block: PlannedBlock) => Math.max(1, x(Math.min(block.end, view.value.end)) - blockX(block));
const labelSize = 14;
function blockTitle(block: PlannedBlock) {
  const item = block.item;
  return `Заказ ${item.order_number} · ${item.product_name} · ${item.product_version}\n${item.operation_name}\n${dateLabel(block.start)} — ${dateLabel(block.end - 1)}${item.status === "unplanned" ? "\nЗапланирована только часть операции" : ""}${item.issue_codes.length ? "\n" + item.issue_codes.map(getPlanningIssueLabel).join("; ") : ""}\nНажать для фокуса на заказе; повторно — вернуть масштаб`;
}
async function selectOrder(orderId: number) {
  if (focus.value.orderId === null) previousScrollTop.value = chartElement.value?.scrollTop ?? 0;
  focus.value = toggleOrderFocus(layout.value, orderId, focus.value);
  await nextTick();
  chartElement.value?.scrollTo({ top: focus.value.orderId === null ? previousScrollTop.value : 0 });
}
function reset() {
  focus.value = { view: { ...selectedView.value }, orderId: null, previous: null };
  chartElement.value?.scrollTo({ top: 0 });
}
function applyRange() {
  if (rangeError.value) return;
  appliedRange.value = { from: dateFrom.value, to: dateTo.value };
  reset();
}
function closeSearchOutside(event: PointerEvent) {
  if (event.target instanceof Node && !searchElement.value?.contains(event.target)) searchOpen.value = false;
}
function findOrder() {
  searchOpen.value = true;
  searchMessage.value = "";
  const exact = orderMatches.value.find(order => order.number.toLocaleLowerCase("ru") === orderQuery.value.trim().toLocaleLowerCase("ru"));
  const match = exact ?? (orderMatches.value.length === 1 ? orderMatches.value[0] : null);
  if (match) chooseOrder(match.id);
}
function chooseOrder(orderId: number) {
  const match = orderMatches.value.find(order => order.id === orderId);
  if (!match) return;
  orderQuery.value = match.number;
  searchOpen.value = false;
  if (!match.hasDates) {
    searchMessage.value = `Заказ ${match.number}: рассчитанных дат нет. Причины указаны под графиком.`;
    return;
  }
  searchMessage.value = "";
  if (focus.value.orderId !== orderId) void selectOrder(orderId);
}
function zoom(factor: number) { focus.value = { ...focus.value, view: zoomTimeline(view.value, factor, navigationBounds.value) }; }
function pan(direction: number) {
  const span = view.value.end - view.value.start;
  const start = Math.max(navigationBounds.value.start, Math.min(navigationBounds.value.end - span, view.value.start + direction * span / 2));
  focus.value = { ...focus.value, view: { ...view.value, start, end: start + span } };
}
async function load() {
  if (loading.value) return;
  loading.value = true; error.value = "";
  try { data.value = await fetchPlanningTimeline(); reset(); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "Не удалось загрузить план"; }
  finally { loading.value = false; }
}
watch(chartElement, element => {
  resizeObserver?.disconnect();
  if (element) {
    resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(element);
    resize();
  }
});
function resize() {
  viewportWidth.value = chartElement.value?.clientWidth || 1200;
  viewportHeight.value = Math.max(240, Math.min(760, window.innerHeight * .6));
}
onMounted(async () => {
  document.addEventListener("pointerdown", closeSearchOutside);
  window.addEventListener("resize", resize);
  await load();
});
onBeforeUnmount(() => { document.removeEventListener("pointerdown", closeSearchOutside); resizeObserver?.disconnect(); window.removeEventListener("resize", resize); });
</script>

<template>
  <article class="timeline-panel">
    <header class="timeline-head">
      <div><h2>Рабочее время</h2><p>Прогноз по дням · от первого до последнего запланированного дня операции</p><p v-if="data?.calculation.active_completed_at">Расчёт: {{ new Date(data.calculation.active_completed_at).toLocaleString('ru-RU') }}</p></div>
      <button type="button" class="fc-button" :disabled="loading" @click="load">{{ loading ? 'Загрузка…' : 'Обновить' }}</button>
    </header>
    <div class="timeline-filters">
      <form class="range-form" @submit.prevent="applyRange">
        <label>С<input v-model="dateFrom" type="date" required></label>
        <label>По<input v-model="dateTo" type="date" required></label>
        <button type="submit" class="fc-button" :disabled="Boolean(rangeError)">Построить</button>
      </form>
      <form ref="searchElement" class="order-search" @submit.prevent="findOrder" @keydown.esc="searchOpen = false">
        <label for="timeline-order-search">Найти заказ</label>
        <div class="search-controls"><input id="timeline-order-search" v-model="orderQuery" type="search" placeholder="Номер заказа" autocomplete="off" @input="searchOpen = true; searchMessage = ''" @keydown.esc="searchOpen = false"><button type="submit" class="fc-button" :disabled="!orderQuery.trim() || !data">Найти</button></div>
        <div v-if="searchOpen && orderQuery.trim()" class="search-results">
          <button v-for="order in orderMatches.slice(0, 30)" :key="order.id" type="button" @click="chooseOrder(order.id)"><strong>{{ order.number }}</strong> · {{ order.product }}<small v-if="!order.hasDates">Без рассчитанных дат</small></button>
          <p v-if="!orderMatches.length">Заказ не найден в опубликованном прогнозе.</p>
          <p v-if="orderMatches.length > 30">Найдено {{ orderMatches.length }}. Уточнить номер заказа.</p>
        </div>
      </form>
    </div>
    <p v-if="rangeError" class="message error" role="alert">{{ rangeError }}</p>
    <p v-if="searchMessage" class="message" role="status">{{ searchMessage }}</p>
    <p v-if="error" class="message error" role="alert">{{ error }}</p>
    <p v-if="data?.calculation.is_stale" class="message">Показан последний опубликованный расчёт. Исходные данные изменились; для актуализации нужен пересчёт администратором.</p>
    <p v-if="data && data.calculation.active_run_id === null" class="message">Расчёт ещё не опубликован.</p>
    <template v-if="layout.blocks.length">
      <div class="timeline-toolbar" aria-label="Масштаб графика">
        <button type="button" class="fc-button" :disabled="view.end - view.start <= 1" @click="zoom(.5)">+ Приблизить</button>
        <button type="button" class="fc-button" :disabled="view.end - view.start >= navigationBounds.end - navigationBounds.start" @click="zoom(2)">− Отдалить</button>
        <button type="button" class="fc-button" :disabled="view.start <= navigationBounds.start" aria-label="Предыдущие дни" @click="pan(-1)">←</button>
        <button type="button" class="fc-button" :disabled="view.end >= navigationBounds.end" aria-label="Следующие дни" @click="pan(1)">→</button>
        <button type="button" class="fc-button" @click="reset">Выбранный период</button>
        <span>{{ dateLabel(view.start) }} — {{ dateLabel(Math.ceil(view.end) - 1) }}</span>
      </div>
      <div v-if="focusedOrder" class="focus-note" role="status"><span>Фокус: заказ {{ focusedOrder.order_number }}</span><button type="button" class="fc-button" @click="selectOrder(focusedOrder.order_id)">Вернуть масштаб</button><span v-if="focusMissing">Без рассчитанных дат: {{ focusMissing }}. Причины — под графиком.</span></div>
      <p class="hint">Цвет обозначает заказ. Нажатие на блок показывает все его рассчитанные операции; повторное нажатие возвращает прежний масштаб. Пунктир — частично запланированная операция.</p>
      <p v-if="!visibleBlocks.length" class="message">В выбранном диапазоне нет запланированных операций. Выбор дат меняет отображение, но не запускает пересчёт.</p>
      <div ref="chartElement" class="chart-scroll" :style="{ maxHeight: `${viewportHeight}px` }">
        <div class="chart-date-header">
          <svg class="chart" :viewBox="`0 0 ${viewportWidth} 48`" height="48" role="img" aria-label="Шкала дат">
            <text x="12" y="28" class="axis-label">Операция / дата</text>
            <text v-for="day in ticks" :key="day" :x="x(day) + 3" y="28" class="date-label">{{ dateLabel(day) }}</text>
          </svg>
        </div>
        <svg class="chart" :viewBox="`0 0 ${viewportWidth} ${graphHeight}`" :style="{ height: `${graphHeight}px` }" role="group" aria-label="Распределение заказов по операциям и дням">
          <line v-for="day in ticks" :key="day" :x1="x(day)" :x2="x(day)" y1="0" :y2="graphHeight" stroke="#d6dee6" />
          <g v-for="group in visibleGroups" :key="group.key" class="operation-row">
            <rect class="operation-row-background" x="0" :y="group.top" :width="viewportWidth" :height="group.height" />
            <line x1="0" :x2="viewportWidth" :y1="group.top" :y2="group.top" stroke="#d6dee6" />
            <text x="12" :y="group.top + 24" :font-size="labelSize"><title>{{ group.name }}</title>{{ group.name.length > Math.floor((chartLeft - 24) / 8.5) ? group.name.slice(0, Math.max(3, Math.floor((chartLeft - 24) / 8.5) - 3)) + '…' : group.name }}</text>
          <g v-for="block in group.blocks" :key="block.key" tabindex="0" role="button" :aria-label="blockTitle(block)" :aria-pressed="focus.orderId === block.item.order_id" class="operation-block" :class="{ muted: focus.orderId !== null && focus.orderId !== block.item.order_id }" @click="selectOrder(block.item.order_id)" @keydown.enter.prevent="selectOrder(block.item.order_id)" @keydown.space.prevent="selectOrder(block.item.order_id)">
            <title>{{ blockTitle(block) }}</title>
            <rect :x="blockX(block) + .5" :y="block.top" :width="Math.max(.5, blockWidth(block) - 1)" :height="block.height" rx="3" :fill="orderColor(block.item.order_id)" :stroke="block.item.status === 'unplanned' ? '#202b38' : 'none'" :stroke-dasharray="block.item.status === 'unplanned' ? '4 3' : undefined" />
            <text v-if="block.height >= 20 && blockWidth(block) > block.item.order_number.length * labelSize * .65 + 12" :x="blockX(block) + 6" :y="block.top + block.height / 2 + 5" :font-size="labelSize" font-weight="600" fill="white">{{ block.item.order_number }}</text>
          </g>
          </g>
        </svg>
      </div>
    </template>
    <p v-else-if="data && !loading && data.calculation.active_run_id !== null" class="message">В текущем расчёте нет операций с запланированными датами.</p>
    <details v-if="missing.length" class="unplanned"><summary>Операции без рассчитанных дат: {{ missing.length }}</summary><div class="unplanned-table"><table><thead><tr><th>Заказ</th><th>Операция</th><th>Причина</th></tr></thead><tbody><tr v-for="item in missing" :key="`${item.order_id}:${item.operation_id}`"><td>{{ item.order_number }}</td><td>{{ item.operation_name }}</td><td><span v-for="code in item.issue_codes" :key="code" :title="getPlanningIssueHint(code)">{{ getPlanningIssueLabel(code) }}<br></span><span v-if="!item.issue_codes.length">{{ item.status === 'completed' ? 'Операция завершена' : 'Даты не определены' }}</span></td></tr></tbody></table></div></details>
  </article>
</template>

<style scoped>
.timeline-filters { display: flex; flex-wrap: wrap; align-items: start; gap: 20px; margin: 20px 0; }
.range-form { display: flex; flex-wrap: wrap; align-items: end; gap: 10px; }
.timeline-filters label { display: grid; gap: 7px; font-size: .875rem; font-weight: 600; }
.timeline-filters input { min-height: 44px; min-width: 0; padding: 10px 12px; border: 1px solid var(--color-border); border-radius: 10px; font: inherit; background: var(--color-surface); color: var(--color-text); }
.range-form input { width: 11rem; }
.order-search { position: relative; flex: 1 1 260px; max-width: 460px; display: grid; gap: 7px; }
.search-controls { display: flex; gap: 10px; }
.search-controls input { flex: 1; width: 0; }
.search-results { position: absolute; top: 100%; left: 0; right: 0; z-index: 3; max-height: 280px; overflow: auto; border: 1px solid var(--color-border); border-radius: 10px; background: var(--color-surface); box-shadow: 0 10px 24px #15273c22; }
.search-results button { display: block; width: 100%; text-align: left; padding: 12px; border: 0; background: transparent; font: inherit; color: inherit; cursor: pointer; }
.search-results button:hover, .search-results button:focus-visible { background: var(--color-surface-soft); }
.search-results p { padding: 12px; margin: 0; font-size: .875rem; }
.search-results small { display: block; color: var(--color-text-secondary); }

.timeline-panel { padding: 22px; background: var(--color-surface); border: 1px solid var(--color-border); border-radius: 24px; }
h2 { margin: 0; font-size: 1.5rem; }
.timeline-head, .timeline-toolbar, .focus-note { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; }
.timeline-head { justify-content: space-between; align-items: flex-start; }
.timeline-head p, .hint { color: var(--color-text-secondary); font-size: .875rem; }
.timeline-toolbar { margin: 20px 0 12px; }
.timeline-toolbar span { font-size: .875rem; }
.message, .focus-note { padding: 12px; background: var(--color-surface-soft); border-radius: 12px; }
.error { background: #fbeaea; color: #963b3b; }
.chart-scroll { overflow: auto; border: 1px solid var(--color-border); border-radius: 12px; }
.chart-date-header { position: sticky; top: 0; z-index: 1; background: var(--color-surface); border-bottom: 1px solid var(--color-border); }
.chart { display: block; width: 100%; }
.axis-label, .date-label { font-size: 14px; fill: var(--color-text-secondary); }
.operation-row-background { fill: transparent; }
.operation-row:hover > .operation-row-background,
.operation-row:focus-within > .operation-row-background { fill: var(--color-surface-soft); fill-opacity: .65; }
.operation-block { cursor: pointer; outline: none; }
.operation-block:hover rect, .operation-block:focus-visible rect { stroke: #111827; stroke-width: 2; }
.operation-block.muted { filter: grayscale(1); opacity: .38; }
.unplanned { margin-top: 20px; }
summary { cursor: pointer; font-weight: 600; }
.unplanned-table { overflow: auto; margin-top: 12px; }
table { border-collapse: collapse; width: 100%; font-size: .875rem; }
th, td { text-align: left; padding: 10px; border-bottom: 1px solid var(--color-border); }
@media (max-width: 760px) { .timeline-panel { padding: 14px; } }
</style>
