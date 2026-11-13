<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { vEscapeClose } from "./escapeClose";
import BitrixProductPicker from "./BitrixProductPicker.vue";
import BitrixDealsPanel from "./BitrixDealsPanel.vue";
import {
  fetchBitrixStatus, fetchBitrixCatalog, saveBitrixSettings, checkBitrixConnection,
  syncBitrixCatalog, saveBitrixMapping, saveBitrixMappingRequirement, cancelBitrixSync,
  type BitrixCatalog, type BitrixItem, type BitrixStatus, type MappedProduct,
} from "@/shared/api/bitrix";

const props = defineProps<{ settingsOnly?: boolean }>();

const status = ref<BitrixStatus>({ configured: false, syncing: false, synced_at: null, last_error: null });
const catalog = ref<BitrixCatalog>({ items: [], products: [], metadata: {} });
const section = ref<"catalog" | "deals">("catalog");
const tab = ref<"goods" | "mappings">("goods");
const webhook = ref("");
const working = ref(false);
const cancelling = ref(false);
const loading = ref(true);
const error = ref("");
const notice = ref("");
const search = ref("");
const activity = ref("all");
const catalogFilter = ref("");
const page = ref(1);
const productSearch = ref("");
const mappingFilter = ref("all");
const productPage = ref(1);
const pageSize = 25;
const selected = ref<BitrixItem | null>(null);
const drafts = ref<Record<number, number[]>>({});
const savingProduct = ref<number | null>(null);
let timer: ReturnType<typeof setTimeout> | undefined;
let disposed = false;

const goods = computed(() => catalog.value.items.filter(item => {
  const query = search.value.trim().toLocaleLowerCase();
  return (!query || `${item.id} ${item.name} ${item.parent_id ?? ""}`.toLocaleLowerCase().includes(query))
    && (!catalogFilter.value || String(item.catalog_id) === catalogFilter.value)
    && (activity.value === "all" || (activity.value === "active" ? item.active && item.present : !item.active || !item.present));
}));
const products = computed(() => catalog.value.products.filter(item => {
  const matchesSearch = `${item.id} ${item.name} ${item.version}`.toLocaleLowerCase().includes(productSearch.value.trim().toLocaleLowerCase());
  const matchesStatus = mappingFilter.value === "all"
    || (mappingFilter.value === "mapped" && item.bitrix_ids.length > 0)
    || (mappingFilter.value === "not-required" && item.mapping_not_required)
    || (mappingFilter.value === "unmapped" && !item.mapping_not_required && item.bitrix_ids.length === 0);
  return matchesSearch && matchesStatus;
}));
const goodsPages = computed(() => Math.max(1, Math.ceil(goods.value.length / pageSize)));
const productPages = computed(() => Math.max(1, Math.ceil(products.value.length / pageSize)));
const visibleGoods = computed(() => goods.value.slice((page.value - 1) * pageSize, page.value * pageSize));
const visibleProducts = computed(() => products.value.slice((productPage.value - 1) * pageSize, productPage.value * pageSize));
const byId = computed(() => new Map(catalog.value.items.map(item => [item.id, item])));
const selectedFields = computed(() => {
  if (!selected.value) return [];
  const fields = catalog.value.metadata[String(selected.value.catalog_id)]?.fields ?? {};
  const keys = new Set([...Object.keys(fields), ...Object.keys(selected.value.fields)]);
  return [...keys].map(key => ({ key, label: fields[key]?.name ?? key, value: selected.value?.fields[key] }));
});
watch([search, activity, catalogFilter], () => { page.value = 1; });
watch([productSearch, mappingFilter], () => { productPage.value = 1; });

