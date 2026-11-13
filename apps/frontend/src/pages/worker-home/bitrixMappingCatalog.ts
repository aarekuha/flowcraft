import { ref } from "vue";
import { fetchBitrixCatalog, type BitrixCatalog } from "@/shared/api/bitrix";

export const mappingCatalog = ref<BitrixCatalog>({ items: [], products: [], metadata: {} });
let pending: Promise<void> | null = null;

export function refreshMappingCatalog(): Promise<void> {
  if (!pending) {
    pending = fetchBitrixCatalog().then(data => { mappingCatalog.value = data; }).finally(() => { pending = null; });
  }
  return pending;
}
