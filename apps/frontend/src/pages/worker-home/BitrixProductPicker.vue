<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import type { BitrixItem } from "@/shared/api/bitrix";

const props = defineProps<{ items: BitrixItem[]; productId: number; disabled?: boolean }>();
const emit = defineEmits<{ select: [id: number] }>();
const query = ref("");
const opened = ref(false);
const highlighted = ref(0);
const root = ref<HTMLElement | null>(null);
const list = ref<HTMLElement | null>(null);
const listId = computed(() => `bitrix-options-${props.productId}`);
const matches = computed(() => {
  const text = query.value.trim().toLocaleLowerCase();
  return props.items.filter(item => !text || `${item.id} ${item.name}`.toLocaleLowerCase().includes(text));
});
const activeId = computed(() => opened.value && matches.value[highlighted.value]
  ? `${listId.value}-${matches.value[highlighted.value].id}` : undefined);
watch(matches, () => { highlighted.value = 0; });
watch(() => props.disabled, disabled => { if (disabled) opened.value = false; });

function open() { if (!props.disabled) opened.value = true; }
function search() { highlighted.value = 0; open(); }
function choose(item: BitrixItem) {
  if (props.disabled) return;
  emit("select", item.id);
  query.value = "";
  opened.value = false;
  highlighted.value = 0;
}
function outside(event: PointerEvent) {
  if (!root.value?.contains(event.target as Node)) opened.value = false;
}
function blur(event: FocusEvent) {
  if (!root.value?.contains(event.relatedTarget as Node | null)) opened.value = false;
}
async function keydown(event: KeyboardEvent) {
  if (event.isComposing || props.disabled) return;
  if (event.key === "Escape") {
    if (opened.value) { event.preventDefault(); event.stopPropagation(); opened.value = false; }
    return;
  }
  if (event.key === "Enter") {
    if (opened.value) {
      event.preventDefault();
      const item = matches.value[highlighted.value];
      if (item) choose(item);
    }
    return;
  }
  if (event.key !== "ArrowDown" && event.key !== "ArrowUp") return;
  event.preventDefault();
  if (!opened.value) {
    opened.value = true;
    highlighted.value = event.key === "ArrowDown" ? 0 : Math.max(0, matches.value.length - 1);
  } else {
    highlighted.value = Math.max(0, Math.min(matches.value.length - 1, highlighted.value + (event.key === "ArrowDown" ? 1 : -1)));
  }
  await nextTick();
  list.value?.querySelector('[aria-selected="true"]')?.scrollIntoView({ block: "nearest" });
}
onMounted(() => document.addEventListener("pointerdown", outside));
onBeforeUnmount(() => document.removeEventListener("pointerdown", outside));
</script>

<template>
  <div ref="root" class="bitrix-picker" @focusout="blur">
    <input v-model="query" type="text" role="combobox" aria-autocomplete="list" aria-haspopup="listbox"
      :aria-label="`Найти и добавить товар Bitrix для изделия ${productId}`" :aria-expanded="opened"
      :aria-controls="listId" :aria-activedescendant="activeId" :disabled="disabled" autocomplete="off"
      placeholder="Найти и добавить товар Bitrix…" @focus="open" @click="open" @input="search" @keydown="keydown">
    <div v-if="opened" class="results">
      <div :id="listId" ref="list" class="options" role="listbox" aria-label="Товары Bitrix">
        <button v-for="(item, index) in matches" :id="`${listId}-${item.id}`" :key="item.id" type="button"
          role="option" tabindex="-1" :aria-selected="highlighted === index" :class="{ highlighted: highlighted === index }"
          @pointerdown.prevent @click="choose(item)">
          <span>{{ item.id }} · {{ item.name }}</span>
          <small v-if="item.parent_id || !item.active">{{ item.parent_id ? `Вариация товара ${item.parent_id}` : '' }}{{ item.active ? '' : ' · Неактивен' }}</small>
        </button>
      </div>
      <p v-if="!matches.length" role="status">Подходящих товаров нет</p>
      <p v-else class="hint">Найдено: {{ matches.length }} · ↑ ↓ — выбор, Enter — добавить</p>
    </div>
  </div>
</template>

<style scoped>
.bitrix-picker { margin-top: 8px; min-width: 0; }
input { box-sizing: border-box; width: 100%; font: inherit; color: inherit; padding: 9px 11px; border: 1px solid #ccd6e1; border-radius: 8px; background: #fff; }
input:focus { outline: 2px solid #3476a8; outline-offset: 1px; }
input:disabled { opacity: .5; }
.results { margin-top: 5px; border: 1px solid #ccd6e1; border-radius: 8px; overflow: hidden; background: #fff; }
.options { max-height: 220px; overflow-y: auto; overscroll-behavior: contain; }
button { display: block; width: 100%; text-align: left; border: 0; border-bottom: 1px solid #edf0f4; padding: 9px 11px; font: inherit; color: inherit; background: #fff; cursor: pointer; overflow-wrap: anywhere; }
button:hover, button.highlighted { background: #edf5fc; }
small { display: block; color: #68788a; margin-top: 3px; }
p { margin: 0; padding: 8px 11px; color: #68788a; font-size: .8rem; }
.hint { border-top: 1px solid #edf0f4; }
</style>
