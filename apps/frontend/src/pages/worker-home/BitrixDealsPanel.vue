<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { vEscapeClose } from "./escapeClose";
import {
  fetchBitrixDealsStatus, syncBitrixDeals, fetchBitrixDeals, fetchBitrixDeal,
  type BitrixStatus, type BitrixDeals, type BitrixDealDetails,
} from "@/shared/api/bitrix";

const status = ref<BitrixStatus>({ configured: false, syncing: false, synced_at: null, last_error: null });
const data = ref<BitrixDeals>({ items: [], metadata: {}, total: 0, page: 1, page_size: 25 });
const search = ref("");
const state = ref("all");
const category = ref("");
const page = ref(1);
const loading = ref(false);
const starting = ref(false);
const error = ref("");
const selected = ref<BitrixDealDetails | null>(null);
const detailLoading = ref(false);
const detailError = ref("");
const detailOpen = ref(false);
let disposed = false;
let requestId = 0;
let detailRequestId = 0;
let timer: ReturnType<typeof setTimeout> | undefined;
let debounce: ReturnType<typeof setTimeout> | undefined;
const pages = computed(() => Math.max(1, Math.ceil(data.value.total / data.value.page_size)));
const fields = computed(() => Object.entries(selected.value?.fields ?? {}).map(([key, value]) => ({
  key, value, label: data.value.metadata.fields?.[key]?.formLabel || data.value.metadata.fields?.[key]?.listLabel || data.value.metadata.fields?.[key]?.title || key,
})));
function message(cause: unknown) { return cause instanceof Error ? cause.message : "Не удалось загрузить заказы"; }
function timestamp(value: number | null) { return value ? new Date(value).toLocaleString("ru-RU") : "Ещё не загружались"; }
function format(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
}
function categoryName(id: number) { return data.value.metadata.categories?.find(item => Number(item.id) === id)?.name ?? String(id); }
function stageName(id: string) { return data.value.metadata.stages?.find(item => item.STATUS_ID === id)?.NAME ?? id; }
async function load() {
  const id = ++requestId;
  loading.value = true;
  error.value = "";
  const query = new URLSearchParams({ search: search.value, state: state.value, page: String(page.value) });
  if (category.value) query.set("category_id", category.value);
  try {
    const next = await fetchBitrixDeals(query);
    if (!disposed && id === requestId) {
      data.value = next;
      if (page.value > pages.value) page.value = pages.value;
    }
  } catch (cause) { if (!disposed && id === requestId) error.value = message(cause); }
  finally { if (!disposed && id === requestId) loading.value = false; }
}
async function poll() {
  try {
    const next = await fetchBitrixDealsStatus();
    if (disposed) return;
    const refresh = status.value.synced_at !== next.synced_at || (status.value.syncing && !next.syncing);
    status.value = next;
    if (refresh) await load();
  } catch (cause) { if (!disposed) error.value = message(cause); }
  finally { if (!disposed) timer = setTimeout(poll, 3000); }
}
async function sync() {
  starting.value = true;
  error.value = "";
  try { await syncBitrixDeals(); status.value.syncing = true; }
  catch (cause) { error.value = message(cause); }
  finally { starting.value = false; }
}
function closeDetail() { detailRequestId++; detailOpen.value = false; selected.value = null; }
async function openDetail(id: number) {
  const token = ++detailRequestId;
  selected.value = null;
  detailOpen.value = true;
  detailLoading.value = true;
  detailError.value = "";
  try {
    const result = await fetchBitrixDeal(id);
    if (!disposed && token === detailRequestId) selected.value = result;
  } catch (cause) { if (!disposed && token === detailRequestId) detailError.value = message(cause); }
  finally { if (!disposed && token === detailRequestId) detailLoading.value = false; }
}
watch([search, state, category], () => {
  requestId++;
  clearTimeout(debounce);
  if (page.value !== 1) page.value = 1;
  else debounce = setTimeout(load, 250);
});
watch(page, () => { clearTimeout(debounce); void load(); });
onMounted(() => { void load(); void poll(); });
onBeforeUnmount(() => { disposed = true; clearTimeout(timer); clearTimeout(debounce); });
</script>