function message(cause: unknown) { return cause instanceof Error ? cause.message : "Не удалось выполнить запрос"; }
function timestamp(value: number | null) { return value ? new Date(value).toLocaleString("ru-RU") : "Ещё не загружались"; }
function format(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  return typeof value === "object" ? JSON.stringify(value, null, 2) : String(value);
}
function typeName(item: BitrixItem) {
  return ({ 1: "Товар", 3: "Товар с вариациями", 4: "Вариация", 6: "Услуга" } as Record<string, string>)[String(item.fields.type)] ?? String(item.fields.type ?? "—");
}
function priceLabel(item: BitrixItem) {
  return item.prices.length ? item.prices.map(price => `${price.price ?? "—"} ${price.currency ?? ""} (тип ${price.catalogGroupId ?? "—"})`).join("; ") : "—";
}
function dirty(product: MappedProduct) {
  return JSON.stringify([...(drafts.value[product.id] ?? [])].sort()) !== JSON.stringify([...product.bitrix_ids].sort());
}
function options(product: MappedProduct) {
  return catalog.value.items.filter(item => item.present
    && !(drafts.value[product.id] ?? []).includes(item.id)
    && (item.mapped_product_id === null || item.mapped_product_id === product.id));
}
function addMapping(productId: number, bitrixId: number) {
  const selected = drafts.value[productId] ?? [];
  if (!selected.includes(bitrixId)) drafts.value[productId] = [...selected, bitrixId];
}
function removeMapping(productId: number, id: number) {
  drafts.value[productId] = (drafts.value[productId] ?? []).filter(value => value !== id);
}
async function loadCatalog() {
  if (props.settingsOnly) return;
  const next = await fetchBitrixCatalog();
  if (disposed) return;
  const changed = new Set(catalog.value.products.filter(dirty).map(product => product.id));
  for (const product of next.products) {
    if (!changed.has(product.id)) drafts.value[product.id] = [...product.bitrix_ids];
  }
  catalog.value = next;
  page.value = Math.min(page.value, goodsPages.value);
  productPage.value = Math.min(productPage.value, productPages.value);
}
async function poll() {
  try {
    const previous = status.value;
    const next = await fetchBitrixStatus();
    if (disposed) return;
    status.value = next;
    if ((previous.syncing && !next.syncing) || previous.synced_at !== next.synced_at) await loadCatalog();
  } catch (cause) { if (!disposed) error.value = message(cause); }
  finally { if (!disposed) timer = setTimeout(poll, 3000); }
}
async function cancelSync() {
  const job = status.value.job_id;
  if (!job || cancelling.value) return;
  cancelling.value = true; error.value = ""; notice.value = "";
  try {
    await cancelBitrixSync(job);
    status.value = await fetchBitrixStatus();
    notice.value = "Загрузка прервана. Можно запустить обновление повторно";
  } catch (cause) { error.value = message(cause); }
  finally { cancelling.value = false; }
}
async function saveSettings() {
  working.value = true; error.value = ""; notice.value = "";
  try {
    status.value = await saveBitrixSettings(webhook.value);
    webhook.value = "";
    notice.value = "Вебхук сохранён на сервере";
  } catch (cause) { error.value = message(cause); }
  finally { working.value = false; }
}
async function check() {
  working.value = true; error.value = ""; notice.value = "";
  try { await checkBitrixConnection(); notice.value = "Подключение работает, каталоги доступны"; }
  catch (cause) { error.value = message(cause); }
  finally { working.value = false; }
}
async function sync() {
  working.value = true; error.value = ""; notice.value = "";
  try { await syncBitrixCatalog(); status.value = await fetchBitrixStatus(); await loadCatalog(); }
  catch (cause) { error.value = message(cause); }
  finally { working.value = false; }
}
async function saveRow(product: MappedProduct) {
  savingProduct.value = product.id; error.value = ""; notice.value = "";
  const sent = [...(drafts.value[product.id] ?? [])];
  try {
    await saveBitrixMapping(product.id, sent);
    product.bitrix_ids = sent;
    await loadCatalog();
    notice.value = `Сопоставления изделия №${product.id} сохранены`;
  } catch (cause) { error.value = message(cause); }
  finally { savingProduct.value = null; }
}
async function toggleMappingRequirement(product: MappedProduct) {
  savingProduct.value = product.id; error.value = ""; notice.value = "";
  try {
    await saveBitrixMappingRequirement(product.id, !product.mapping_not_required);
    await loadCatalog();
    notice.value = `Статус изделия №${product.id} сохранён`;
  } catch (cause) { error.value = message(cause); }
  finally { savingProduct.value = null; }
}
onMounted(async () => {
  try { status.value = await fetchBitrixStatus(); await loadCatalog(); }
  catch (cause) { error.value = message(cause); }
  finally { loading.value = false; if (!disposed) timer = setTimeout(poll, 3000); }
});
onBeforeUnmount(() => { disposed = true; clearTimeout(timer); webhook.value = ""; });
</script>

