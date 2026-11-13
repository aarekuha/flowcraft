<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import BitrixProductPicker from "./BitrixProductPicker.vue";
import { saveBitrixMapping, saveBitrixMappingRequirement } from "@/shared/api/bitrix";

import { mappingCatalog as catalog, refreshMappingCatalog } from "./bitrixMappingCatalog";

const props = defineProps<{ productId: number }>();
const loading = ref(true);
const saving = ref(false);
const error = ref("");
const product = computed(() => catalog.value.products.find(item => item.id === props.productId));
const options = computed(() => catalog.value.items.filter(item => item.present
  && !product.value?.bitrix_ids.includes(item.id)
  && (item.mapped_product_id === null || item.mapped_product_id === props.productId)));
function name(id: number) { return catalog.value.items.find(item => item.id === id)?.name ?? "Товар отсутствует в каталоге"; }
async function load() {
  await refreshMappingCatalog();
}
async function change(ids: number[]) {
  if (saving.value) return;
  saving.value = true; error.value = "";
  try { await saveBitrixMapping(props.productId, ids); await load(); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "Не удалось сохранить сопоставления"; }
  finally { saving.value = false; }
}
async function toggleRequirement() {
  if (!product.value || saving.value) return;
  saving.value = true; error.value = "";
  try { await saveBitrixMappingRequirement(props.productId, !product.value.mapping_not_required); await load(); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "Не удалось сохранить статус"; }
  finally { saving.value = false; }
}
onMounted(async () => {
  try { await load(); }
  catch (cause) { error.value = cause instanceof Error ? cause.message : "Не удалось загрузить каталог"; }
  finally { loading.value = false; }
});
</script>

<template>
  <section class="product-bitrix">
    <p v-if="error" role="alert" class="error">{{ error }}</p>
    <p v-if="loading">Загрузка каталога…</p>
    <template v-else-if="product">
      <div v-for="id in product.bitrix_ids" :key="id" class="mapping-row">
        <span>{{ id }} · {{ name(id) }}</span>
        <button class="fc-button" type="button" :disabled="saving" @click="change(product.bitrix_ids.filter(value => value !== id))">Убрать</button>
      </div>
      <p v-if="product.mapping_not_required">Не требует сопоставления</p>
      <BitrixProductPicker v-else :items="options" :product-id="productId" :disabled="saving" @select="change([...product.bitrix_ids, $event])" />
      <button class="fc-button" type="button" :disabled="saving || product.bitrix_ids.length > 0" @click="toggleRequirement">{{ product.mapping_not_required ? 'Требует сопоставления' : 'Не требует сопоставления' }}</button>
      <span v-if="saving" role="status">Сохранение…</span>
    </template>
    <p v-else-if="!error">Сопоставление доступно для активных изделий.</p>
  </section>
</template>

<style scoped>
.product-bitrix { min-width: 260px; max-width: 420px; }
h3 { margin: 0 0 10px; font-size: 1rem; }
.hint { color: #68788a; font-size: .85rem; }
.mapping-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 5px 0; }
button { font: inherit; padding: 8px 10px; border: 1px solid #ccd6e1; border-radius: 8px; background: white; cursor: pointer; margin-top: 8px; }
button:disabled { opacity: .5; cursor: default; }
.error { color: #b13030; }
</style>