<template>
  <section class="deals-panel">
    <div class="toolbar">
      <button class="fc-button" type="button" :disabled="starting || status.syncing || !status.configured" @click="sync">{{ status.syncing ? 'Выполняется загрузка Bitrix24…' : 'Обновить заказы' }}</button>
      <span>Последнее обновление: {{ timestamp(status.synced_at) }}</span>
    </div>
    <p class="muted">Открытые сделки из всех воронок и ранее загруженные сделки. Производственные заказы Flowcraft из них пока не создаются.</p>
    <p v-if="!status.configured" class="muted">Для загрузки сохранить вебхук в блоке «Подключение».</p>
    <p v-if="error || status.last_error" class="error" role="alert">{{ error || status.last_error }}</p>
    <div class="toolbar">
      <input v-model="search" type="search" placeholder="ID или название сделки" aria-label="Поиск сделки">
      <select v-model="category" aria-label="Воронка"><option value="">Все воронки</option><option v-for="item in data.metadata.categories ?? []" :key="item.id" :value="String(item.id)">{{ item.name }}</option></select>
      <select v-model="state" aria-label="Состояние сделки"><option value="all">Все сохранённые</option><option value="open">Открытые</option><option value="closed">Закрытые</option><option value="missing">Нет в последней выгрузке</option></select>
    </div>
    <p v-if="loading" role="status">Загрузка…</p>
    <div class="table-wrap"><table>
      <thead><tr><th>ID</th><th>Наименование</th><th>Воронка</th><th>Стадия</th><th>Сумма</th><th>Состояние</th></tr></thead>
      <tbody><tr v-for="item in data.items" :key="item.id">
        <td>{{ item.id }}</td><td><button class="link" @click="openDetail(item.id)">{{ item.title }}</button></td>
        <td>{{ categoryName(item.category_id) }}</td><td>{{ stageName(item.stage_id) }}</td><td>{{ item.amount }} {{ item.currency }}</td>
        <td>{{ !item.present ? 'Нет в последней выгрузке' : item.closed ? 'Закрыта' : 'Открыта' }}</td>
      </tr><tr v-if="!data.items.length && !loading"><td colspan="6">{{ status.synced_at ? 'Сделки не найдены' : 'Для загрузки нажать «Обновить заказы»' }}</td></tr></tbody>
    </table></div>
    <div class="toolbar pagination"><button class="fc-button" :disabled="page <= 1 || loading" @click="page--">Назад</button><span>{{ page }} / {{ pages }} · Всего: {{ data.total }}</span><button class="fc-button" :disabled="page >= pages || loading" @click="page++">Далее</button></div>
    <Teleport to="body">
      <div v-if="detailOpen" v-escape-close="closeDetail" class="bitrix-deal-overlay" @click.self="closeDetail">
        <section role="dialog" aria-modal="true" aria-labelledby="bitrix-deal-title" class="bitrix-deal-dialog">
          <header><h3 id="bitrix-deal-title">{{ selected ? `${selected.id} · ${selected.title}` : 'Сделка Bitrix24' }}</h3><button class="fc-button" aria-label="Закрыть" @click="closeDetail">×</button></header>
          <div class="dialog-body">
            <p v-if="detailLoading">Загрузка…</p><p v-if="detailError" role="alert" class="error">{{ detailError }}</p>
            <template v-if="selected">
              <h4>Товары</h4>
              <div class="table-wrap"><table><thead><tr><th>ID строки</th><th>ID товара</th><th>Наименование</th><th>Количество</th><th>Цена</th></tr></thead><tbody>
                <tr v-for="(row, index) in selected.product_rows" :key="index"><td>{{ row.ID }}</td><td>{{ row.PRODUCT_ID }}</td><td>{{ row.PRODUCT_NAME }}</td><td>{{ row.QUANTITY }}</td><td>{{ row.PRICE }}</td></tr>
                <tr v-if="!selected.product_rows.length"><td colspan="5">Товаров нет</td></tr>
              </tbody></table></div>
              <details v-for="(row, index) in selected.product_rows" :key="index"><summary>Все поля товарной строки {{ row.ID }}</summary><pre>{{ format(row) }}</pre></details>
              <h4>Все поля сделки</h4>
              <dl><template v-for="field in fields" :key="field.key"><dt>{{ field.label }} <small>{{ field.key }}</small></dt><dd><pre>{{ format(field.value) }}</pre></dd></template></dl>
            </template>
          </div>
          <footer><button class="fc-button" @click="closeDetail">Закрыть</button></footer>
        </section>
      </div>
    </Teleport>
  </section>
</template>

<style scoped>
.deals-panel { display: grid; gap: 12px; min-width: 0; }
.toolbar { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
button, input, select { font: inherit; padding: 8px 12px; border: 1px solid #cbd5e1; border-radius: 6px; background: white; }
button { cursor: pointer; } button:disabled { opacity: .55; cursor: default; }
.link { padding: 0; border: 0; color: #2563eb; text-align: left; }
.muted { color: #64748b; } .error { color: #b91c1c; }
.table-wrap { overflow: auto; } table { border-collapse: collapse; width: 100%; }
th, td { padding: 10px; border-bottom: 1px solid #e2e8f0; text-align: left; vertical-align: top; }
.pagination { justify-content: flex-end; }
.bitrix-deal-overlay { position: fixed; inset: 0; z-index: 1200; background: #0f172a88; display: grid; place-items: center; padding: 12px; }
.bitrix-deal-dialog { background: white; width: min(1050px, 100%); max-height: calc(100dvh - 24px); display: flex; flex-direction: column; min-height: 0; border-radius: 12px; overflow: hidden; }
header, footer { flex-shrink: 0; padding: 16px; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
h3 { margin: 0; } footer { justify-content: flex-end; }
.dialog-body { padding: 0 16px 16px; min-height: 0; overflow: auto; }
dt { font-weight: 600; margin-top: 12px; } dt small { color: #64748b; font-weight: normal; } dd { margin: 4px 0; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; margin: 0; font: inherit; }
summary { cursor: pointer; padding: 8px 0; }
</style>