<template>
  <section class="bitrix-panel" :class="{ 'bitrix-panel--settings': props.settingsOnly }">
    <header class="section-head"><h2>Bitrix24</h2><p v-if="props.settingsOnly">Подключение к каталогу и CRM</p></header>
    <nav v-if="!props.settingsOnly" class="fc-tabs" aria-label="Разделы Bitrix24">
      <button type="button" class="fc-tab" :class="{ 'fc-tab--active': section === 'catalog' }" @click="section = 'catalog'">Каталог и сопоставления</button>
      <button class="fc-tab" type="button" disabled title="Работа с заказами временно отключена">Заказы из Bitrix24</button>
    </nav>
    <div v-if="status.syncing" class="sync-progress" role="status" aria-live="polite">
      <template v-if="status.progress">
        <strong>{{ status.progress.kind === 'deals' ? 'Заказы' : 'Каталог' }}: {{ status.progress.stage }}</strong>
        <span>{{ status.progress.completed }}{{ status.progress.total === null ? ' получено' : ` / ${status.progress.total}` }}</span>
        <progress v-if="status.progress.total !== null && status.progress.total > 0" :value="status.progress.completed" :max="status.progress.total" aria-label="Прогресс текущего этапа" />
        <small>Обновлено: {{ timestamp(status.progress.updated_at) }}</small>
      </template>
      <span v-else>Подготовка загрузки Bitrix24…</span>
      <button class="fc-button" type="button" :disabled="cancelling || !status.job_id" @click="cancelSync">{{ cancelling ? 'Прерывание…' : 'Прервать загрузку' }}</button>
    </div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <p v-if="notice" class="notice" role="status">{{ notice }}</p>
    <div class="layout">
      <main v-if="!props.settingsOnly" class="workspace">
        <BitrixDealsPanel v-if="section === 'deals'" />
        <div v-show="section === 'catalog'">
        <nav class="fc-tabs" aria-label="Каталог и сопоставления">
          <button type="button" class="fc-tab" :class="{ 'fc-tab--active': tab === 'goods' }" @click="tab = 'goods'">Товары из Bitrix</button>
          <button type="button" class="fc-tab" :class="{ 'fc-tab--active': tab === 'mappings' }" @click="tab = 'mappings'">Сопоставления</button>
        </nav>
        <p v-if="status.last_error" class="error" role="alert">{{ status.last_error }}</p>
        <p v-if="loading">Загрузка…</p>
        <template v-else-if="tab === 'goods'">
          <div class="toolbar">
            <button class="fc-button" type="button" :disabled="working || status.syncing || !status.configured" @click="sync">{{ status.syncing ? 'Выполняется загрузка Bitrix24…' : 'Обновить товары' }}</button>
            <span>Последнее обновление: {{ timestamp(status.synced_at) }}</span>
          </div>
          <div class="filters">
            <input v-model="search" aria-label="Поиск товара Bitrix" placeholder="ID или название товара" type="search">
            <select v-model="catalogFilter" aria-label="Каталог"><option value="">Все каталоги</option><option v-for="(meta, id) in catalog.metadata" :key="id" :value="String(id)">{{ meta.catalog.name }} ({{ id }})</option></select>
            <select v-model="activity" aria-label="Активность"><option value="all">Все товары</option><option value="active">Активные</option><option value="inactive">Неактивные и отсутствующие</option></select>
          </div>
          <p class="muted">Найдено: {{ goods.length }}. Цены сохранены из Bitrix и не меняют расценки Flowcraft.</p>
          <div class="table-wrap"><table>
            <thead><tr><th>ID</th><th>Наименование</th><th>Каталог</th><th>Тип</th><th>Основной товар</th><th>Активность</th><th>Цены</th><th>Изделие Flowcraft</th></tr></thead>
            <tbody><tr v-for="item in visibleGoods" :key="item.id">
              <td>{{ item.id }}</td><td><button class="link" type="button" @click="selected = item">{{ item.name }}</button></td>
              <td>{{ item.catalog_id }}</td><td>{{ typeName(item) }}</td><td>{{ item.parent_id ? `${item.parent_id} · ${byId.get(item.parent_id)?.name ?? ''}` : '—' }}</td>
              <td>{{ !item.present ? 'Нет в последней выгрузке' : item.active ? 'Активен' : 'Неактивен' }}</td><td>{{ priceLabel(item) }}</td><td>{{ item.mapped_product_id ?? 'Не сопоставлен' }}</td>
            </tr><tr v-if="!visibleGoods.length"><td colspan="8">{{ status.synced_at ? 'Товары не найдены' : 'Для получения товаров сохранить подключение и нажать «Обновить товары»' }}</td></tr></tbody>
          </table></div>
          <div class="pagination"><button class="fc-button" :disabled="page <= 1" @click="page--">Назад</button><span>{{ page }} / {{ goodsPages }}</span><button class="fc-button" :disabled="page >= goodsPages" @click="page++">Далее</button></div>
        </template>
        <template v-else>
          <div class="filters"><input v-model="productSearch" type="search" aria-label="Поиск изделия Flowcraft" placeholder="ID, наименование или версия изделия">
            <select v-model="mappingFilter" aria-label="Статус сопоставления"><option value="all">Все изделия</option><option value="mapped">Сопоставлено</option><option value="unmapped">Не сопоставлено</option><option value="not-required">Не требует сопоставления</option></select>
          </div>
          <p class="muted">Активные изделия Flowcraft: {{ products.length }}. Одному изделию можно назначить несколько товаров Bitrix.</p>
          <div class="table-wrap"><table>
            <thead><tr><th>ID изделия</th><th>Наименование</th><th>Версия</th><th>Товары Bitrix</th><th>Действия</th></tr></thead>
            <tbody><tr v-for="product in visibleProducts" :key="product.id">
              <td>{{ product.id }}</td><td>{{ product.name }}</td><td>{{ product.version }}</td>
              <td class="mapping-cell">
                <div v-for="id in drafts[product.id] ?? []" :key="id" class="mapping-item">
                  <span>{{ id }} · {{ byId.get(id)?.name ?? 'Неизвестный товар' }}<small v-if="!byId.get(id)?.present"> · Нет в последней выгрузке</small><small v-else-if="!byId.get(id)?.active"> · Неактивен</small></span>
                  <button class="fc-button" type="button" :disabled="savingProduct === product.id" :aria-label="`Убрать товар ${id}`" @click="removeMapping(product.id, id)">×</button>
                </div>
                <span v-if="product.mapping_not_required" class="muted">Не требует сопоставления</span>
                <span v-else-if="!drafts[product.id]?.length" class="muted">Не сопоставлено</span>
                <BitrixProductPicker v-if="!product.mapping_not_required" :items="options(product)" :product-id="product.id"
                  :disabled="savingProduct === product.id" @select="addMapping(product.id, $event)" />
              </td>
              <td><button class="fc-button" type="button" :disabled="savingProduct !== null || !dirty(product)" @click="saveRow(product)">{{ savingProduct === product.id ? 'Сохранение…' : 'Сохранить' }}</button>
                <button class="fc-button" type="button" :disabled="savingProduct !== null || product.bitrix_ids.length > 0 || dirty(product)" :title="product.bitrix_ids.length ? 'Для установки статуса сначала удалить и сохранить сопоставления' : dirty(product) ? 'Сначала сохранить изменения сопоставлений' : ''" @click="toggleMappingRequirement(product)">{{ product.mapping_not_required ? 'Требует сопоставления' : 'Не требует сопоставления' }}</button>
              </td>
            </tr><tr v-if="!visibleProducts.length"><td colspan="5">Активные изделия не найдены</td></tr></tbody>
          </table></div>
          <div class="pagination"><button class="fc-button" :disabled="productPage <= 1" @click="productPage--">Назад</button><span>{{ productPage }} / {{ productPages }}</span><button class="fc-button" :disabled="productPage >= productPages" @click="productPage++">Далее</button></div>
        </template>
        </div>
      </main>
      <aside v-if="props.settingsOnly">
        <section class="connection">
          <span class="connection-status" :class="{ 'connection-status--ready': status.configured }">{{ status.configured ? 'Подключение настроено' : 'Подключение не настроено' }}</span>
          <form @submit.prevent="saveSettings">
            <label for="bitrix-webhook">Вебхук для вызова REST API</label>
            <input id="bitrix-webhook" v-model="webhook" type="password" autocomplete="new-password" :disabled="working || status.syncing" placeholder="https://…bitrix24.ru/rest/…/" required maxlength="2048">
            <p class="muted">{{ status.configured ? 'Для замены подключения ввести новый вебхук того же портала.' : 'Указать входящий вебхук с доступом к торговому каталогу и CRM.' }} Сохранённое значение не отображается.</p>
            <div class="connection-actions"><button type="submit" class="fc-button fc-button--primary" :disabled="working || status.syncing || !webhook.trim()">Сохранить</button>
            <button class="fc-button" type="button" :disabled="working || status.syncing || !status.configured" @click="check">Проверить подключение</button></div>
          </form>
        </section>
      </aside>
    </div>
    <Teleport to="body">
      <div v-if="selected" class="bitrix-overlay" @click.self="selected = null">
        <section v-escape-close="() => selected = null" class="bitrix-dialog" role="dialog" aria-modal="true" aria-labelledby="bitrix-item-title" tabindex="-1">
          <header><h3 id="bitrix-item-title">{{ selected.id }} · {{ selected.name }}</h3><button class="fc-button" type="button" @click="selected = null">Закрыть</button></header>
          <div class="dialog-body">
            <h4>Все поля товара</h4>
            <table><thead><tr><th>Поле</th><th>Код</th><th>Значение</th></tr></thead><tbody><tr v-for="field in selectedFields" :key="field.key"><td>{{ field.label }}</td><td>{{ field.key }}</td><td><pre>{{ format(field.value) }}</pre></td></tr></tbody></table>
            <h4>Цены</h4><p v-if="!selected.prices.length">Цены не заданы</p>
            <div v-for="(price, index) in selected.prices" :key="index"><h5>Тип цены {{ price.catalogGroupId }}</h5><table><tbody><tr v-for="(value, key) in price" :key="key"><th>{{ key }}</th><td><pre>{{ format(value) }}</pre></td></tr></tbody></table></div>
          </div>
        </section>
      </div>
    </Teleport>
  </section>
</template>

<style scoped>
.bitrix-panel--settings { padding: 24px; }
.bitrix-panel--settings .section-head h2 { font-size: 1.05rem; margin: 0; }
.bitrix-panel--settings .section-head p { font-size: .875rem; color: var(--color-text-secondary); margin: 6px 0 20px; }
.bitrix-panel--settings .connection { padding: 0; border: 0; background: transparent; }
.bitrix-panel--settings input { width: 100%; min-width: 0; min-height: 44px; border-radius: 10px; }
.connection-actions { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 6px; }
.connection-status { display: inline-block; border-radius: 8px; background: #eef1f4; padding: 5px 10px; color: #65727d; font-size: .8rem; }
.connection-status--ready { color: #23784d; background: #edf7f0; }

.bitrix-panel { background: #fff; border: 1px solid #e0e5eb; border-radius: 18px; padding: 20px; color: #23344b; }
.section-head h2 { margin: 0 0 16px; }
.fc-tabs { margin-bottom: 20px; }
.section-tab { display: inline-block; padding: 10px 16px; border-bottom: 3px solid #3476a8; font-weight: 600; margin-bottom: 20px; }
.layout { display: grid; grid-template-columns: minmax(0, 1fr); gap: 20px; align-items: start; }
.workspace { min-width: 0; }
.sync-progress { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; padding: 12px; margin-bottom: 16px; background: #edf5fc; border-radius: 8px; }
.sync-progress small { color: #68788a; }
.subtabs, .toolbar, .filters, .pagination { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; margin-bottom: 16px; }
button, input, select { font: inherit; border: 1px solid #ccd6e1; border-radius: 8px; padding: 8px 10px; background: white; color: inherit; max-width: 100%; }
button { cursor: pointer; }
button:disabled { cursor: default; opacity: .5; }
button.active, .toolbar button:not(.fc-button) { background: #edf5fc; border-color: #8cb8d8; }
input:focus, select:focus, button:focus-visible, summary:focus-visible { outline: 2px solid #3476a8; outline-offset: 2px; }
.filters input { flex: 1; min-width: 160px; }
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: .9rem; }
th, td { padding: 10px; border-bottom: 1px solid #e5eaf0; text-align: left; vertical-align: top; }
th { background: #f6f8fb; text-transform: none; }
.link { padding: 0; border: 0; text-align: left; color: #236ba1; background: none; }
.muted { color: #68788a; font-size: .85rem; }
.error { color: #b13030; background: #fff0f0; padding: 10px; border-radius: 8px; }
.notice, .configured { color: #23784d; }
.pagination { justify-content: flex-end; margin-top: 15px; }
.connection { background: #f6f8fb; border: 1px solid #e0e5eb; border-radius: 12px; padding: 14px; }
summary { cursor: pointer; font-weight: 600; }
summary span { display: block; margin: 8px 0 0 16px; font-size: .85rem; font-weight: normal; }
form { display: grid; gap: 10px; margin-top: 16px; }
form label { font-size: .9rem; }
.mapping-cell { min-width: 260px; }
.mapping-item { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 5px 0; }
.bitrix-overlay { position: fixed; inset: 0; z-index: 180; background: #15273c77; display: grid; place-items: center; padding: 16px; }
.bitrix-dialog { background: white; color: #23344b; width: min(1000px, 100%); max-height: calc(100dvh - 32px); display: flex; flex-direction: column; border-radius: 16px; overflow: hidden; }
.bitrix-dialog header { display: flex; justify-content: space-between; align-items: center; gap: 16px; padding: 16px 20px; flex-shrink: 0; border-bottom: 1px solid #e0e5eb; }
.bitrix-dialog h3 { margin: 0; overflow-wrap: anywhere; }
.dialog-body { padding: 16px 20px; overflow: auto; min-height: 0; }
pre { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; font: inherit; }
.dialog-body table { table-layout: fixed; }
.dialog-body td, .dialog-body th { overflow-wrap: anywhere; }
@media (max-width: 1100px) { .layout { grid-template-columns: 1fr; } aside { order: 2; } }
@media (max-width: 600px) { .bitrix-panel { padding: 12px; } .bitrix-overlay { padding: 6px; } .bitrix-dialog { max-height: calc(100dvh - 12px); } .dialog-body { padding: 10px; } }
</style>
