<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from "vue";
import QRCode from "qrcode";
import type { IScannerControls } from "@zxing/browser";
import { useRoute, useRouter } from "vue-router";
import flowcraftLogoUrl from "@/shared/assets/flowcraft_logo.png";
import ReportsPanel from "@/pages/worker-home/ReportsPanel.vue";

import {
  changePassword,
  fetchCurrentSession,
  login,
  logout,
  setupPassword,
  type AuthSession,
} from "@/shared/api/auth";
import {
  createLeatherType,
  fetchAllLeatherTypes,
  fetchLeatherTypes,
  updateLeatherTypeStatus,
  type LeatherTypeListParams,
  type LeatherTypeRecord,
  type LeatherTypeSortDirection,
} from "@/shared/api/leatherTypes";
import {
  createOperationCatalogEntry,
  fetchAllOperationCatalogEntries,
  fetchOperationCatalog,
  updateOperationCatalogEntryStatus,
  type OperationCatalogEntry,
  type OperationCatalogListParams,
  type OperationCatalogSortDirection,
} from "@/shared/api/operationCatalog";
import {
  acceptWorkOrderQualityControl,
  createWorkOrder,
  fetchAllWorkOrders,
  fetchWorkOrder,
  fetchWorkOrderTimeBreakdown,
  fetchWorkOrders,
  fetchWorkerAssignedWorkOrders,
  updateWorkOrderAssignments,
  updateWorkOrderDeletedStatus,
  updateWorkOrderPlannedCompletionDate,
  updateWorkOrderQualityControlStatus,
  updateWorkOrderStatus,
  updateWorkOrderTakenStatus,
  updateWorkerAssignmentStatus,
  type WorkOrderListParams,
  type WorkOrderSortBy,
  type WorkOrderSortDirection,
  type WorkOrderStatusFilter,
  type WorkOrderDetail,
  type WorkOrderSummary,
  type WorkOrderTimeBreakdown,
  type WorkerAssignmentStatus,
} from "@/shared/api/orders";
import {
  createProduct,
  deleteProduct,
  fetchProduct,
  fetchProducts,
  updateProductCosts,
  updateProductStatus,
  type OperationNode,
  type ProductCreatePayload,
  type ProductDetail,
  type ProductSummary,
} from "@/shared/api/products";
import {
  downloadStatisticsExport,
  fetchStatisticsOverview,
  type StatisticsDailyItem,
  type StatisticsOperationItem,
  type StatisticsOrderItem,
  type StatisticsOverview,
  type StatisticsPeriodParams,
  type StatisticsWorkerItem,
} from "@/shared/api/statistics";
import {
  endWorkerDay as endWorkerDayApi,
  fetchWorkerTimerState,
  startWorkerDay as startWorkerDayApi,
  switchWorkerTimer,
  type TimerType,
  type WorkerTimerApiState,
} from "@/shared/api/timers";
import {
  createUser as createUserApi,
  deleteUser as deleteUserApi,
  fetchUsers,
  resetUserPassword as resetUserPasswordApi,
  updateUser as updateUserApi,
  type UserRecord,
  type UserRole,
} from "@/shared/api/users";

type TabId = "worker" | "brigadier" | "constructor" | "stats" | "reports" | "users";
type ModalMode = "create" | "copy" | "view" | null;
type WorkOrderStatusTabId = Exclude<WorkOrderStatusFilter, "all">;
type BrigadierTabId = "orders" | WorkOrderStatusTabId;
type ConstructorTabId = "products" | "directories";
type ConstructorDirectoryTabId = "operation-catalog" | "leather-types";
type ProductVisibilityFilter = "all" | "active" | "inactive";
type ProductSort =
  | "created-desc"
  | "created-asc"
  | "name-asc"
  | "name-desc"
  | "version-asc"
  | "version-desc";
type StatisticsPeriodMode = "preset" | "custom";
type WorkOrderSort = `${WorkOrderSortBy}-${WorkOrderSortDirection}`;
type WorkOrderActionConfirmKind =
  | "send_to_quality_control"
  | "return_to_created"
  | "return_to_work"
  | "return_to_quality_control"
  | "delete"
  | "restore";
type UserSort = "created-desc" | "created-asc" | "name-asc" | "name-desc";

type FlatOperationNodeRow = {
  id: number;
  operationCatalogEntryId: number | null;
  name: string;
  priceCents: number | null;
  standardTimeSeconds: number | null;
  level: number;
  isGroup: boolean;
  canMoveUp: boolean;
  canMoveDown: boolean;
  canIndent: boolean;
  canOutdent: boolean;
};

type BrigadierOrderAssignment = {
  operationId: number;
  operationLabel: string;
  workerUserId: number | null;
  workerName: string;
};

type WorkerTimerKind = "preparation" | "break" | "idle" | "operation";

type WorkerTimerDefinition = {
  id: string;
  label: string;
  kind: WorkerTimerKind;
  assignmentId?: number;
  assignmentStatus?: WorkerAssignmentStatus;
  orderGroupKey?: string;
  productLabel?: string;
  productQuantity?: number;
  leatherTypeName?: string | null;
  orderNumber?: string;
};

type WorkerTimerState = WorkerTimerDefinition & {
  elapsedMs: number;
  startedAtMs: number | null;
};

type WorkerTimerGroup = {
  groupKey: string;
  orderNumber: string;
  productLabel: string;
  leatherTypeName: string | null;
  quantity: number;
  timers: WorkerTimerDefinition[];
};

type WorkerAssignmentStatusConfirm = {
  timer: WorkerTimerDefinition;
  status: Exclude<WorkerAssignmentStatus, "in_work">;
};

const tabs: Array<{ id: TabId; label: string; icon: string }> = [
  { id: "worker", label: "Исполнитель", icon: "worker" },
  { id: "brigadier", label: "Бригадир", icon: "brigadier" },
  { id: "constructor", label: "Конструктор", icon: "constructor" },
  { id: "stats", label: "Статистика", icon: "stats" },
  { id: "reports", label: "Отчеты", icon: "stats" },
  { id: "users", label: "Пользователи", icon: "users" },
];

const tabRoles: Record<TabId, UserRole[]> = {
  worker: ["worker"],
  brigadier: ["brigadier", "quality_control"],
  constructor: ["constructor"],
  stats: ["brigadier", "admin"],
  reports: ["reports"],
  users: ["admin"],
};

const visibilityOptions: Array<{
  value: ProductVisibilityFilter;
  label: string;
  icon: string;
}> = [
  { value: "all", label: "Все изделия", icon: "all" },
  { value: "active", label: "Только активные", icon: "active" },
  { value: "inactive", label: "Только деактивированные", icon: "inactive" },
];

const workerAssignmentStatusOptions: Array<{
  value: WorkerAssignmentStatus;
  label: string;
}> = [
  { value: "in_work", label: "В работе" },
  { value: "hidden", label: "Скрытые" },
  { value: "completed", label: "Выполненные" },
];

const sortOptions: Array<{
  field: "name" | "version" | "created";
  label: string;
  icon: string;
}> = [
  { field: "name", label: "Сортировка по имени", icon: "name" },
  { field: "version", label: "Сортировка по версии", icon: "version" },
  { field: "created", label: "Сортировка по дате создания", icon: "created" },
];

const userRoleOptions: Array<{
  value: UserRole;
  label: string;
  icon: string;
}> = [
  { value: "worker", label: "Исполнитель", icon: "worker" },
  { value: "brigadier", label: "Бригадир", icon: "brigadier" },
  { value: "constructor", label: "Конструктор", icon: "constructor" },
  { value: "quality_control", label: "ОТК", icon: "quality-control" },
  { value: "reports", label: "Отчеты", icon: "stats" },
  { value: "admin", label: "Администратор", icon: "admin" },
];

const userSortOptions: Array<{
  field: "name" | "created";
  label: string;
  icon: string;
}> = [
  { field: "name", label: "Сортировка пользователей по имени", icon: "name" },
  { field: "created", label: "Сортировка пользователей по дате создания", icon: "created" },
];

const workOrderStatusTabs: Array<{
  id: WorkOrderStatusTabId;
  label: string;
  icon: string;
}> = [
  { id: "created", label: "Созданные", icon: "orders" },
  { id: "in_work", label: "В работе", icon: "in-work" },
  { id: "quality_control", label: "ОТК", icon: "search" },
  { id: "completed", label: "Выполненные", icon: "check" },
  { id: "deleted", label: "Удаленные", icon: "delete" },
];

const statisticsPeriodOptions = [7, 14, 30] as const;

const ACTIVE_TAB_STORAGE_KEY = "flowcraft.active-tab";
const BRIGADIER_TAB_STORAGE_KEY = "flowcraft.brigadier-tab";
const CONSTRUCTOR_TAB_STORAGE_KEY = "flowcraft.constructor-tab";
const CONSTRUCTOR_DIRECTORY_TAB_STORAGE_KEY = "flowcraft.constructor-directory-tab";
const PREPARATION_TIMER_ID = "worker:preparation";
const BREAK_TIMER_ID = "worker:break";
const IDLE_TIMER_ID = "worker:idle";
const PRINT_QR_CODE_COUNT = 5;
const SMARTPHONE_MEDIA_QUERY = "(max-width: 760px)";
const PROJECT_PAGE_SIZE = 10;
const WORK_ORDER_PAGE_SIZE = PROJECT_PAGE_SIZE;
const LEATHER_TYPE_PAGE_SIZE = PROJECT_PAGE_SIZE;
const OPERATION_CATALOG_PAGE_SIZE = PROJECT_PAGE_SIZE;

const route = useRoute();
const router = useRouter();

const activeTab = ref<TabId>(readStoredTab<TabId>(ACTIVE_TAB_STORAGE_KEY, tabs.map((tab) => tab.id), "constructor"));
const brigadierTab = ref<BrigadierTabId>(
  readStoredTab<BrigadierTabId>(
    BRIGADIER_TAB_STORAGE_KEY,
    ["orders", ...workOrderStatusTabs.map((tab) => tab.id)],
    "orders",
  ),
);
const constructorTab = ref<ConstructorTabId>(
  readStoredTab<ConstructorTabId>(
    CONSTRUCTOR_TAB_STORAGE_KEY,
    ["products", "directories"],
    "products",
  ),
);
const constructorDirectoryTab = ref<ConstructorDirectoryTabId>(
  readStoredTab<ConstructorDirectoryTabId>(
    CONSTRUCTOR_DIRECTORY_TAB_STORAGE_KEY,
    ["operation-catalog", "leather-types"],
    "operation-catalog",
  ),
);
const modalMode = ref<ModalMode>(null);
const modalProductId = ref<number | null>(null);
const currentSession = ref<AuthSession | null>(null);
const products = ref<ProductSummary[]>([]);
const busyProductIds = ref<number[]>([]);
const users = ref<UserRecord[]>([]);
const workOrders = ref<WorkOrderSummary[]>([]);
const busyWorkOrderIds = ref<number[]>([]);
const busyPrintWorkOrderIds = ref<number[]>([]);
const workOrdersTotal = ref(0);
const workOrdersPage = ref(1);
const workOrdersPages = ref(1);
const leatherTypes = ref<LeatherTypeRecord[]>([]);
const activeLeatherTypes = ref<LeatherTypeRecord[]>([]);
const busyLeatherTypeIds = ref<number[]>([]);
const leatherTypesTotal = ref(0);
const leatherTypesPage = ref(1);
const leatherTypesPages = ref(1);
const operationCatalogEntries = ref<OperationCatalogEntry[]>([]);
const activeOperationCatalogEntries = ref<OperationCatalogEntry[]>([]);
const busyOperationCatalogEntryIds = ref<number[]>([]);
const operationCatalogTotal = ref(0);
const operationCatalogPage = ref(1);
const operationCatalogPages = ref(1);

const productFilter = ref("");
const productVisibility = ref<ProductVisibilityFilter>("all");
const productSort = ref<ProductSort>("name-asc");
const workOrderFilter = ref("");
const workOrderSearchDraft = ref("");
const workOrderSort = ref<WorkOrderSort>("created-desc");
const leatherTypeFilter = ref("");
const leatherTypeSearchDraft = ref("");
const showInactiveLeatherTypes = ref(false);
const leatherTypeSortDirection = ref<LeatherTypeSortDirection>("asc");
const leatherTypeName = ref("");
const operationCatalogFilter = ref("");
const operationCatalogSearchDraft = ref("");
const showInactiveOperationCatalogEntries = ref(false);
const operationCatalogSortDirection = ref<OperationCatalogSortDirection>("asc");
const operationCatalogName = ref("");
const brigadierProductFilter = ref("");
const brigadierProductSort = ref<ProductSort>("name-asc");
const userFilter = ref("");
const userVisibility = ref<ProductVisibilityFilter>("all");
const userSort = ref<UserSort>("name-asc");
const productName = ref("");
const productVersion = ref("");
const productMaterialCostCents = ref<number | null>(null);
const operationTree = ref<OperationNode[]>([]);
const operationStandardTimeInputErrors = ref<Record<number, string>>({});
const productPendingDelete = ref<ProductSummary | null>(null);
const userPendingDelete = ref<UserRecord | null>(null);
const editingUserId = ref<number | null>(null);
const editingUserDraft = ref<UserRecord | null>(null);
const brigadierModalMode = ref<"create" | "manage" | "quality_control" | null>(null);
const brigadierModalProduct = ref<ProductDetail | null>(null);
const brigadierModalOrderId = ref<number | null>(null);
const brigadierModalAssignments = ref<BrigadierOrderAssignment[]>([]);
const brigadierModalQuantity = ref("1");
const brigadierModalPlannedCompletionDate = ref("");
const brigadierModalDefectQuantity = ref("0");
const brigadierModalOrderNumber = ref("");
const brigadierModalLeatherTypeId = ref("");
const brigadierModalLeatherTypeNameDraft = ref("");
const brigadierModalHasSpentTime = ref(false);
const brigadierOpenAssignmentDropdownId = ref<number | null>(null);
let brigadierDropdownCloseTimeoutId: number | null = null;
const isBrigadierLeatherTypeDropdownOpen = ref(false);
let brigadierLeatherTypeDropdownCloseTimeoutId: number | null = null;
const brigadierModalLoading = ref(false);
const brigadierModalError = ref("");
const brigadierOrdersLoading = ref(false);
const brigadierOrdersError = ref("");
const brigadierSaveLoading = ref(false);
const isBrigadierSaveConfirmOpen = ref(false);
const workOrderActionConfirm = ref<{
  kind: WorkOrderActionConfirmKind;
  order: WorkOrderSummary;
} | null>(null);
const workOrderTimeBreakdownModal = ref<{
  order: WorkOrderSummary;
  breakdown: WorkOrderTimeBreakdown | null;
} | null>(null);
const workOrderTimeBreakdownLoading = ref(false);
const workOrderTimeBreakdownError = ref("");
const workOrderDetails = ref<WorkOrderDetail[]>([]);
const workerAssignmentsLoading = ref(false);
const workerAssignmentsError = ref("");
const workerAssignmentStatusFilter = ref<WorkerAssignmentStatus>("in_work");
const isWorkerAssignmentStatusDropdownOpen = ref(false);
const workerTimerSubmitting = ref(false);
const workerDayStartedAt = ref<number | null>(null);
const isWorkerDayEndConfirmOpen = ref(false);
const workerAssignmentStatusConfirm = ref<WorkerAssignmentStatusConfirm | null>(null);
const activeWorkerTimerId = ref<string | null>(null);
const workerTimers = ref<Record<string, WorkerTimerState>>({});
const workerTimerNow = ref(Date.now());
const workerGroupExpanded = ref<Record<string, boolean>>({});
const isSmartphoneViewport = ref(false);
const statisticsPeriodMode = ref<StatisticsPeriodMode>("preset");
const statisticsPeriodDays = ref<(typeof statisticsPeriodOptions)[number]>(14);
const statisticsDateFrom = ref(getDateInputValueForDays(14));
const statisticsDateTo = ref(getDateInputValue(Date.now()));
const statisticsLoading = ref(false);
const statisticsExportLoading = ref(false);
const statisticsError = ref("");
const statisticsOverview = ref<StatisticsOverview | null>(null);

const listLoading = ref(false);
const listError = ref("");
const leatherTypesLoading = ref(false);
const leatherTypesError = ref("");
const leatherTypeSaveLoading = ref(false);
const leatherTypeError = ref("");
const operationCatalogLoading = ref(false);
const operationCatalogError = ref("");
const operationCatalogSaveLoading = ref(false);
const operationCatalogSaveError = ref("");
const authInitializing = ref(true);
const authSubmitting = ref(false);
const authError = ref("");
const authPhone = ref("");
const authPassword = ref("");
const authRequiresPasswordSetup = ref(false);
const authSetupUserName = ref("");
const authNewPassword = ref("");
const authConfirmPassword = ref("");
const usersLoading = ref(false);
const usersError = ref("");
const changePasswordModalOpen = ref(false);
const changePasswordCurrent = ref("");
const changePasswordNext = ref("");
const changePasswordConfirm = ref("");
const changePasswordError = ref("");
const changePasswordSaving = ref(false);
const modalLoading = ref(false);
const modalError = ref("");
const saveLoading = ref(false);
const hasAttemptedSubmit = ref(false);

let nextOperationId = 1;
let nextUserId = 100;
let workerClockIntervalId: number | null = null;
let workOrdersRequestId = 0;
let workerAssignmentsRequestId = 0;
let workerAssignmentStatusDropdownCloseTimeoutId: number | null = null;
let leatherTypesRequestId = 0;
let operationCatalogRequestId = 0;
let workOrderTimeBreakdownRequestId = 0;
let operationNameDropdownCloseTimeoutId: number | null = null;
const openOperationNameDropdownId = ref<number | null>(null);
const isModalOpen = computed(() => modalMode.value !== null);
const isBrigadierOrderModalOpen = computed(() => brigadierModalMode.value !== null);
const isBrigadierLeatherTypeEditable = computed(
  () => isBrigadierOrderAttributesEditable.value,
);
const isBrigadierQuantityEditable = computed(
  () => isBrigadierOrderAttributesEditable.value,
);
const isQualityControlOrderModal = computed(
  () => brigadierModalMode.value === "quality_control",
);
const isDeleteModalOpen = computed(() => productPendingDelete.value !== null);
const isUserDeleteModalOpen = computed(() => userPendingDelete.value !== null);
const isViewMode = computed(() => modalMode.value === "view");
const printableWorkOrder = ref<WorkOrderDetail | null>(null);
const printableWorkOrderQrCode = ref("");
const workerOrderFocusMessage = ref("");
const workerQrScannerVideo = ref<HTMLVideoElement | null>(null);
const isWorkerQrScannerOpen = ref(false);
const workerQrScannerStarting = ref(false);
const workerQrScannerError = ref("");
let workerQrScannerControls: IScannerControls | null = null;
let workerQrScannerRunId = 0;
const workOrderStatusTab = computed<WorkOrderStatusTabId>(() =>
  brigadierTab.value === "orders" ? "created" : brigadierTab.value,
);
const availableTabs = computed(() => {
  if (!currentSession.value) {
    return [] as Array<{ id: TabId; label: string; icon: string }>;
  }

  return tabs.filter((tab) =>
    tabRoles[tab.id].some((role) => currentSession.value?.userRoles.includes(role)),
  );
});

const canViewStatistics = computed(
  () =>
    currentSession.value?.userRoles.includes("brigadier") ||
    currentSession.value?.userRoles.includes("admin") ||
    false,
);
const statisticsPeriodValidationError = computed(() => getStatisticsPeriodValidationError());
const canManageWorkOrders = computed(
  () =>
    currentSession.value?.userRoles.includes("brigadier") ||
    currentSession.value?.userRoles.includes("quality_control") ||
    false,
);
const canAcceptQualityControl = computed(
  () => currentSession.value?.userRoles.includes("quality_control") ?? false,
);
const workerOrderRouteId = computed(() => {
  const routeOrderId = route.params.orderId;
  const value = Array.isArray(routeOrderId) ? routeOrderId[0] : routeOrderId;

  if (!value || !/^\d+$/.test(value)) {
    return null;
  }

  const orderId = Number.parseInt(value, 10);
  return orderId > 0 ? orderId : null;
});

const shouldShowValidation = computed(
  () => modalMode.value === "create" || modalMode.value === "copy",
);
const activeOperationCatalogNameByKey = computed(() => {
  const names = new Map<string, string>();
  for (const entry of activeOperationCatalogEntries.value) {
    names.set(normalizeName(entry.name), entry.name);
  }
  return names;
});
const activeOperationCatalogEntryByKey = computed(() => {
  const entries = new Map<string, OperationCatalogEntry>();
  for (const entry of activeOperationCatalogEntries.value) {
    entries.set(normalizeName(entry.name), entry);
  }
  return entries;
});
const activeOperationCatalogEntryById = computed(() => {
  const entries = new Map<number, OperationCatalogEntry>();
  for (const entry of activeOperationCatalogEntries.value) {
    entries.set(entry.id, entry);
  }
  return entries;
});
const operationErrors = computed(() =>
  validateOperationTree(
    operationTree.value,
    operationStandardTimeInputErrors.value,
  ),
);
const hasOperationErrors = computed(
  () => Object.keys(operationErrors.value).length > 0,
);
const firstOperationErrorRow = computed(() =>
  flatOperationRows.value.find((row) => Boolean(operationErrors.value[row.id])),
);

const productNameError = computed(() =>
  productName.value.trim() ? "" : "Укажите наименование изделия.",
);

const productVersionError = computed(() =>
  productVersion.value.trim() ? "" : "Укажите версию изделия.",
);

const productMaterialCostError = computed(() =>
  productMaterialCostCents.value === null || productMaterialCostCents.value >= 0
    ? ""
    : "Стоимость материала не может быть отрицательной.",
);

const productIdentityError = computed(() => {
  const normalizedName = normalizeName(productName.value);
  const normalizedVersion = normalizeName(productVersion.value);

  if (!normalizedName || !normalizedVersion || modalMode.value === "view") {
    return "";
  }

  const duplicate = products.value.some(
    (product) =>
      normalizeName(product.name) === normalizedName &&
      normalizeName(product.version) === normalizedVersion,
  );

  return duplicate ? "Изделие с таким именем и версией уже существует." : "";
});

const operationTreeError = computed(() =>
  operationTree.value.length > 0 ? "" : "Добавьте хотя бы одну операцию.",
);

const canSaveProduct = computed(
  () => {
    if (isViewMode.value) {
      return modalProductId.value !== null && !productMaterialCostError.value;
    }

    return (
      !productNameError.value &&
      !productVersionError.value &&
      !productMaterialCostError.value &&
      !productIdentityError.value &&
      !operationTreeError.value &&
      !hasOperationErrors.value
    );
  },
);

const saveBlockIssue = computed<{
  message: string;
  selector: string;
} | null>(() => {
  if (productIdentityError.value) {
    return {
      message: productIdentityError.value,
      selector: '[data-field="product-version"]',
    };
  }

  if (shouldShowValidation.value && productNameError.value) {
    return {
      message: productNameError.value,
      selector: '[data-field="product-name"]',
    };
  }

  if (shouldShowValidation.value && productVersionError.value) {
    return {
      message: productVersionError.value,
      selector: '[data-field="product-version"]',
    };
  }

  if (productMaterialCostError.value) {
    return {
      message: productMaterialCostError.value,
      selector: '[data-field="product-material-cost"]',
    };
  }

  if (hasOperationErrors.value && firstOperationErrorRow.value) {
    return {
      message: operationErrors.value[firstOperationErrorRow.value.id],
      selector: `[data-operation-id="${firstOperationErrorRow.value.id}"]`,
    };
  }

  if (shouldShowValidation.value && operationTreeError.value) {
    return {
      message: operationTreeError.value,
      selector: '[data-field="add-root-operation"]',
    };
  }

  return null;
});

const modalTitle = computed(() => {
  if (modalMode.value === "copy") {
    return "Копия изделия";
  }

  if (modalMode.value === "view") {
    return "Карточка изделия";
  }

  return "Новое изделие";
});

const modalDescription = computed(() => {
  if (modalMode.value === "copy") {
    return "Форма предзаполнена текущим изделием и его деревом операций.";
  }

  if (modalMode.value === "view") {
    return "Структура изделия, цены и нормы операций доступны для просмотра, стоимость материала можно изменить.";
  }

  return "Заполните карточку изделия и задайте дерево производственных операций.";
});

const flatOperationRows = computed<FlatOperationNodeRow[]>(() =>
  flattenOperations(operationTree.value),
);

const filteredProducts = computed(() => {
  const normalizedFilter = productFilter.value.trim().toLowerCase();

  const filtered = products.value.filter((product) => {
    const matchesName = product.name.toLowerCase().includes(normalizedFilter);
    const matchesVisibility =
      productVisibility.value === "all" ||
      (productVisibility.value === "active" && product.isActive) ||
      (productVisibility.value === "inactive" && !product.isActive);

    return matchesName && matchesVisibility;
  });

  return [...filtered].sort((left, right) =>
    compareProducts(left, right, productSort.value),
  );
});

const filteredUsers = computed(() => {
  const normalizedFilter = userFilter.value.trim().toLowerCase();

  const filtered = users.value.filter((user) => {
    const matchesName = user.name.toLowerCase().includes(normalizedFilter);
    const matchesVisibility =
      userVisibility.value === "all" ||
      (userVisibility.value === "active" && user.isActive) ||
      (userVisibility.value === "inactive" && !user.isActive);

    return matchesName && matchesVisibility;
  });

  return [...filtered].sort((left, right) => compareUsers(left, right, userSort.value));
});

const brigadierWorkerUsers = computed(() =>
  [...users.value]
    .filter((user) => user.roles.includes("worker") && user.isActive)
    .sort((left, right) => left.name.localeCompare(right.name, "ru")),
);

const filteredWorkOrders = computed(() => {
  return workOrders.value;
});

const filteredBrigadierProducts = computed(() => {
  const normalizedFilter = brigadierProductFilter.value.trim().toLowerCase();
  const filtered = products.value.filter(
    (product) =>
      product.isActive &&
      product.name.toLowerCase().includes(normalizedFilter),
  );

  return [...filtered].sort((left, right) =>
    compareProducts(left, right, brigadierProductSort.value),
  );
});

const brigadierCurrentOrder = computed(() =>
  workOrders.value.find((order) => order.id === brigadierModalOrderId.value) ?? null,
);

const isCompletedBrigadierOrderModal = computed(
  () =>
    brigadierModalMode.value === "manage" &&
    brigadierCurrentOrder.value?.completedAtTs !== null &&
    brigadierCurrentOrder.value?.completedAtTs !== undefined,
);

const isQualityControlStageBrigadierOrderModal = computed(
  () =>
    brigadierModalMode.value === "manage" &&
    brigadierCurrentOrder.value?.qualityControlAtTs !== null &&
    brigadierCurrentOrder.value?.qualityControlAtTs !== undefined,
);

const isDeletedBrigadierOrderModal = computed(
  () =>
    brigadierModalMode.value === "manage" &&
    brigadierCurrentOrder.value?.deletedAtTs !== null &&
    brigadierCurrentOrder.value?.deletedAtTs !== undefined,
);

const isBrigadierOrderAttributesEditable = computed(
  () =>
    brigadierModalMode.value === "create" ||
    (brigadierModalMode.value === "manage" &&
      !isDeletedBrigadierOrderModal.value &&
      !isCompletedBrigadierOrderModal.value &&
      !isQualityControlStageBrigadierOrderModal.value &&
      !brigadierModalHasSpentTime.value),
);

const isBrigadierAssignmentsEditable = computed(
  () =>
    !isQualityControlOrderModal.value &&
    (brigadierModalMode.value === "create" ||
      (brigadierModalMode.value === "manage" &&
        !isDeletedBrigadierOrderModal.value &&
        !isCompletedBrigadierOrderModal.value &&
        !isQualityControlStageBrigadierOrderModal.value)),
);

const isBrigadierPlannedCompletionDateChanged = computed(
  () =>
    brigadierModalMode.value !== "create" &&
    brigadierModalPlannedCompletionDate.value !==
      (brigadierCurrentOrder.value?.plannedCompletionDate ?? ""),
);

const isBrigadierSaveAvailable = computed(
  () =>
    brigadierModalMode.value === "create" ||
    isQualityControlOrderModal.value ||
    isBrigadierOrderAttributesEditable.value ||
    isBrigadierAssignmentsEditable.value ||
    isBrigadierPlannedCompletionDateChanged.value,
);

const brigadierModalLeatherTypeName = computed(() => {
  const leatherTypeId = Number.parseInt(brigadierModalLeatherTypeId.value, 10);
  if (!Number.isInteger(leatherTypeId)) {
    return null;
  }

  return activeLeatherTypes.value.find((item) => item.id === leatherTypeId)?.name ?? null;
});

const workOrdersPageStart = computed(() =>
  workOrdersTotal.value === 0
    ? 0
    : (workOrdersPage.value - 1) * WORK_ORDER_PAGE_SIZE + 1,
);

const workOrdersPageEnd = computed(() =>
  Math.min(workOrdersPage.value * WORK_ORDER_PAGE_SIZE, workOrdersTotal.value),
);

const leatherTypesPageStart = computed(() =>
  leatherTypesTotal.value === 0
    ? 0
    : (leatherTypesPage.value - 1) * LEATHER_TYPE_PAGE_SIZE + 1,
);

const leatherTypesPageEnd = computed(() =>
  Math.min(leatherTypesPage.value * LEATHER_TYPE_PAGE_SIZE, leatherTypesTotal.value),
);

const leatherTypeNameError = computed(() =>
  leatherTypeName.value.trim() ? "" : "Укажите наименование вида кожи.",
);
const operationCatalogNameError = computed(() =>
  operationCatalogName.value.trim() ? "" : "Укажите наименование операции.",
);
const operationCatalogPageStart = computed(() =>
  operationCatalogTotal.value === 0
    ? 0
    : (operationCatalogPage.value - 1) * OPERATION_CATALOG_PAGE_SIZE + 1,
);
const operationCatalogPageEnd = computed(() =>
  Math.min(
    operationCatalogPage.value * OPERATION_CATALOG_PAGE_SIZE,
    operationCatalogTotal.value,
  ),
);

const brigadierModalTitle = computed(() =>
  brigadierModalMode.value === "create" ? "Новый заказ" : "Управление заказом",
);

const brigadierModalDescription = computed(() =>
  brigadierModalMode.value === "quality_control"
    ? "Проверьте заказ, укажите количество брака и при необходимости скорректируйте плановую дату."
    : isDeletedBrigadierOrderModal.value
    ? "В удаленном заказе можно изменить плановую дату сдачи."
    : isCompletedBrigadierOrderModal.value
    ? "В выполненном заказе можно изменить плановую дату сдачи."
    : isQualityControlStageBrigadierOrderModal.value
    ? "На стадии ОТК можно изменить плановую дату, назначения доступны для просмотра."
    : brigadierModalHasSpentTime.value
    ? "По заказу уже есть трудозатраты: можно изменить плановую дату и исполнителей до передачи в ОТК, вид кожи и количество заблокированы."
    : brigadierModalMode.value === "manage"
    ? "Можно изменить плановую дату, вид кожи, количество изделий и назначенных исполнителей до передачи в ОТК."
    : "Укажите плановую дату, количество изделий и распределите исполнителей по операциям.",
);

const brigadierModalSaveLabel = computed(() =>
  brigadierModalMode.value === "quality_control"
    ? "Заказ выполнен"
    : brigadierModalMode.value === "manage"
      ? "Сохранить изменения"
      : "Сохранить заказ",
);

const brigadierSaveConfirmTitle = computed(() =>
  brigadierModalMode.value === "quality_control"
    ? "Принять заказ после ОТК?"
    : brigadierModalMode.value === "manage"
      ? "Сохранить изменения заказа?"
      : "Создать заказ?",
);

const brigadierSaveConfirmDescription = computed(() =>
  brigadierModalMode.value === "quality_control"
    ? "Будут сохранены плановая дата и количество брака, затем установлено время проведения ОТК."
    : brigadierModalMode.value === "manage"
    ? "Назначения исполнителей будут обновлены в заказе."
    : "Заказ будет создан и появится во вкладке созданных заказов.",
);

const workOrderActionConfirmTitle = computed(() => {
  switch (workOrderActionConfirm.value?.kind) {
    case "send_to_quality_control":
      return "Передать заказ в ОТК?";
    case "return_to_created":
      return "Вернуть заказ в созданные?";
    case "return_to_work":
      return "Вернуть заказ в работу?";
    case "return_to_quality_control":
      return "Вернуть заказ на ОТК?";
    case "delete":
      return "Удалить заказ?";
    case "restore":
      return "Восстановить заказ?";
    default:
      return "Подтвердить действие?";
  }
});

const workOrderActionConfirmDescription = computed(() => {
  switch (workOrderActionConfirm.value?.kind) {
    case "send_to_quality_control":
      return "Будет установлена дата передачи в ОТК. Заказ исчезнет из таймеров исполнителей.";
    case "return_to_created":
      return "Время взятия в работу, ОТК и время проведения ОТК будут очищены. Заказ исчезнет из таймеров исполнителей.";
    case "return_to_work":
      return "Дата передачи в ОТК и количество брака будут очищены, заказ снова появится в работе.";
    case "return_to_quality_control":
      return "Время проведения ОТК будет очищено, заказ вернется во вкладку ОТК.";
    case "delete":
      return "Заказ будет перенесен во вкладку удаленных. Его можно будет восстановить позже.";
    case "restore":
      return "Заказ будет восстановлен в состояние, соответствующее его сохраненным датам.";
    default:
      return "";
  }
});

const workOrderActionConfirmLabel = computed(() => {
  switch (workOrderActionConfirm.value?.kind) {
    case "send_to_quality_control":
      return "Передать в ОТК";
    case "return_to_created":
      return "Вернуть в созданные";
    case "return_to_work":
      return "Вернуть в работу";
    case "return_to_quality_control":
      return "Вернуть на ОТК";
    case "delete":
      return "Удалить";
    case "restore":
      return "Восстановить";
    default:
      return "Подтвердить";
  }
});

const workOrderActionConfirmIcon = computed(() => {
  switch (workOrderActionConfirm.value?.kind) {
    case "send_to_quality_control":
      return "button-icon--check";
    case "return_to_created":
    case "restore":
      return "button-icon--refresh";
    case "return_to_work":
      return "button-icon--in-work";
    case "return_to_quality_control":
      return "button-icon--check";
    case "delete":
      return "button-icon--delete";
    default:
      return "button-icon--check";
  }
});

const isWorkOrderActionConfirmDanger = computed(
  () => workOrderActionConfirm.value?.kind === "delete",
);

const isWorkerAssignmentStatusConfirmActiveTimer = computed(() => {
  const pendingAction = workerAssignmentStatusConfirm.value;
  return pendingAction ? activeWorkerTimerId.value === pendingAction.timer.id : false;
});

const workerAssignmentStatusConfirmTitle = computed(() => {
  switch (workerAssignmentStatusConfirm.value?.status) {
    case "hidden":
      return "Скрыть операцию?";
    case "completed":
      return "Отметить операцию выполненной?";
    default:
      return "Подтвердить действие?";
  }
});

const workerAssignmentStatusConfirmDescription = computed(() => {
  const timerNotice = isWorkerAssignmentStatusConfirmActiveTimer.value
    ? " Сейчас по этой операции запущен таймер, после подтверждения он переключится на «Перерыв»."
    : "";

  switch (workerAssignmentStatusConfirm.value?.status) {
    case "hidden":
      return `Операция будет перенесена в скрытые.${timerNotice}`;
    case "completed":
      return `Операция будет перенесена в выполненные.${timerNotice}`;
    default:
      return "";
  }
});

const workerAssignmentStatusConfirmLabel = computed(() => {
  switch (workerAssignmentStatusConfirm.value?.status) {
    case "hidden":
      return "Скрыть";
    case "completed":
      return "Выполнено";
    default:
      return "Подтвердить";
  }
});

const workerAssignmentStatusConfirmIcon = computed(() =>
  workerAssignmentStatusConfirm.value?.status === "hidden"
    ? "button-icon--delete"
    : "button-icon--check",
);

const brigadierOrderNumberError = computed(() => {
  const normalizedOrderNumber = brigadierModalOrderNumber.value.trim();

  if (!normalizedOrderNumber) {
    return "Укажите номер заказа.";
  }

  const duplicate = workOrders.value.some(
    (order) =>
      order.id !== brigadierModalOrderId.value &&
      normalizeName(order.orderNumber) === normalizeName(normalizedOrderNumber),
  );

  return duplicate ? "Заказ с таким номером уже существует." : "";
});

const brigadierQuantityError = computed(() => {
  const quantity = Number.parseInt(brigadierModalQuantity.value, 10);

  return Number.isInteger(quantity) && quantity > 0
    ? ""
    : "Укажите количество изделий больше нуля.";
});

const brigadierPlannedCompletionDateError = computed(() =>
  !brigadierModalPlannedCompletionDate.value &&
  (brigadierModalMode.value === "create" ||
    Boolean(brigadierCurrentOrder.value?.plannedCompletionDate))
    ? "Укажите плановую дату сдачи заказа."
    : "",
);

const brigadierLeatherTypeError = computed(() =>
  brigadierModalLeatherTypeNameDraft.value.trim() && !brigadierModalLeatherTypeId.value
    ? "Выберите вид кожи из списка."
    : "",
);

const brigadierDefectQuantityError = computed(() => {
  if (!isQualityControlOrderModal.value) {
    return "";
  }

  const defectQuantity = Number.parseInt(brigadierModalDefectQuantity.value, 10);
  const orderQuantity = Number.parseInt(brigadierModalQuantity.value, 10);

  if (!Number.isInteger(defectQuantity) || defectQuantity < 0) {
    return "Укажите количество брака целым числом от 0.";
  }

  if (Number.isInteger(orderQuantity) && defectQuantity > orderQuantity) {
    return "Количество брака не может превышать количество изделий в заказе.";
  }

  return "";
});

const firstBrigadierAssignmentError = computed(() =>
  brigadierModalAssignments.value.find((assignment) =>
    Boolean(getBrigadierAssignmentError(assignment)),
  ) ?? null,
);

const brigadierSaveIssue = computed<{
  message: string;
  selector: string;
} | null>(() => {
  if (!isBrigadierSaveAvailable.value) {
    return null;
  }

  if (isQualityControlOrderModal.value) {
    return brigadierDefectQuantityError.value
      ? {
          message: brigadierDefectQuantityError.value,
          selector: '[data-field="brigadier-defect-quantity"]',
        }
      : null;
  }

  if (brigadierOrderNumberError.value) {
    return {
      message: brigadierOrderNumberError.value,
      selector: '[data-field="brigadier-order-number"]',
    };
  }

  if (brigadierQuantityError.value) {
    return {
      message: brigadierQuantityError.value,
      selector: '[data-field="brigadier-quantity"]',
    };
  }

  if (brigadierPlannedCompletionDateError.value) {
    return {
      message: brigadierPlannedCompletionDateError.value,
      selector: '[data-field="brigadier-planned-completion-date"]',
    };
  }

  if (brigadierLeatherTypeError.value) {
    return {
      message: brigadierLeatherTypeError.value,
      selector: '[data-field="brigadier-leather-type"]',
    };
  }

  if (brigadierDefectQuantityError.value) {
    return {
      message: brigadierDefectQuantityError.value,
      selector: '[data-field="brigadier-defect-quantity"]',
    };
  }

  if (firstBrigadierAssignmentError.value) {
    return {
      message: getBrigadierAssignmentError(firstBrigadierAssignmentError.value),
      selector: `[data-brigadier-operation-id="${firstBrigadierAssignmentError.value.operationId}"]`,
    };
  }

  return null;
});

const brigadierModalCanSave = computed(() => {
  if (!isBrigadierSaveAvailable.value) {
    return false;
  }

  if (isQualityControlOrderModal.value) {
    return (
      Boolean(brigadierModalProduct.value) &&
      brigadierModalOrderId.value !== null &&
      !brigadierDefectQuantityError.value &&
      !brigadierPlannedCompletionDateError.value
    );
  }

  if (
    brigadierModalMode.value === "manage" &&
    !isBrigadierOrderAttributesEditable.value &&
    !isBrigadierAssignmentsEditable.value
  ) {
    return (
      Boolean(brigadierModalProduct.value) &&
      Boolean(brigadierModalPlannedCompletionDate.value) &&
      isBrigadierPlannedCompletionDateChanged.value
    );
  }

  return (
    Boolean(brigadierModalProduct.value) &&
    !brigadierOrderNumberError.value &&
    !brigadierQuantityError.value &&
    !brigadierPlannedCompletionDateError.value &&
    !brigadierLeatherTypeError.value &&
    brigadierModalAssignments.value.length > 0 &&
    !firstBrigadierAssignmentError.value
  );
});

const currentWorker = computed(() => {
  if (!currentSession.value || !currentSession.value.userRoles.includes("worker")) {
    return null;
  }

  return users.value.find((user) => user.id === currentSession.value?.userId && user.isActive) ?? null;
});

const staticWorkerTimerDefinitions = computed<WorkerTimerDefinition[]>(() => [
  {
    id: PREPARATION_TIMER_ID,
    label: "Подготовка",
    kind: "preparation",
  },
  {
    id: BREAK_TIMER_ID,
    label: "Перерыв",
    kind: "break",
  },
  {
    id: IDLE_TIMER_ID,
    label: "Простой",
    kind: "idle",
  },
]);

const assignedWorkerTimerDefinitions = computed<WorkerTimerDefinition[]>(() => {
  if (!currentWorker.value) {
    return [];
  }

  return workOrderDetails.value.flatMap((order) =>
    order.assignments
      .filter((assignment) => assignment.workerUserId === currentWorker.value?.id)
      .map((assignment) => ({
        id: `worker:operation:${order.id}:${assignment.operationId}`,
        label: assignment.operationName,
        kind: "operation" as const,
        assignmentId: assignment.id,
        assignmentStatus: assignment.workerStatus,
        orderGroupKey: String(order.id),
        productLabel: order.productName,
        productQuantity: order.quantity,
        leatherTypeName: order.leatherTypeName,
        orderNumber: order.orderNumber,
      })),
  );
});

const workerTimerDefinitions = computed<WorkerTimerDefinition[]>(() => [
  ...staticWorkerTimerDefinitions.value,
  ...assignedWorkerTimerDefinitions.value,
]);

const workerTimerGroups = computed<WorkerTimerGroup[]>(() => {
  const groups = new Map<string, WorkerTimerGroup>();

  for (const timer of assignedWorkerTimerDefinitions.value) {
    if (!timer.orderGroupKey || !timer.orderNumber || !timer.productLabel) {
      continue;
    }

    const existingGroup = groups.get(timer.orderGroupKey);
    if (existingGroup) {
      existingGroup.timers.push(timer);
      continue;
    }

    groups.set(timer.orderGroupKey, {
      groupKey: timer.orderGroupKey,
      orderNumber: timer.orderNumber,
      productLabel: timer.productLabel,
      leatherTypeName: timer.leatherTypeName ?? null,
      quantity: timer.productQuantity ?? 0,
      timers: [timer],
    });
  }

  return [...groups.values()];
});

const workerPrimaryTimers = computed(() =>
  staticWorkerTimerDefinitions.value.filter((timer) => timer.kind !== "idle"),
);

const workerIdleTimer = computed(
  () => staticWorkerTimerDefinitions.value.find((timer) => timer.kind === "idle") ?? null,
);

const workerAssignmentStatusFilterLabel = computed(
  () =>
    workerAssignmentStatusOptions.find(
      (option) => option.value === workerAssignmentStatusFilter.value,
    )?.label ?? "В работе",
);

const isWorkerDayActive = computed(() => workerDayStartedAt.value !== null);

const workerDayElapsedMs = computed(() => {
  if (workerDayStartedAt.value === null) {
    return 0;
  }

  return workerTimerNow.value - workerDayStartedAt.value;
});

const workerActiveTimer = computed(() =>
  activeWorkerTimerId.value ? workerTimers.value[activeWorkerTimerId.value] ?? null : null,
);

const shouldShowWorkerActiveTimerCard = computed(() => !isSmartphoneViewport.value);

const statisticsDailyMax = computed(() =>
  Math.max(...(statisticsOverview.value?.dailyBreakdown.map((item) => item.totalMs) ?? [0]), 1),
);

const statisticsOperationMax = computed(() =>
  Math.max(...(statisticsOverview.value?.topOperations.map((item) => item.totalMs) ?? [0]), 1),
);

const statisticsOrderMax = computed(() =>
  Math.max(...(statisticsOverview.value?.topOrders.map((item) => item.totalMs) ?? [0]), 1),
);

const statisticsWorkerMax = computed(() =>
  Math.max(...(statisticsOverview.value?.workers.map((item) => item.totalMs) ?? [0]), 1),
);

const statisticsIdleMax = computed(() =>
  Math.max(...(statisticsOverview.value?.idleByDay.map((item) => item.idleMs) ?? [0]), 1),
);

onMounted(async () => {
  await initializePage();
  updateSmartphoneViewport();
  window.addEventListener("keydown", handleWindowKeydown);
  window.addEventListener("resize", updateSmartphoneViewport);
  const intervalId = window.setInterval(() => {
    workerTimerNow.value = Date.now();
  }, 1000);
  workerClockIntervalId = intervalId;
});

watch(activeTab, (value) => {
  storeTab(ACTIVE_TAB_STORAGE_KEY, value);
  if (value === "worker" && !authInitializing.value && canLoadWorkerWorkspace()) {
    void loadWorkerWorkspace();
  }
});

watch(workerOrderRouteId, (orderId) => {
  workerOrderFocusMessage.value = "";
  if (orderId === null || authInitializing.value || !currentSession.value) {
    return;
  }

  if (!canLoadWorkerWorkspace()) {
    return;
  }

  if (activeTab.value !== "worker") {
    activeTab.value = "worker";
    return;
  }

  void loadWorkerWorkspace();
});

watch(availableTabs, (nextTabs) => {
  if (!nextTabs.length) {
    return;
  }

  if (!nextTabs.some((tab) => tab.id === activeTab.value)) {
    activeTab.value = nextTabs[0].id;
  }
}, { immediate: true });

watch(brigadierTab, (value) => {
  storeTab(BRIGADIER_TAB_STORAGE_KEY, value);
});

watch(constructorTab, (value) => {
  storeTab(CONSTRUCTOR_TAB_STORAGE_KEY, value);
});

watch(constructorDirectoryTab, (value) => {
  storeTab(CONSTRUCTOR_DIRECTORY_TAB_STORAGE_KEY, value);
});

watch(
  [workOrderFilter, workOrderStatusTab, workOrderSort],
  () => {
    reloadWorkOrdersFromFirstPage();
  },
);

watch(workOrdersPage, () => {
  void loadWorkOrders();
});

watch(
  [leatherTypeFilter, showInactiveLeatherTypes, leatherTypeSortDirection],
  () => {
    reloadLeatherTypesFromFirstPage();
  },
);

watch(leatherTypesPage, () => {
  void loadLeatherTypes();
});

watch(
  [
    operationCatalogFilter,
    showInactiveOperationCatalogEntries,
    operationCatalogSortDirection,
  ],
  () => {
    reloadOperationCatalogFromFirstPage();
  },
);

watch(operationCatalogPage, () => {
  void loadOperationCatalog();
});

watch(workerAssignmentStatusFilter, () => {
  if (activeTab.value === "worker" && canLoadWorkerWorkspace()) {
    void loadWorkerWorkspace();
  }
});

watch(
  workerTimerDefinitions,
  (definitions) => {
    syncWorkerTimers(definitions);
  },
  { immediate: true },
);

watch(
  workerTimerGroups,
  (groups) => {
    const nextExpanded: Record<string, boolean> = {};

    for (const group of groups) {
      nextExpanded[group.groupKey] =
        workerGroupExpanded.value[group.groupKey] ?? false;
    }

    workerGroupExpanded.value = nextExpanded;
  },
  { immediate: true },
);

onBeforeUnmount(() => {
  closeWorkerQrScanner();
  window.removeEventListener("keydown", handleWindowKeydown);
  window.removeEventListener("resize", updateSmartphoneViewport);
  clearWorkerAssignmentStatusDropdownCloseTimeout();
  clearOperationNameDropdownCloseTimeout();
  if (workerClockIntervalId !== null) {
    window.clearInterval(workerClockIntervalId);
  }
});

function updateSmartphoneViewport() {
  isSmartphoneViewport.value = window.matchMedia(SMARTPHONE_MEDIA_QUERY).matches;
}

function setActiveTab(tabId: TabId) {
  activeTab.value = tabId;
}

function isSortFieldActive(field: "name" | "version" | "created"): boolean {
  return productSort.value.startsWith(field);
}

function getSortDirection(field: "name" | "version" | "created"): "asc" | "desc" {
  if (!isSortFieldActive(field)) {
    return field === "created" ? "desc" : "asc";
  }

  return productSort.value.endsWith("asc") ? "asc" : "desc";
}

function toggleProductSort(field: "name" | "version" | "created") {
  const nextDirection = isSortFieldActive(field)
    ? getSortDirection(field) === "asc"
      ? "desc"
      : "asc"
    : field === "created"
      ? "desc"
      : "asc";

  productSort.value = `${field}-${nextDirection}` as ProductSort;
}

function isWorkOrderSortFieldActive(field: WorkOrderSortBy): boolean {
  return workOrderSort.value.startsWith(field);
}

function getWorkOrderSortDirection(
  field: WorkOrderSortBy,
): "asc" | "desc" {
  if (!isWorkOrderSortFieldActive(field)) {
    return getDefaultWorkOrderSortDirection(field);
  }

  return workOrderSort.value.endsWith("asc") ? "asc" : "desc";
}

function toggleWorkOrderSort(field: WorkOrderSortBy) {
  const nextDirection = isWorkOrderSortFieldActive(field)
    ? getWorkOrderSortDirection(field) === "asc"
      ? "desc"
      : "asc"
    : getDefaultWorkOrderSortDirection(field);

  workOrderSort.value = `${field}-${nextDirection}`;
}

function getDefaultWorkOrderSortDirection(
  field: WorkOrderSortBy,
): WorkOrderSortDirection {
  return field === "name" ||
    field === "order_number" ||
    field === "planned_completion"
    ? "asc"
    : "desc";
}

function applyWorkOrderSearch() {
  const nextSearch = workOrderSearchDraft.value.trim();
  if (nextSearch === workOrderFilter.value) {
    return;
  }

  workOrderFilter.value = nextSearch;
}

function clearWorkOrderSearch() {
  workOrderSearchDraft.value = "";
  if (workOrderFilter.value === "") {
    return;
  }

  workOrderFilter.value = "";
}

function getWorkOrderListParams(): WorkOrderListParams {
  const [sortBy, sortDirection] = workOrderSort.value.split("-") as [
    WorkOrderSortBy,
    WorkOrderSortDirection,
  ];

  return {
    search: workOrderFilter.value,
    status: workOrderStatusTab.value,
    sortBy,
    sortDirection,
    page: workOrdersPage.value,
    pageSize: WORK_ORDER_PAGE_SIZE,
  };
}

function reloadWorkOrdersFromFirstPage() {
  if (workOrdersPage.value === 1) {
    void loadWorkOrders();
    return;
  }

  workOrdersPage.value = 1;
}

function goToWorkOrdersPage(page: number) {
  const nextPage = Math.min(Math.max(page, 1), workOrdersPages.value);
  if (nextPage === workOrdersPage.value) {
    return;
  }

  workOrdersPage.value = nextPage;
}

function toggleLeatherTypeSort() {
  leatherTypeSortDirection.value =
    leatherTypeSortDirection.value === "asc" ? "desc" : "asc";
}

function applyLeatherTypeSearch() {
  const nextSearch = leatherTypeSearchDraft.value.trim();
  if (nextSearch === leatherTypeFilter.value) {
    return;
  }

  leatherTypeFilter.value = nextSearch;
}

function clearLeatherTypeSearch() {
  leatherTypeSearchDraft.value = "";
  if (leatherTypeFilter.value === "") {
    return;
  }

  leatherTypeFilter.value = "";
}

function getLeatherTypeListParams(): LeatherTypeListParams {
  return {
    search: leatherTypeFilter.value,
    includeInactive: showInactiveLeatherTypes.value,
    sortDirection: leatherTypeSortDirection.value,
    page: leatherTypesPage.value,
    pageSize: LEATHER_TYPE_PAGE_SIZE,
  };
}

function toggleOperationCatalogSort() {
  operationCatalogSortDirection.value =
    operationCatalogSortDirection.value === "asc" ? "desc" : "asc";
}

function applyOperationCatalogSearch() {
  const nextSearch = operationCatalogSearchDraft.value.trim();
  if (nextSearch === operationCatalogFilter.value) {
    return;
  }

  operationCatalogFilter.value = nextSearch;
}

function clearOperationCatalogSearch() {
  operationCatalogSearchDraft.value = "";
  if (operationCatalogFilter.value === "") {
    return;
  }

  operationCatalogFilter.value = "";
}

function getOperationCatalogListParams(): OperationCatalogListParams {
  return {
    search: operationCatalogFilter.value,
    includeInactive: showInactiveOperationCatalogEntries.value,
    sortDirection: operationCatalogSortDirection.value,
    page: operationCatalogPage.value,
    pageSize: OPERATION_CATALOG_PAGE_SIZE,
  };
}

function reloadLeatherTypesFromFirstPage() {
  if (leatherTypesPage.value === 1) {
    void loadLeatherTypes();
    return;
  }

  leatherTypesPage.value = 1;
}

function goToLeatherTypesPage(page: number) {
  const nextPage = Math.min(Math.max(page, 1), leatherTypesPages.value);
  if (nextPage === leatherTypesPage.value) {
    return;
  }

  leatherTypesPage.value = nextPage;
}

function reloadOperationCatalogFromFirstPage() {
  if (operationCatalogPage.value === 1) {
    void loadOperationCatalog();
    return;
  }

  operationCatalogPage.value = 1;
}

function goToOperationCatalogPage(page: number) {
  const nextPage = Math.min(Math.max(page, 1), operationCatalogPages.value);
  if (nextPage === operationCatalogPage.value) {
    return;
  }

  operationCatalogPage.value = nextPage;
}

function isUserSortFieldActive(field: "name" | "created"): boolean {
  return userSort.value.startsWith(field);
}

function getUserSortDirection(field: "name" | "created"): "asc" | "desc" {
  if (!isUserSortFieldActive(field)) {
    return field === "created" ? "desc" : "asc";
  }

  return userSort.value.endsWith("asc") ? "asc" : "desc";
}

function toggleUserSort(field: "name" | "created") {
  const nextDirection = isUserSortFieldActive(field)
    ? getUserSortDirection(field) === "asc"
      ? "desc"
      : "asc"
    : field === "created"
      ? "desc"
      : "asc";

  userSort.value = `${field}-${nextDirection}` as UserSort;
}

function isBrigadierSortFieldActive(field: "name" | "created"): boolean {
  return brigadierProductSort.value.startsWith(field);
}

function getBrigadierSortDirection(
  field: "name" | "created",
): "asc" | "desc" {
  if (!isBrigadierSortFieldActive(field)) {
    return field === "created" ? "desc" : "asc";
  }

  return brigadierProductSort.value.endsWith("asc") ? "asc" : "desc";
}

function toggleBrigadierSort(field: "name" | "created") {
  const nextDirection = isBrigadierSortFieldActive(field)
    ? getBrigadierSortDirection(field) === "asc"
      ? "desc"
      : "asc"
    : field === "created"
      ? "desc"
      : "asc";

  brigadierProductSort.value = `${field}-${nextDirection}` as ProductSort;
}

async function initializePage() {
  authInitializing.value = true;

  try {
    currentSession.value = await fetchCurrentSession();
    await loadProtectedData();
  } catch {
    currentSession.value = null;
  } finally {
    authInitializing.value = false;
  }
}

async function loadProtectedData() {
  if (workerOrderRouteId.value !== null && canLoadWorkerWorkspace()) {
    activeTab.value = "worker";
  }

  const protectedDataLoaders = [
    loadProducts(),
    loadUsers(),
    loadLeatherTypes(),
    loadActiveLeatherTypes(),
    loadOperationCatalog(),
    loadActiveOperationCatalogEntries(),
  ];

  if (canManageWorkOrders.value) {
    protectedDataLoaders.push(loadWorkOrders());
  } else {
    workOrders.value = [];
    workOrdersTotal.value = 0;
    workOrdersPage.value = 1;
    workOrdersPages.value = 1;
    brigadierOrdersError.value = "";
    brigadierOrdersLoading.value = false;
  }

  await Promise.all(protectedDataLoaders);

  if (canLoadWorkerWorkspace() && activeTab.value === "worker") {
    await loadWorkerWorkspace();
  } else {
    workOrderDetails.value = [];
    workerAssignmentsError.value = "";
    workerAssignmentsLoading.value = false;
    resetWorkerTimerState();
  }

  if (canViewStatistics.value) {
    await loadStatistics();
  } else {
    statisticsOverview.value = null;
    statisticsError.value = "";
  }
}

function isUnauthorizedError(error: unknown): boolean {
  if (!(error instanceof Error)) {
    return false;
  }

  return (
    error.message.includes("Требуется аутентификация") ||
    error.message.includes("Сессия истекла")
  );
}

function redirectToAuth(message = "Требуется аутентификация.") {
  currentSession.value = null;
  authInitializing.value = false;
  authSubmitting.value = false;
  authRequiresPasswordSetup.value = false;
  authPassword.value = "";
  authNewPassword.value = "";
  authConfirmPassword.value = "";
  authError.value = message;
  workOrderDetails.value = [];
  workerAssignmentsError.value = "";
  workerAssignmentsLoading.value = false;
  resetWorkerTimerState();
  closeWorkerQrScanner();
  closeChangePasswordModal();
  closeBrigadierOrderModal();
  closeWorkOrderActionConfirm();
  closeProductModal();
  closeDeleteConfirmation();
  closeUserDeleteConfirmation();
}

async function submitAuthentication() {
  authSubmitting.value = true;
  authInitializing.value = true;
  authError.value = "";

  try {
    if (authRequiresPasswordSetup.value) {
      if (authNewPassword.value.length < 8) {
        authError.value = "Новый пароль должен содержать не менее 8 символов.";
        return;
      }

      if (authNewPassword.value !== authConfirmPassword.value) {
        authError.value = "Подтверждение пароля не совпадает.";
        return;
      }

      currentSession.value = await setupPassword(
        authPhone.value.trim(),
        authNewPassword.value,
      );
    } else {
      const loginResult = await login(authPhone.value.trim(), authPassword.value);

      if (loginResult.status === "password_setup_required") {
        authRequiresPasswordSetup.value = true;
        authSetupUserName.value = loginResult.userName ?? "";
        authPassword.value = "";
        return;
      }

      currentSession.value = loginResult.session;
    }

    authRequiresPasswordSetup.value = false;
    authSetupUserName.value = "";
    authPassword.value = "";
    authNewPassword.value = "";
    authConfirmPassword.value = "";
    authError.value = "";
    await loadProtectedData();
  } catch (error) {
    authError.value = getErrorMessage(error, "Не удалось пройти аутентификацию.");
  } finally {
    authSubmitting.value = false;
    authInitializing.value = false;
  }
}

async function handleLogout() {
  try {
    await logout();
  } finally {
    redirectToAuth("Сессия завершена.");
  }
}

function openChangePasswordModal() {
  changePasswordModalOpen.value = true;
  changePasswordCurrent.value = "";
  changePasswordNext.value = "";
  changePasswordConfirm.value = "";
  changePasswordError.value = "";
  changePasswordSaving.value = false;
}

function closeChangePasswordModal() {
  changePasswordModalOpen.value = false;
  changePasswordCurrent.value = "";
  changePasswordNext.value = "";
  changePasswordConfirm.value = "";
  changePasswordError.value = "";
  changePasswordSaving.value = false;
}

async function submitPasswordChange() {
  if (!currentSession.value) {
    redirectToAuth();
    return;
  }

  if (changePasswordNext.value.length < 8) {
    changePasswordError.value = "Новый пароль должен содержать не менее 8 символов.";
    return;
  }

  if (changePasswordNext.value !== changePasswordConfirm.value) {
    changePasswordError.value = "Подтверждение пароля не совпадает.";
    return;
  }

  changePasswordSaving.value = true;
  changePasswordError.value = "";

  try {
    currentSession.value = await changePassword(
      changePasswordCurrent.value === "" ? null : changePasswordCurrent.value,
      changePasswordNext.value,
    );
    closeChangePasswordModal();
  } catch (error) {
    changePasswordError.value = getErrorMessage(error, "Не удалось изменить пароль.");
  } finally {
    changePasswordSaving.value = false;
  }
}

async function loadProducts() {
  listLoading.value = true;
  listError.value = "";

  try {
    products.value = await fetchProducts();
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    listError.value = getErrorMessage(error, "Не удалось загрузить изделия.");
  } finally {
    listLoading.value = false;
  }
}

async function loadUsers() {
  usersLoading.value = true;
  usersError.value = "";

  try {
    users.value = await fetchUsers();
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    usersError.value = getErrorMessage(error, "Не удалось загрузить пользователей.");
  } finally {
    usersLoading.value = false;
  }
}

async function loadLeatherTypes() {
  const requestId = ++leatherTypesRequestId;
  leatherTypesLoading.value = true;
  leatherTypesError.value = "";

  try {
    const page = await fetchLeatherTypes(getLeatherTypeListParams());

    if (requestId !== leatherTypesRequestId) {
      return;
    }

    if (
      page.items.length === 0 &&
      page.total > 0 &&
      leatherTypesPage.value > page.pages
    ) {
      leatherTypesTotal.value = page.total;
      leatherTypesPages.value = page.pages;
      leatherTypesPage.value = page.pages;
      return;
    }

    leatherTypes.value = page.items;
    leatherTypesTotal.value = page.total;
    leatherTypesPage.value = page.page;
    leatherTypesPages.value = page.pages;
  } catch (error) {
    if (requestId !== leatherTypesRequestId) {
      return;
    }

    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    leatherTypesError.value = getErrorMessage(
      error,
      "Не удалось загрузить виды кожи.",
    );
  } finally {
    if (requestId === leatherTypesRequestId) {
      leatherTypesLoading.value = false;
    }
  }
}

async function loadActiveLeatherTypes() {
  try {
    activeLeatherTypes.value = await fetchAllLeatherTypes({
      includeInactive: false,
      sortDirection: "asc",
      pageSize: 100,
    });
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    activeLeatherTypes.value = [];
  }
}

async function loadOperationCatalog() {
  const requestId = ++operationCatalogRequestId;
  operationCatalogLoading.value = true;
  operationCatalogError.value = "";

  try {
    const page = await fetchOperationCatalog(getOperationCatalogListParams());

    if (requestId !== operationCatalogRequestId) {
      return;
    }

    if (
      page.items.length === 0 &&
      page.total > 0 &&
      operationCatalogPage.value > page.pages
    ) {
      operationCatalogTotal.value = page.total;
      operationCatalogPages.value = page.pages;
      operationCatalogPage.value = page.pages;
      return;
    }

    operationCatalogEntries.value = page.items;
    operationCatalogTotal.value = page.total;
    operationCatalogPage.value = page.page;
    operationCatalogPages.value = page.pages;
  } catch (error) {
    if (requestId !== operationCatalogRequestId) {
      return;
    }

    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    operationCatalogError.value = getErrorMessage(
      error,
      "Не удалось загрузить операции.",
    );
  } finally {
    if (requestId === operationCatalogRequestId) {
      operationCatalogLoading.value = false;
    }
  }
}

async function loadActiveOperationCatalogEntries() {
  try {
    activeOperationCatalogEntries.value = await fetchAllOperationCatalogEntries({
      includeInactive: false,
      sortDirection: "asc",
      pageSize: 100,
    });
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    activeOperationCatalogEntries.value = [];
  }
}

async function loadWorkOrders() {
  if (!canManageWorkOrders.value) {
    workOrders.value = [];
    workOrdersTotal.value = 0;
    workOrdersPage.value = 1;
    workOrdersPages.value = 1;
    brigadierOrdersError.value = "";
    brigadierOrdersLoading.value = false;
    return;
  }

  const requestId = ++workOrdersRequestId;
  brigadierOrdersLoading.value = true;
  brigadierOrdersError.value = "";

  try {
    const ordersPage = await fetchWorkOrders(getWorkOrderListParams());

    if (requestId !== workOrdersRequestId) {
      return;
    }

    if (
      ordersPage.items.length === 0 &&
      ordersPage.total > 0 &&
      workOrdersPage.value > ordersPage.pages
    ) {
      workOrdersTotal.value = ordersPage.total;
      workOrdersPages.value = ordersPage.pages;
      workOrdersPage.value = ordersPage.pages;
      return;
    }

    workOrders.value = ordersPage.items;
    workOrdersTotal.value = ordersPage.total;
    workOrdersPage.value = ordersPage.page;
    workOrdersPages.value = ordersPage.pages;
  } catch (error) {
    if (requestId !== workOrdersRequestId) {
      return;
    }

    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    brigadierOrdersError.value = getErrorMessage(error, "Не удалось загрузить заказы.");
  } finally {
    if (requestId === workOrdersRequestId) {
      brigadierOrdersLoading.value = false;
    }
  }
}

function canLoadWorkerWorkspace(): boolean {
  return currentSession.value?.userRoles.includes("worker") ?? false;
}

async function loadWorkerWorkspace() {
  if (!canLoadWorkerWorkspace()) {
    workOrderDetails.value = [];
    workerAssignmentsError.value = "";
    workerAssignmentsLoading.value = false;
    resetWorkerTimerState();
    return;
  }

  const assignmentsLoaded = await loadWorkerAssignments();
  if (assignmentsLoaded) {
    await loadWorkerTimerState();
    await focusWorkerOrderFromRoute();
  }
}

async function loadWorkerAssignments(): Promise<boolean> {
  const requestId = ++workerAssignmentsRequestId;
  workerAssignmentsLoading.value = true;
  workerAssignmentsError.value = "";

  try {
    const assignedOrders = await fetchWorkerAssignedWorkOrders(
      workerAssignmentStatusFilter.value,
    );

    if (requestId !== workerAssignmentsRequestId) {
      return false;
    }

    workOrderDetails.value = assignedOrders;
    return true;
  } catch (error) {
    if (requestId !== workerAssignmentsRequestId) {
      return false;
    }

    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return false;
    }
    workOrderDetails.value = [];
    workerAssignmentsError.value = getErrorMessage(
      error,
      "Не удалось загрузить назначения исполнителя.",
    );
    return false;
  } finally {
    if (requestId === workerAssignmentsRequestId) {
      workerAssignmentsLoading.value = false;
    }
  }
}

async function loadWorkerTimerState() {
  workerTimerSubmitting.value = true;

  try {
    applyWorkerTimerApiState(await fetchWorkerTimerState());
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    workerAssignmentsError.value = getErrorMessage(
      error,
      "Не удалось загрузить состояние таймеров.",
    );
  } finally {
    workerTimerSubmitting.value = false;
  }
}

async function loadStatistics() {
  const validationError = statisticsPeriodValidationError.value;
  if (validationError) {
    statisticsError.value = validationError;
    return;
  }

  statisticsLoading.value = true;
  statisticsError.value = "";

  try {
    statisticsOverview.value = await fetchStatisticsOverview(getStatisticsPeriodParams());
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    statisticsError.value = getErrorMessage(error, "Не удалось загрузить статистику.");
  } finally {
    statisticsLoading.value = false;
  }
}

async function exportStatisticsXlsx() {
  const validationError = statisticsPeriodValidationError.value;
  if (validationError) {
    statisticsError.value = validationError;
    return;
  }

  statisticsExportLoading.value = true;
  statisticsError.value = "";

  try {
    const { blob, filename } = await downloadStatisticsExport(getStatisticsPeriodParams());
    triggerFileDownload(blob, filename);
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    statisticsError.value = getErrorMessage(error, "Не удалось выгрузить статистику.");
  } finally {
    statisticsExportLoading.value = false;
  }
}

function resetForm() {
  hasAttemptedSubmit.value = false;
  modalError.value = "";
  modalProductId.value = null;
  productName.value = "";
  productVersion.value = "";
  productMaterialCostCents.value = null;
  operationTree.value = [];
  operationStandardTimeInputErrors.value = {};
  nextOperationId = 1;
}

function startCreateProduct() {
  modalMode.value = "create";
  modalLoading.value = false;
  saveLoading.value = false;
  resetForm();
}

async function startCopyProduct(productId: number) {
  await openProductModal(productId, "copy");
}

async function startViewProduct(productId: number) {
  await openProductModal(productId, "view");
}

async function openProductModal(productId: number, mode: Exclude<ModalMode, "create" | null>) {
  modalMode.value = mode;
  modalLoading.value = true;
  saveLoading.value = false;
  resetForm();

  try {
    const product = await fetchProduct(productId);
    fillFormFromProduct(product);
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    modalError.value = getErrorMessage(error, "Не удалось загрузить изделие.");
  } finally {
    modalLoading.value = false;
  }
}

function closeProductModal() {
  clearOperationNameDropdownCloseTimeout();
  openOperationNameDropdownId.value = null;
  modalMode.value = null;
  modalProductId.value = null;
  modalLoading.value = false;
  saveLoading.value = false;
  hasAttemptedSubmit.value = false;
  modalError.value = "";
}

function openDeleteConfirmation(product: ProductSummary) {
  productPendingDelete.value = product;
}

function closeDeleteConfirmation() {
  productPendingDelete.value = null;
}

function openUserDeleteConfirmation(user: UserRecord) {
  if (editingUserId.value !== null && editingUserId.value !== user.id) {
    return;
  }

  userPendingDelete.value = user;
}

function closeUserDeleteConfirmation() {
  userPendingDelete.value = null;
}

function openWorkOrderActionConfirm(
  order: WorkOrderSummary,
  kind: WorkOrderActionConfirmKind,
) {
  workOrderActionConfirm.value = { order, kind };
}

function closeWorkOrderActionConfirm() {
  const pendingOrder = workOrderActionConfirm.value?.order;
  if (pendingOrder && isWorkOrderBusy(pendingOrder.id)) {
    return;
  }

  workOrderActionConfirm.value = null;
}

async function openWorkOrderTimeBreakdown(order: WorkOrderSummary) {
  const requestId = ++workOrderTimeBreakdownRequestId;
  workOrderTimeBreakdownModal.value = {
    order,
    breakdown: null,
  };
  workOrderTimeBreakdownLoading.value = true;
  workOrderTimeBreakdownError.value = "";

  try {
    const breakdown = await fetchWorkOrderTimeBreakdown(order.id);
    if (
      requestId !== workOrderTimeBreakdownRequestId ||
      workOrderTimeBreakdownModal.value?.order.id !== order.id
    ) {
      return;
    }

    workOrderTimeBreakdownModal.value = {
      order,
      breakdown,
    };
  } catch (error) {
    if (requestId !== workOrderTimeBreakdownRequestId) {
      return;
    }

    workOrderTimeBreakdownError.value = getErrorMessage(
      error,
      "Не удалось загрузить детализацию времени.",
    );
  } finally {
    if (requestId === workOrderTimeBreakdownRequestId) {
      workOrderTimeBreakdownLoading.value = false;
    }
  }
}

function closeWorkOrderTimeBreakdown() {
  workOrderTimeBreakdownRequestId += 1;
  workOrderTimeBreakdownModal.value = null;
  workOrderTimeBreakdownLoading.value = false;
  workOrderTimeBreakdownError.value = "";
}

function setBrigadierTab(tabId: BrigadierTabId) {
  brigadierTab.value = tabId;
}

function syncWorkerTimers(definitions: WorkerTimerDefinition[]) {
  const nextTimers: Record<string, WorkerTimerState> = {};

  for (const definition of definitions) {
    const existingTimer = workerTimers.value[definition.id];
    nextTimers[definition.id] = existingTimer
      ? {
          ...existingTimer,
          ...definition,
        }
      : {
          ...definition,
          elapsedMs: 0,
          startedAtMs: null,
        };
  }

  if (activeWorkerTimerId.value && !nextTimers[activeWorkerTimerId.value]) {
    activeWorkerTimerId.value = null;
  }

  workerTimers.value = nextTimers;
}

function resetWorkerTimerState() {
  workerDayStartedAt.value = null;
  activeWorkerTimerId.value = null;
  workerTimers.value = {};
  workerTimerNow.value = Date.now();
}

function clearWorkerAssignmentStatusDropdownCloseTimeout() {
  if (workerAssignmentStatusDropdownCloseTimeoutId !== null) {
    window.clearTimeout(workerAssignmentStatusDropdownCloseTimeoutId);
    workerAssignmentStatusDropdownCloseTimeoutId = null;
  }
}

function openWorkerAssignmentStatusDropdown() {
  clearWorkerAssignmentStatusDropdownCloseTimeout();
  isWorkerAssignmentStatusDropdownOpen.value = true;
}

function closeWorkerAssignmentStatusDropdown() {
  clearWorkerAssignmentStatusDropdownCloseTimeout();
  isWorkerAssignmentStatusDropdownOpen.value = false;
}

function scheduleWorkerAssignmentStatusDropdownClose() {
  clearWorkerAssignmentStatusDropdownCloseTimeout();
  workerAssignmentStatusDropdownCloseTimeoutId = window.setTimeout(() => {
    isWorkerAssignmentStatusDropdownOpen.value = false;
    workerAssignmentStatusDropdownCloseTimeoutId = null;
  }, 120);
}

function selectWorkerAssignmentStatusFilter(status: WorkerAssignmentStatus) {
  workerAssignmentStatusFilter.value = status;
  closeWorkerAssignmentStatusDropdown();
}

function getTimerIdForApiTarget(target: {
  timerType: TimerType;
  orderId?: number | null;
  operationId?: number | null;
}): string | null {
  switch (target.timerType) {
    case "preparation":
      return PREPARATION_TIMER_ID;
    case "break":
      return BREAK_TIMER_ID;
    case "idle":
      return IDLE_TIMER_ID;
    case "operation":
      return target.orderId != null && target.operationId != null
        ? `worker:operation:${target.orderId}:${target.operationId}`
        : null;
  }
}

function applyWorkerTimerApiState(state: WorkerTimerApiState) {
  const now = Date.now();
  const nextTimers: Record<string, WorkerTimerState> = {};

  for (const definition of workerTimerDefinitions.value) {
    nextTimers[definition.id] = {
      ...definition,
      elapsedMs: 0,
      startedAtMs: null,
    };
  }

  for (const aggregate of state.timerTotals) {
    const timerId = getTimerIdForApiTarget(aggregate);
    if (!timerId || !nextTimers[timerId]) {
      continue;
    }

    nextTimers[timerId].elapsedMs = aggregate.elapsedMs;
  }

  let activeTimerId: string | null = null;
  if (state.activeTimer) {
    const nextActiveTimerId = getTimerIdForApiTarget(state.activeTimer);
    if (nextActiveTimerId && nextTimers[nextActiveTimerId]) {
      const activeElapsedMs = Math.max(0, now - state.activeTimer.startedAtTs);
      nextTimers[nextActiveTimerId].elapsedMs = Math.max(
        0,
        nextTimers[nextActiveTimerId].elapsedMs - activeElapsedMs,
      );
      nextTimers[nextActiveTimerId].startedAtMs = state.activeTimer.startedAtTs;
      activeTimerId = nextActiveTimerId;
    }
  }

  workerTimers.value = nextTimers;
  workerDayStartedAt.value = state.shift?.startedAtTs ?? null;
  activeWorkerTimerId.value = activeTimerId;
  workerTimerNow.value = now;
}

function handleWindowKeydown(event: KeyboardEvent) {
  if (event.key !== "Escape") {
    return;
  }

  if (isWorkerQrScannerOpen.value) {
    closeWorkerQrScanner();
    return;
  }

  if (changePasswordModalOpen.value) {
    closeChangePasswordModal();
    return;
  }

  if (isWorkerAssignmentStatusDropdownOpen.value) {
    closeWorkerAssignmentStatusDropdown();
    return;
  }

  if (isWorkerDayEndConfirmOpen.value) {
    closeWorkerDayEndConfirm();
    return;
  }

  if (workerAssignmentStatusConfirm.value) {
    closeWorkerAssignmentStatusConfirm();
    return;
  }

  if (isBrigadierSaveConfirmOpen.value) {
    closeBrigadierSaveConfirm();
    return;
  }

  if (workOrderActionConfirm.value) {
    closeWorkOrderActionConfirm();
    return;
  }

  if (workOrderTimeBreakdownModal.value) {
    closeWorkOrderTimeBreakdown();
    return;
  }

  if (editingUserId.value !== null) {
    cancelUserEdit();
    return;
  }

  if (isUserDeleteModalOpen.value) {
    closeUserDeleteConfirmation();
    return;
  }

  if (isDeleteModalOpen.value) {
    closeDeleteConfirmation();
    return;
  }

  if (isBrigadierOrderModalOpen.value) {
    closeBrigadierOrderModal();
    return;
  }

  if (isModalOpen.value) {
    closeProductModal();
  }
}

function fillFormFromProduct(product: ProductDetail) {
  hasAttemptedSubmit.value = false;
  modalProductId.value = product.id;
  productName.value = product.name;
  productVersion.value = product.version;
  productMaterialCostCents.value = product.materialCostCents;
  operationTree.value = cloneOperations(product.operations);
  nextOperationId = getMaxOperationId(operationTree.value) + 1;
}

async function startWorkerDay() {
  if (!currentWorker.value) {
    return;
  }

  workerTimerSubmitting.value = true;
  workerAssignmentsError.value = "";

  try {
    applyWorkerTimerApiState(await startWorkerDayApi());
    await loadWorkerAssignments();
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    workerAssignmentsError.value = getErrorMessage(
      error,
      "Не удалось начать рабочий день.",
    );
  } finally {
    workerTimerSubmitting.value = false;
  }
}

function requestEndWorkerDay() {
  if (workerDayStartedAt.value === null) {
    return;
  }

  isWorkerDayEndConfirmOpen.value = true;
}

function closeWorkerDayEndConfirm() {
  isWorkerDayEndConfirmOpen.value = false;
}

function isWorkerAssignmentStatusFinal(
  status: WorkerAssignmentStatus,
): status is Exclude<WorkerAssignmentStatus, "in_work"> {
  return status === "hidden" || status === "completed";
}

function requestWorkerAssignmentStatusChange(
  timer: WorkerTimerDefinition,
  status: WorkerAssignmentStatus,
) {
  if (!timer.assignmentId || workerTimerSubmitting.value) {
    return;
  }

  if (isWorkerAssignmentStatusFinal(status)) {
    workerAssignmentStatusConfirm.value = { timer, status };
    return;
  }

  void setWorkerAssignmentStatus(timer, status);
}

function closeWorkerAssignmentStatusConfirm() {
  if (workerTimerSubmitting.value) {
    return;
  }

  workerAssignmentStatusConfirm.value = null;
}

async function confirmWorkerAssignmentStatusChange() {
  const pendingAction = workerAssignmentStatusConfirm.value;
  if (!pendingAction) {
    return;
  }

  await setWorkerAssignmentStatus(pendingAction.timer, pendingAction.status);
}

async function endWorkerDay() {
  if (workerDayStartedAt.value === null) {
    return;
  }

  workerTimerSubmitting.value = true;
  workerAssignmentsError.value = "";

  try {
    applyWorkerTimerApiState(await endWorkerDayApi());
    await loadWorkerAssignments();
    closeWorkerDayEndConfirm();
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    workerAssignmentsError.value = getErrorMessage(
      error,
      "Не удалось завершить рабочий день.",
    );
  } finally {
    workerTimerSubmitting.value = false;
  }
}

async function activateWorkerTimer(timerId: string) {
  if (workerDayStartedAt.value === null) {
    return;
  }

  const timer = workerTimers.value[timerId];

  if (
    !timer ||
    activeWorkerTimerId.value === timerId ||
    timer.assignmentStatus === "hidden" ||
    timer.assignmentStatus === "completed"
  ) {
    return;
  }

  const shouldPreserveScroll = isSmartphoneViewport.value && timer.kind === "operation";
  const previousScrollY = shouldPreserveScroll ? window.scrollY : null;

  workerTimerSubmitting.value = true;
  workerAssignmentsError.value = "";

  try {
    applyWorkerTimerApiState(
      await switchWorkerTimer(timer.kind, {
        orderId: parseOrderIdFromTimerId(timerId),
        operationId: parseOperationIdFromTimerId(timerId),
      }),
    );
    await loadWorkerAssignments();
    if (previousScrollY !== null) {
      await nextTick();
      window.scrollTo({ top: previousScrollY, behavior: "auto" });
      (document.activeElement as HTMLElement | null)?.blur?.();
    }
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    workerAssignmentsError.value = getErrorMessage(
      error,
      "Не удалось переключить таймер.",
    );
  } finally {
    workerTimerSubmitting.value = false;
  }
}

function getWorkerTimerElapsedMs(timerId: string): number {
  const timer = workerTimers.value[timerId];

  if (!timer) {
    return 0;
  }

  if (timer.startedAtMs === null) {
    return timer.elapsedMs;
  }

  return timer.elapsedMs + (workerTimerNow.value - timer.startedAtMs);
}

function isWorkerTimerActive(timerId: string): boolean {
  return activeWorkerTimerId.value === timerId;
}

function toggleWorkerGroup(groupKey: string) {
  workerGroupExpanded.value = {
    ...workerGroupExpanded.value,
    [groupKey]: !workerGroupExpanded.value[groupKey],
  };
}

async function focusWorkerOrderFromRoute() {
  const orderId = workerOrderRouteId.value;
  if (orderId === null) {
    workerOrderFocusMessage.value = "";
    return;
  }

  const focusedGroupKey = String(orderId);
  const focusedGroupExists = workerTimerGroups.value.some(
    (group) => group.groupKey === focusedGroupKey,
  );
  const nextExpanded: Record<string, boolean> = {};

  for (const group of workerTimerGroups.value) {
    nextExpanded[group.groupKey] = group.groupKey === focusedGroupKey;
  }

  workerGroupExpanded.value = nextExpanded;

  if (!focusedGroupExists) {
    workerOrderFocusMessage.value =
      "Для вас нет активных операций по этому заказу.";
    return;
  }

  workerOrderFocusMessage.value = "";
  await nextTick();
  document
    .querySelector<HTMLElement>(`[data-worker-order-id="${orderId}"]`)
    ?.scrollIntoView({ behavior: "smooth", block: "center" });
}

async function openWorkerQrScanner() {
  if (isWorkerQrScannerOpen.value) {
    return;
  }

  const runId = ++workerQrScannerRunId;
  isWorkerQrScannerOpen.value = true;
  workerQrScannerStarting.value = true;
  workerQrScannerError.value = "";

  if (!navigator.mediaDevices?.getUserMedia) {
    workerQrScannerStarting.value = false;
    workerQrScannerError.value = window.isSecureContext
      ? "Этот браузер не поддерживает доступ к камере."
      : "Для доступа к камере откройте FlowCraft по HTTPS.";
    return;
  }

  await nextTick();

  const videoElement = workerQrScannerVideo.value;
  if (!videoElement) {
    workerQrScannerStarting.value = false;
    workerQrScannerError.value = "Не удалось подготовить окно камеры.";
    return;
  }

  try {
    const { BrowserQRCodeReader } = await import("@zxing/browser");
    if (runId !== workerQrScannerRunId) {
      return;
    }

    const reader = new BrowserQRCodeReader(undefined, {
      delayBetweenScanAttempts: 200,
      delayBetweenScanSuccess: 500,
    });
    const controls = await reader.decodeFromConstraints(
      {
        audio: false,
        video: {
          facingMode: { ideal: "environment" },
          width: { ideal: 1280 },
          height: { ideal: 720 },
        },
      },
      videoElement,
      (result, _error, scannerControls) => {
        if (!result || runId !== workerQrScannerRunId) {
          return;
        }

        const orderId = parseWorkerOrderQrCode(result.getText());
        if (orderId === null) {
          workerQrScannerError.value =
            "Этот QR-код не является ссылкой на таймеры заказа FlowCraft.";
          return;
        }

        workerQrScannerControls = scannerControls;
        closeWorkerQrScanner();
        void navigateToScannedWorkerOrder(orderId);
      },
    );

    if (runId !== workerQrScannerRunId || !isWorkerQrScannerOpen.value) {
      controls.stop();
      return;
    }

    workerQrScannerControls = controls;
  } catch (error) {
    if (runId !== workerQrScannerRunId) {
      return;
    }

    workerQrScannerError.value = getWorkerQrScannerError(error);
  } finally {
    if (runId === workerQrScannerRunId) {
      workerQrScannerStarting.value = false;
    }
  }
}

function closeWorkerQrScanner() {
  workerQrScannerRunId += 1;
  workerQrScannerControls?.stop();
  workerQrScannerControls = null;

  const stream = workerQrScannerVideo.value?.srcObject;
  if (stream instanceof MediaStream) {
    for (const track of stream.getTracks()) {
      track.stop();
    }
  }

  if (workerQrScannerVideo.value) {
    workerQrScannerVideo.value.srcObject = null;
  }

  isWorkerQrScannerOpen.value = false;
  workerQrScannerStarting.value = false;
  workerQrScannerError.value = "";
}

function parseWorkerOrderQrCode(value: string): number | null {
  let scannedUrl: URL;

  try {
    scannedUrl = new URL(value.trim());
  } catch {
    return null;
  }

  if (
    !["http:", "https:"].includes(scannedUrl.protocol) ||
    !getWorkerQrAllowedOrigins().has(scannedUrl.origin) ||
    scannedUrl.search ||
    scannedUrl.hash
  ) {
    return null;
  }

  const match = /^\/worker\/orders\/([1-9]\d*)\/timers\/?$/.exec(
    scannedUrl.pathname,
  );
  return match ? Number.parseInt(match[1], 10) : null;
}

function getWorkerQrAllowedOrigins(): Set<string> {
  const allowedOrigins = new Set([window.location.origin]);
  const configuredAppUrl = import.meta.env.VITE_PUBLIC_APP_URL?.trim();

  if (configuredAppUrl) {
    try {
      allowedOrigins.add(new URL(configuredAppUrl).origin);
    } catch {
      return allowedOrigins;
    }
  }

  return allowedOrigins;
}

function getWorkerQrScannerError(error: unknown): string {
  if (error instanceof DOMException) {
    switch (error.name) {
      case "NotAllowedError":
      case "SecurityError":
        return "Разрешите доступ к камере в настройках браузера.";
      case "NotFoundError":
      case "OverconstrainedError":
        return "На устройстве не найдена доступная камера.";
      case "NotReadableError":
        return "Камера занята другим приложением или недоступна.";
    }
  }

  return "Не удалось запустить камеру. Проверьте разрешение и повторите попытку.";
}

async function navigateToScannedWorkerOrder(orderId: number) {
  const isCurrentOrder = workerOrderRouteId.value === orderId;
  await router.push({
    name: "worker-order-timers",
    params: { orderId: String(orderId) },
  });

  if (isCurrentOrder) {
    await focusWorkerOrderFromRoute();
  }
}

async function setWorkerAssignmentStatus(
  timer: WorkerTimerDefinition,
  status: WorkerAssignmentStatus,
) {
  if (!timer.assignmentId || workerTimerSubmitting.value) {
    return;
  }

  const shouldSwitchActiveTimerToBreak =
    isWorkerAssignmentStatusFinal(status) &&
    activeWorkerTimerId.value === timer.id &&
    isWorkerDayActive.value;

  workerTimerSubmitting.value = true;
  workerAssignmentsError.value = "";

  try {
    if (shouldSwitchActiveTimerToBreak) {
      applyWorkerTimerApiState(await switchWorkerTimer("break"));
    }

    await updateWorkerAssignmentStatus(timer.assignmentId, status);
    await loadWorkerAssignments();
    await loadWorkerTimerState();
    workerAssignmentStatusConfirm.value = null;
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    workerAssignmentsError.value = getErrorMessage(
      error,
      "Не удалось обновить статус операции.",
    );
  } finally {
    workerTimerSubmitting.value = false;
  }
}

async function toggleProductStatus(product: ProductSummary) {
  setProductBusy(product.id, true);

  try {
    const updatedProduct = await updateProductStatus(product.id, !product.isActive);
    replaceProductSummary(updatedProduct);
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    listError.value = getErrorMessage(error, "Не удалось обновить статус изделия.");
  } finally {
    setProductBusy(product.id, false);
  }
}

async function submitLeatherType() {
  if (leatherTypeNameError.value) {
    return;
  }

  leatherTypeSaveLoading.value = true;
  leatherTypeError.value = "";

  try {
    await createLeatherType(leatherTypeName.value.trim());
    leatherTypeName.value = "";
    await Promise.all([loadLeatherTypes(), loadActiveLeatherTypes()]);
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    leatherTypeError.value = getErrorMessage(
      error,
      "Не удалось сохранить вид кожи.",
    );
  } finally {
    leatherTypeSaveLoading.value = false;
  }
}

async function toggleLeatherTypeStatus(leatherType: LeatherTypeRecord) {
  setLeatherTypeBusy(leatherType.id, true);
  leatherTypeError.value = "";

  try {
    await updateLeatherTypeStatus(leatherType.id, !leatherType.isActive);
    await Promise.all([loadLeatherTypes(), loadActiveLeatherTypes()]);
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    leatherTypeError.value = getErrorMessage(
      error,
      "Не удалось обновить статус вида кожи.",
    );
  } finally {
    setLeatherTypeBusy(leatherType.id, false);
  }
}

async function submitOperationCatalogEntry() {
  if (operationCatalogNameError.value) {
    return;
  }

  operationCatalogSaveLoading.value = true;
  operationCatalogSaveError.value = "";

  try {
    await createOperationCatalogEntry(operationCatalogName.value.trim());
    operationCatalogName.value = "";
    await Promise.all([
      loadOperationCatalog(),
      loadActiveOperationCatalogEntries(),
    ]);
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    operationCatalogSaveError.value = getErrorMessage(
      error,
      "Не удалось сохранить операцию.",
    );
  } finally {
    operationCatalogSaveLoading.value = false;
  }
}

async function toggleOperationCatalogEntryStatus(entry: OperationCatalogEntry) {
  setOperationCatalogEntryBusy(entry.id, true);
  operationCatalogSaveError.value = "";

  try {
    await updateOperationCatalogEntryStatus(entry.id, !entry.isActive);
    await Promise.all([
      loadOperationCatalog(),
      loadActiveOperationCatalogEntries(),
    ]);
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    operationCatalogSaveError.value = getErrorMessage(
      error,
      "Не удалось обновить статус операции.",
    );
  } finally {
    setOperationCatalogEntryBusy(entry.id, false);
  }
}

async function handleDeleteProduct(product: ProductSummary) {
  if (productPendingDelete.value?.id !== product.id) {
    return;
  }

  setProductBusy(product.id, true);

  try {
    await deleteProduct(product.id);
    products.value = products.value.filter((item) => item.id !== product.id);
    closeDeleteConfirmation();
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    listError.value = getErrorMessage(error, "Не удалось удалить изделие.");
  } finally {
    setProductBusy(product.id, false);
  }
}

function startCreateUser() {
  if (editingUserId.value !== null) {
    return;
  }

  const user = createUserRecord({
    id: nextUserId,
    name: "",
    phone: "",
    passwordHash: null,
    author: getDefaultAuthorName(),
    authorUserId: getDefaultAuthorUserId(),
    roles: [],
    isActive: true,
    createdAtTs: null,
    updatedAtTs: null,
    deletedAtTs: null,
    isNew: true,
  });

  nextUserId += 1;
  users.value = [user, ...users.value];
  userFilter.value = "";
  userVisibility.value = "all";
  userPendingDelete.value = null;
  startEditUser(user);
}

function startEditUser(user: UserRecord) {
  if (editingUserId.value !== null && editingUserId.value !== user.id) {
    return;
  }

  editingUserId.value = user.id;
  editingUserDraft.value = cloneUser(user);
}

function cancelUserEdit() {
  if (editingUserId.value === null) {
    return;
  }

  const currentUser = users.value.find((user) => user.id === editingUserId.value);

  if (currentUser?.isNew) {
    users.value = users.value.filter((user) => user.id !== currentUser.id);
  }

  editingUserId.value = null;
  editingUserDraft.value = null;
}

function isEditingUser(userId: number): boolean {
  return editingUserId.value === userId && editingUserDraft.value !== null;
}

function isUserLocked(userId: number): boolean {
  return editingUserId.value !== null && editingUserId.value !== userId;
}

function getDisplayedUser(user: UserRecord): UserRecord {
  return isEditingUser(user.id) && editingUserDraft.value ? editingUserDraft.value : user;
}

function toggleUserRole(userId: number, role: UserRole) {
  if (!isEditingUser(userId) || !editingUserDraft.value) {
    return;
  }

  const hasRole = editingUserDraft.value.roles.includes(role);

  editingUserDraft.value = {
    ...editingUserDraft.value,
    roles: hasRole
      ? editingUserDraft.value.roles.filter((item) => item !== role)
      : [...editingUserDraft.value.roles, role],
  };
}

function handleUserRoleAction(user: UserRecord, role: UserRole) {
  if (isUserLocked(user.id)) {
    return;
  }

  if (!isEditingUser(user.id)) {
    startEditUser(user);
  }

  toggleUserRole(user.id, role);
}

function toggleUserStatus(userId: number) {
  if (!isEditingUser(userId) || !editingUserDraft.value) {
    return;
  }

  editingUserDraft.value = {
    ...editingUserDraft.value,
    isActive: !editingUserDraft.value.isActive,
  };
}

function handleUserStatusAction(user: UserRecord) {
  if (isUserLocked(user.id)) {
    return;
  }

  if (!isEditingUser(user.id)) {
    startEditUser(user);
  }

  toggleUserStatus(user.id);
}

function handleUserNameInput(userId: number, event: Event) {
  const target = event.target;

  if (!(target instanceof HTMLInputElement) || !isEditingUser(userId) || !editingUserDraft.value) {
    return;
  }

  editingUserDraft.value = {
    ...editingUserDraft.value,
    name: target.value,
  };
}

function handleUserPhoneInput(userId: number, event: Event) {
  const target = event.target;

  if (!(target instanceof HTMLInputElement) || !isEditingUser(userId) || !editingUserDraft.value) {
    return;
  }

  editingUserDraft.value = {
    ...editingUserDraft.value,
    phone: target.value,
  };
}

function hasUserDraftChanges(user: UserRecord): boolean {
  if (!isEditingUser(user.id) || !editingUserDraft.value) {
    return false;
  }

  return (
    editingUserDraft.value.name !== user.name ||
    editingUserDraft.value.phone !== user.phone ||
    editingUserDraft.value.isActive !== user.isActive ||
    !areRolesEqual(editingUserDraft.value.roles, user.roles)
  );
}

function canSaveUser(user: UserRecord): boolean {
  if (!isEditingUser(user.id) || !editingUserDraft.value) {
    return false;
  }

  return (
    Boolean(editingUserDraft.value.name.trim()) &&
    Boolean(editingUserDraft.value.phone.trim()) &&
    editingUserDraft.value.roles.length > 0 &&
    hasUserDraftChanges(user)
  );
}

function saveUserChanges(user: UserRecord) {
  if (!isEditingUser(user.id) || !editingUserDraft.value || !canSaveUser(user)) {
    return;
  }

  void persistUserChanges(user);
}

function deleteUser(user: UserRecord) {
  if (userPendingDelete.value?.id !== user.id) {
    return;
  }

  void removeUser(user);
}

function getUserNameError(user: UserRecord): string {
  if (!isEditingUser(user.id) || !editingUserDraft.value || editingUserDraft.value.name.trim()) {
    return "";
  }

  return "Укажите имя пользователя.";
}

function getUserRolesError(user: UserRecord): string {
  if (!isEditingUser(user.id) || !editingUserDraft.value || editingUserDraft.value.roles.length > 0) {
    return "";
  }

  return "Выберите хотя бы одну роль.";
}

function getUserPhoneError(user: UserRecord): string {
  if (!isEditingUser(user.id) || !editingUserDraft.value || editingUserDraft.value.phone.trim()) {
    return "";
  }

  return "Укажите номер телефона.";
}

async function saveProductToApi() {
  hasAttemptedSubmit.value = true;

  if (!canSaveProduct.value) {
    scrollToSaveBlockIssue();
    return;
  }

  saveLoading.value = true;
  modalError.value = "";

  try {
    if (isViewMode.value) {
      if (modalProductId.value === null) {
        throw new Error("Не удалось определить изделие для сохранения.");
      }

      await updateProductCosts(modalProductId.value, {
        material_cost_cents: productMaterialCostCents.value,
        operations: [],
      });
      await loadProducts();
      closeProductModal();
      return;
    }

    const payload: ProductCreatePayload = {
      name: productName.value.trim(),
      version: productVersion.value.trim(),
      author_user_id: currentSession.value?.userId ?? null,
      material_cost_cents: productMaterialCostCents.value,
      operations: serializeOperations(operationTree.value),
    };

    await createProduct(payload);
    await loadProducts();
    closeProductModal();
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    modalError.value = getErrorMessage(error, "Не удалось сохранить изделие.");
  } finally {
    saveLoading.value = false;
  }
}

function addRootOperation() {
  operationTree.value = [...operationTree.value, createOperationNode()];
}

function addChildOperation(parentId: number) {
  operationTree.value = appendChildOperation(operationTree.value, parentId);
  pruneOperationStandardTimeInputErrors();
}

function addSiblingOperation(operationId: number) {
  operationTree.value = appendSiblingOperation(operationTree.value, operationId);
}

function moveOperationUp(operationId: number) {
  operationTree.value = reorderOperationInParent(operationTree.value, operationId, -1);
}

function moveOperationDown(operationId: number) {
  operationTree.value = reorderOperationInParent(operationTree.value, operationId, 1);
}

function indentOperation(operationId: number) {
  operationTree.value = indentOperationNode(operationTree.value, operationId);
  pruneOperationStandardTimeInputErrors();
}

function outdentOperation(operationId: number) {
  operationTree.value = outdentOperationNode(operationTree.value, operationId);
}

function removeOperation(operationId: number) {
  operationTree.value = deleteOperation(operationTree.value, operationId);
  pruneOperationStandardTimeInputErrors();
}

function handleOperationNameInput(operationId: number, event: Event) {
  const target = event.target;

  if (!(target instanceof HTMLInputElement)) {
    return;
  }

  clearOperationNameDropdownCloseTimeout();
  openOperationNameDropdownId.value = operationId;
  operationTree.value = renameOperation(
    operationTree.value,
    operationId,
    getCanonicalOperationName(target.value) ?? target.value,
    getOperationCatalogEntryByName(target.value)?.id ?? null,
  );
}

function handleOperationGroupNameInput(operationId: number, event: Event) {
  const target = event.target;

  if (!(target instanceof HTMLInputElement)) {
    return;
  }

  operationTree.value = renameOperation(
    operationTree.value,
    operationId,
    target.value,
    null,
  );
}

function clearOperationNameDropdownCloseTimeout() {
  if (operationNameDropdownCloseTimeoutId !== null) {
    window.clearTimeout(operationNameDropdownCloseTimeoutId);
    operationNameDropdownCloseTimeoutId = null;
  }
}

function openOperationNameDropdown(operationId: number) {
  if (isViewMode.value) {
    return;
  }

  clearOperationNameDropdownCloseTimeout();
  openOperationNameDropdownId.value = operationId;
}

function closeOperationNameDropdown() {
  clearOperationNameDropdownCloseTimeout();
  openOperationNameDropdownId.value = null;
}

function scheduleOperationNameDropdownClose(operationId: number) {
  if (isViewMode.value) {
    return;
  }

  clearOperationNameDropdownCloseTimeout();
  operationNameDropdownCloseTimeoutId = window.setTimeout(() => {
    if (openOperationNameDropdownId.value === operationId) {
      openOperationNameDropdownId.value = null;
    }
    operationNameDropdownCloseTimeoutId = null;
  }, 120);
}

function isOperationNameDropdownOpen(operationId: number): boolean {
  return openOperationNameDropdownId.value === operationId;
}

function getOperationNameOptions(row: FlatOperationNodeRow): OperationCatalogEntry[] {
  if (row.isGroup) {
    return [];
  }

  const normalizedQuery = normalizeName(row.name);
  const selectedEntry = getOperationCatalogEntryForRow(row);
  const selectedName = selectedEntry?.name ?? getCanonicalOperationName(row.name);
  const selectedNameKey = normalizeName(selectedName ?? "");
  const shouldFilterByQuery =
    normalizedQuery !== "" && normalizedQuery !== selectedNameKey;

  return [...activeOperationCatalogEntries.value]
    .filter(
      (entry) =>
        normalizeName(entry.name) === selectedNameKey ||
        !shouldFilterByQuery ||
        normalizeName(entry.name).includes(normalizedQuery),
    )
    .sort((left, right) => {
      const leftPriority = normalizeName(left.name) === selectedNameKey ? 0 : 1;
      const rightPriority = normalizeName(right.name) === selectedNameKey ? 0 : 1;

      if (leftPriority !== rightPriority) {
        return leftPriority - rightPriority;
      }

      return left.name.localeCompare(right.name, "ru");
    });
}

function selectOperationName(operationId: number, entry: OperationCatalogEntry) {
  if (isViewMode.value) {
    return;
  }

  operationTree.value = renameOperation(
    operationTree.value,
    operationId,
    entry.name,
    entry.id,
  );
  closeOperationNameDropdown();
}

function clearOperationName(operationId: number) {
  if (isViewMode.value) {
    return;
  }

  operationTree.value = renameOperation(operationTree.value, operationId, "", null);
  openOperationNameDropdown(operationId);
}

function clearOperationGroupName(operationId: number) {
  if (isViewMode.value) {
    return;
  }

  operationTree.value = renameOperation(operationTree.value, operationId, "", null);
}

function getCanonicalOperationName(value: string): string | null {
  return activeOperationCatalogNameByKey.value.get(normalizeName(value)) ?? null;
}

function getOperationCatalogEntryByName(
  value: string,
): OperationCatalogEntry | null {
  return activeOperationCatalogEntryByKey.value.get(normalizeName(value)) ?? null;
}

function getOperationCatalogEntryForRow(
  row: Pick<FlatOperationNodeRow, "operationCatalogEntryId" | "name">,
): OperationCatalogEntry | null {
  if (row.operationCatalogEntryId !== null) {
    const entry = activeOperationCatalogEntryById.value.get(row.operationCatalogEntryId);
    if (entry) {
      return entry;
    }
  }

  return getOperationCatalogEntryByName(row.name);
}

function handleProductMaterialCostInput(event: Event) {
  const target = event.target;

  if (!(target instanceof HTMLInputElement)) {
    return;
  }

  productMaterialCostCents.value = parseMoneyInputToCents(target.value);
}

function handleOperationPriceInput(operationId: number, event: Event) {
  const target = event.target;

  if (isViewMode.value || !(target instanceof HTMLInputElement)) {
    return;
  }

  operationTree.value = updateOperationPrice(
    operationTree.value,
    operationId,
    parseMoneyInputToCents(target.value),
  );
}

function handleOperationStandardTimeInput(operationId: number, event: Event) {
  const target = event.target;

  if (isViewMode.value || !(target instanceof HTMLInputElement)) {
    return;
  }

  const standardTimeSeconds = parseStandardTimeInput(target.value);
  if (standardTimeSeconds === undefined) {
    operationStandardTimeInputErrors.value = {
      ...operationStandardTimeInputErrors.value,
      [operationId]: "Норма времени должна быть указана в формате мм:сс.",
    };
    return;
  }

  clearOperationStandardTimeInputError(operationId);
  operationTree.value = updateOperationStandardTime(
    operationTree.value,
    operationId,
    standardTimeSeconds,
  );
}

function normalizeOperationStandardTimeInput(operationId: number, event: Event) {
  const target = event.target;

  if (!(target instanceof HTMLInputElement)) {
    return;
  }

  if (!operationStandardTimeInputErrors.value[operationId]) {
    const row = flatOperationRows.value.find((item) => item.id === operationId);
    target.value = formatStandardTimeInput(row?.standardTimeSeconds ?? null);
  }
}

function clearOperationStandardTimeInputError(operationId: number) {
  if (!operationStandardTimeInputErrors.value[operationId]) {
    return;
  }

  const nextErrors = { ...operationStandardTimeInputErrors.value };
  delete nextErrors[operationId];
  operationStandardTimeInputErrors.value = nextErrors;
}

function pruneOperationStandardTimeInputErrors() {
  const leafOperationIds = new Set(
    flatOperationRows.value
      .filter((row) => !row.isGroup)
      .map((row) => row.id),
  );
  operationStandardTimeInputErrors.value = Object.fromEntries(
    Object.entries(operationStandardTimeInputErrors.value).filter(([operationId]) =>
      leafOperationIds.has(Number(operationId)),
    ),
  );
}

function updateOperationPrice(
  operations: OperationNode[],
  operationId: number,
  priceCents: number | null,
): OperationNode[] {
  return operations.map((operation) => {
    if (operation.id === operationId) {
      return {
        ...operation,
        priceCents,
      };
    }

    return {
      ...operation,
      children: updateOperationPrice(operation.children, operationId, priceCents),
    };
  });
}

function updateOperationStandardTime(
  operations: OperationNode[],
  operationId: number,
  standardTimeSeconds: number | null,
): OperationNode[] {
  return operations.map((operation) => {
    if (operation.id === operationId) {
      return {
        ...operation,
        standardTimeSeconds,
      };
    }

    return {
      ...operation,
      children: updateOperationStandardTime(
        operation.children,
        operationId,
        standardTimeSeconds,
      ),
    };
  });
}

function shouldShowFieldError(value: string, error: string): boolean {
  return Boolean(error) && (shouldShowValidation.value || value.length > 0);
}

function shouldShowOperationError(row: FlatOperationNodeRow): boolean {
  return (
    Boolean(operationErrors.value[row.id]) &&
    (
      shouldShowValidation.value ||
      row.name.length > 0 ||
      saveBlockIssue.value?.selector === `[data-operation-id="${row.id}"]`
    )
  );
}

function scrollToSaveBlockIssue() {
  const selector = saveBlockIssue.value?.selector;

  if (!selector) {
    return;
  }

  const target = document.querySelector<HTMLElement>(selector);

  if (!target) {
    return;
  }

  target.scrollIntoView({
    behavior: "smooth",
    block: "center",
    inline: "nearest",
  });

  if (target instanceof HTMLInputElement || target instanceof HTMLButtonElement) {
    target.focus({ preventScroll: true });
  }
}

function isProductBusy(productId: number): boolean {
  return busyProductIds.value.includes(productId);
}

function setProductBusy(productId: number, isBusy: boolean) {
  if (isBusy) {
    if (!busyProductIds.value.includes(productId)) {
      busyProductIds.value = [...busyProductIds.value, productId];
    }
    return;
  }

  busyProductIds.value = busyProductIds.value.filter((id) => id !== productId);
}

function isWorkOrderBusy(orderId: number): boolean {
  return busyWorkOrderIds.value.includes(orderId);
}

function setWorkOrderBusy(orderId: number, isBusy: boolean) {
  if (isBusy) {
    busyWorkOrderIds.value = [...new Set([...busyWorkOrderIds.value, orderId])];
    return;
  }

  busyWorkOrderIds.value = busyWorkOrderIds.value.filter((id) => id !== orderId);
}

function isWorkOrderPrintBusy(orderId: number): boolean {
  return busyPrintWorkOrderIds.value.includes(orderId);
}

function setWorkOrderPrintBusy(orderId: number, isBusy: boolean) {
  if (isBusy) {
    busyPrintWorkOrderIds.value = [
      ...new Set([...busyPrintWorkOrderIds.value, orderId]),
    ];
    return;
  }

  busyPrintWorkOrderIds.value = busyPrintWorkOrderIds.value.filter(
    (id) => id !== orderId,
  );
}

function isLeatherTypeBusy(leatherTypeId: number): boolean {
  return busyLeatherTypeIds.value.includes(leatherTypeId);
}

function setLeatherTypeBusy(leatherTypeId: number, isBusy: boolean) {
  if (isBusy) {
    busyLeatherTypeIds.value = [
      ...new Set([...busyLeatherTypeIds.value, leatherTypeId]),
    ];
    return;
  }

  busyLeatherTypeIds.value = busyLeatherTypeIds.value.filter(
    (id) => id !== leatherTypeId,
  );
}

function isOperationCatalogEntryBusy(entryId: number): boolean {
  return busyOperationCatalogEntryIds.value.includes(entryId);
}

function setOperationCatalogEntryBusy(entryId: number, isBusy: boolean) {
  if (isBusy) {
    busyOperationCatalogEntryIds.value = [
      ...new Set([...busyOperationCatalogEntryIds.value, entryId]),
    ];
    return;
  }

  busyOperationCatalogEntryIds.value = busyOperationCatalogEntryIds.value.filter(
    (id) => id !== entryId,
  );
}

function replaceProductSummary(updatedProduct: ProductSummary) {
  products.value = products.value.map((product) =>
    product.id === updatedProduct.id ? updatedProduct : product,
  );
}

function createOperationNode(): OperationNode {
  const operationId = nextOperationId;
  nextOperationId += 1;

  return {
    id: operationId,
    operationCatalogEntryId: null,
    name: "",
    priceCents: null,
    standardTimeSeconds: null,
    children: [],
  };
}

function appendChildOperation(
  operations: OperationNode[],
  parentId: number,
): OperationNode[] {
  return operations.map((operation) => {
    if (operation.id === parentId) {
      return {
        ...operation,
        operationCatalogEntryId: null,
        priceCents: null,
        standardTimeSeconds: null,
        children: [...operation.children, createOperationNode()],
      };
    }

    return {
      ...operation,
      children: appendChildOperation(operation.children, parentId),
    };
  });
}

function appendSiblingOperation(
  operations: OperationNode[],
  operationId: number,
): OperationNode[] {
  const siblingIndex = operations.findIndex((operation) => operation.id === operationId);

  if (siblingIndex >= 0) {
    const nextOperations = [...operations];
    nextOperations.splice(siblingIndex + 1, 0, createOperationNode());
    return nextOperations;
  }

  return operations.map((operation) => ({
    ...operation,
    children: appendSiblingOperation(operation.children, operationId),
  }));
}

function reorderOperationInParent(
  operations: OperationNode[],
  operationId: number,
  direction: -1 | 1,
): OperationNode[] {
  const nextOperations = cloneOperations(operations);
  const path = findOperationPath(nextOperations, operationId);

  if (!path) {
    return operations;
  }

  const siblings = getOperationsAtPath(nextOperations, path.slice(0, -1));
  const currentIndex = path[path.length - 1];
  const targetIndex = currentIndex + direction;

  if (targetIndex < 0 || targetIndex >= siblings.length) {
    return operations;
  }

  const [movedOperation] = siblings.splice(currentIndex, 1);
  siblings.splice(targetIndex, 0, movedOperation);
  return nextOperations;
}

function indentOperationNode(
  operations: OperationNode[],
  operationId: number,
): OperationNode[] {
  const nextOperations = cloneOperations(operations);
  const path = findOperationPath(nextOperations, operationId);

  if (!path) {
    return operations;
  }

  const siblings = getOperationsAtPath(nextOperations, path.slice(0, -1));
  const currentIndex = path[path.length - 1];

  if (currentIndex === 0) {
    return operations;
  }

  const [movedOperation] = siblings.splice(currentIndex, 1);
  siblings[currentIndex - 1].operationCatalogEntryId = null;
  siblings[currentIndex - 1].priceCents = null;
  siblings[currentIndex - 1].standardTimeSeconds = null;
  siblings[currentIndex - 1].children = [
    ...siblings[currentIndex - 1].children,
    movedOperation,
  ];
  return nextOperations;
}

function outdentOperationNode(
  operations: OperationNode[],
  operationId: number,
): OperationNode[] {
  const nextOperations = cloneOperations(operations);
  const path = findOperationPath(nextOperations, operationId);

  if (!path || path.length < 2) {
    return operations;
  }

  const parentPath = path.slice(0, -1);
  const grandParentPath = parentPath.slice(0, -1);
  const siblings = getOperationsAtPath(nextOperations, parentPath);
  const currentIndex = path[path.length - 1];
  const parentIndex = parentPath[parentPath.length - 1];
  const grandSiblings = getOperationsAtPath(nextOperations, grandParentPath);
  const [movedOperation] = siblings.splice(currentIndex, 1);

  grandSiblings.splice(parentIndex + 1, 0, movedOperation);
  return nextOperations;
}

function deleteOperation(
  operations: OperationNode[],
  operationId: number,
): OperationNode[] {
  return operations
    .filter((operation) => operation.id !== operationId)
    .map((operation) => ({
      ...operation,
      children: deleteOperation(operation.children, operationId),
    }));
}

function renameOperation(
  operations: OperationNode[],
  operationId: number,
  name: string,
  operationCatalogEntryId: number | null,
): OperationNode[] {
  return operations.map((operation) => {
    if (operation.id === operationId) {
      return {
        ...operation,
        operationCatalogEntryId,
        name,
      };
    }

    return {
      ...operation,
      children: renameOperation(
        operation.children,
        operationId,
        name,
        operationCatalogEntryId,
      ),
    };
  });
}

function flattenOperations(
  operations: OperationNode[],
  level = 0,
): FlatOperationNodeRow[] {
  return operations.flatMap((operation, index, siblings) => {
    const rows: FlatOperationNodeRow[] = [
      {
        id: operation.id,
        operationCatalogEntryId: operation.operationCatalogEntryId,
        name: operation.name,
        priceCents: operation.priceCents,
        standardTimeSeconds: operation.standardTimeSeconds,
        level,
        isGroup: operation.children.length > 0,
        canMoveUp: index > 0,
        canMoveDown: index < siblings.length - 1,
        canIndent: index > 0,
        canOutdent: level > 0,
      },
      ...flattenOperations(operation.children, level + 1),
    ];

    return rows;
  });
}

function findOperationPath(
  operations: OperationNode[],
  operationId: number,
  path: number[] = [],
): number[] | null {
  for (const [index, operation] of operations.entries()) {
    const nextPath = [...path, index];

    if (operation.id === operationId) {
      return nextPath;
    }

    const childPath = findOperationPath(operation.children, operationId, nextPath);

    if (childPath) {
      return childPath;
    }
  }

  return null;
}

function getOperationsAtPath(
  operations: OperationNode[],
  path: number[],
): OperationNode[] {
  let currentOperations = operations;

  for (const index of path) {
    currentOperations = currentOperations[index].children;
  }

  return currentOperations;
}

function validateOperationTree(
  operations: OperationNode[],
  standardTimeInputErrors: Record<number, string>,
): Record<number, string> {
  const errors: Record<number, string> = {};
  const usedOperationCatalogEntryIds = new Set<number>();

  function walk(nodes: OperationNode[]) {
    for (const node of nodes) {
      const normalizedName = normalizeName(node.name);
      const isGroup = node.children.length > 0;
      const entry = isGroup ? null : getOperationCatalogEntryForRow(node);

      if (!normalizedName) {
        errors[node.id] = "Имя операции не должно быть пустым.";
      } else if (isGroup && node.priceCents !== null) {
        errors[node.id] = "У группы операций не должно быть цены.";
      } else if (isGroup && node.standardTimeSeconds !== null) {
        errors[node.id] = "У группы операций не должно быть нормы времени.";
      } else if (!isGroup && !entry) {
        errors[node.id] = "Выберите операцию из справочника.";
      } else if (entry && usedOperationCatalogEntryIds.has(entry.id)) {
        errors[node.id] = "Операция должна быть уникальной в изделии.";
      } else if (!isGroup && node.priceCents !== null && node.priceCents < 0) {
        errors[node.id] = "Цена операции не может быть отрицательной.";
      } else if (standardTimeInputErrors[node.id]) {
        errors[node.id] = standardTimeInputErrors[node.id];
      }

      if (entry) {
        usedOperationCatalogEntryIds.add(entry.id);
      }
      walk(node.children);
    }
  }

  walk(operations);
  return errors;
}

function cloneOperations(operations: OperationNode[]): OperationNode[] {
  return operations.map((operation) => ({
    id: operation.id,
    operationCatalogEntryId: operation.operationCatalogEntryId,
    name: operation.name,
    priceCents: operation.priceCents,
    standardTimeSeconds: operation.standardTimeSeconds,
    children: cloneOperations(operation.children),
  }));
}

function getMaxOperationId(operations: OperationNode[]): number {
  return operations.reduce(
    (maxId, operation) =>
      Math.max(maxId, operation.id, getMaxOperationId(operation.children)),
    0,
  );
}

function serializeOperations(
  operations: OperationNode[],
): ProductCreatePayload["operations"] {
  return operations.map((operation) => {
    if (operation.children.length > 0) {
      return {
        operation_catalog_entry_id: null,
        name: operation.name.trim(),
        price_cents: null,
        standard_time_seconds: null,
        children: serializeOperations(operation.children),
      };
    }

    const entry = getOperationCatalogEntryForRow(operation);
    if (!entry) {
      throw new Error("Операция должна быть выбрана из справочника.");
    }

    return {
      operation_catalog_entry_id: entry.id,
      name: entry.name,
      price_cents: operation.priceCents,
      standard_time_seconds: operation.standardTimeSeconds,
      children: [],
    };
  });
}

function compareProducts(
  left: ProductSummary,
  right: ProductSummary,
  sort: ProductSort,
): number {
  const compareByVersion = () =>
    left.version.localeCompare(right.version, "ru", { numeric: true });

  switch (sort) {
    case "created-asc":
      return left.createdAtTs - right.createdAtTs;
    case "name-asc":
      return (
        left.name.localeCompare(right.name, "ru") ||
        compareByVersion()
      );
    case "name-desc":
      return (
        right.name.localeCompare(left.name, "ru") ||
        -compareByVersion()
      );
    case "version-asc":
      return compareByVersion();
    case "version-desc":
      return -compareByVersion();
    case "created-desc":
    default:
      return right.createdAtTs - left.createdAtTs;
  }
}

function compareUsers(left: UserRecord, right: UserRecord, sort: UserSort): number {
  switch (sort) {
    case "created-asc":
      return (left.createdAtTs ?? 0) - (right.createdAtTs ?? 0);
    case "name-desc":
      return (
        right.name.localeCompare(left.name, "ru") ||
        ((right.createdAtTs ?? 0) - (left.createdAtTs ?? 0))
      );
    case "created-desc":
      return (right.createdAtTs ?? 0) - (left.createdAtTs ?? 0);
    case "name-asc":
    default:
      return (
        left.name.localeCompare(right.name, "ru") ||
        ((right.createdAtTs ?? 0) - (left.createdAtTs ?? 0))
      );
  }
}

function formatUserRole(role: UserRole): string {
  switch (role) {
    case "worker":
      return "Исполнитель";
    case "brigadier":
      return "Бригадир";
    case "constructor":
      return "Конструктор";
    case "quality_control":
      return "ОТК";
    case "reports":
      return "Отчеты";
    case "admin":
      return "Администратор";
  }
}

function normalizeName(value: string): string {
  return value.trim().toLowerCase();
}

function parseMoneyInputToCents(value: string): number | null {
  const normalizedValue = value.trim().replace(",", ".");

  if (!normalizedValue) {
    return null;
  }

  const parsedValue = Number(normalizedValue);

  if (!Number.isFinite(parsedValue)) {
    return null;
  }

  return Math.round(parsedValue * 100);
}

function formatMoneyInput(cents: number | null): string {
  if (cents === null) {
    return "";
  }

  const value = cents / 100;
  return Number.isInteger(value)
    ? String(value)
    : value.toFixed(2).replace(/0+$/, "").replace(/\.$/, "");
}

function parseStandardTimeInput(value: string): number | null | undefined {
  const normalizedValue = value.trim();
  if (!normalizedValue) {
    return null;
  }

  const match = /^(\d+):([0-5]\d)$/.exec(normalizedValue);
  if (!match) {
    return undefined;
  }

  const minutes = Number(match[1]);
  const seconds = Number(match[2]);
  const totalSeconds = minutes * 60 + seconds;
  return Number.isSafeInteger(totalSeconds) && totalSeconds <= 2_147_483_647
    ? totalSeconds
    : undefined;
}

function formatStandardTimeInput(totalSeconds: number | null): string {
  if (totalSeconds === null) {
    return "";
  }

  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

function formatWorkerGroupProductMeta(group: WorkerTimerGroup): string {
  return `${group.quantity} шт., ${group.leatherTypeName ?? "вид кожи не указан"}`;
}

function getWorkerAssignmentsEmptyMessage(): string {
  switch (workerAssignmentStatusFilter.value) {
    case "hidden":
      return "Для текущего исполнителя нет скрытых операций.";
    case "completed":
      return "Для текущего исполнителя нет выполненных операций.";
    case "in_work":
    default:
      return "Для текущего исполнителя пока нет операций в работе.";
  }
}

function getErrorMessage(error: unknown, fallback: string): string {
  return error instanceof Error ? error.message : fallback;
}

function formatTimestamp(value: number): string {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(value);
}

function getDateInputValue(timestamp: number): string {
  const value = new Date(timestamp);
  const year = value.getFullYear();
  const month = String(value.getMonth() + 1).padStart(2, "0");
  const day = String(value.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

function getDateInputValueForDays(days: number): string {
  const value = new Date();
  value.setDate(value.getDate() - days + 1);
  return getDateInputValue(value.getTime());
}

function syncStatisticsDateRangeToDays(days: number) {
  statisticsDateFrom.value = getDateInputValueForDays(days);
  statisticsDateTo.value = getDateInputValue(Date.now());
}

function getStatisticsPeriodParams(): StatisticsPeriodParams {
  if (statisticsPeriodMode.value === "custom") {
    return {
      dateFrom: statisticsDateFrom.value,
      dateTo: statisticsDateTo.value,
    };
  }

  return {
    days: statisticsPeriodDays.value,
  };
}

function getStatisticsPeriodValidationError(): string {
  if (statisticsPeriodMode.value !== "custom") {
    return "";
  }

  if (!statisticsDateFrom.value || !statisticsDateTo.value) {
    return "Укажите обе даты периода.";
  }

  const startDate = new Date(`${statisticsDateFrom.value}T00:00:00`);
  const endDate = new Date(`${statisticsDateTo.value}T00:00:00`);
  if (Number.isNaN(startDate.getTime()) || Number.isNaN(endDate.getTime())) {
    return "Проверьте даты периода.";
  }
  if (endDate < startDate) {
    return "Дата окончания периода не может быть раньше даты начала.";
  }

  const periodDays = Math.floor(
    (endDate.getTime() - startDate.getTime()) / 86_400_000,
  ) + 1;
  if (periodDays > 90) {
    return "Период статистики не может быть больше 90 дней.";
  }

  return "";
}

function triggerFileDownload(blob: Blob, filename: string) {
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.URL.revokeObjectURL(url);
}

function readStoredTab<T extends string>(
  key: string,
  allowedValues: readonly T[],
  fallback: T,
): T {
  if (typeof window === "undefined") {
    return fallback;
  }

  const storedValue = window.localStorage.getItem(key);

  if (!storedValue || !allowedValues.includes(storedValue as T)) {
    return fallback;
  }

  return storedValue as T;
}

function storeTab(key: string, value: string) {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(key, value);
}

function createUserRecord(params: {
  id: number;
  name: string;
  phone: string;
  passwordHash: string | null;
  author: string | null;
  authorUserId: number | null;
  roles: UserRole[];
  isActive: boolean;
  createdAtTs: number | null;
  updatedAtTs: number | null;
  deletedAtTs: number | null;
  isNew?: boolean;
}): UserRecord {
  return {
    id: params.id,
    name: params.name,
    phone: params.phone,
    passwordHash: params.passwordHash,
    author: params.author,
    authorUserId: params.authorUserId,
    roles: [...params.roles],
    isActive: params.isActive,
    createdAtTs: params.createdAtTs,
    createdAt: params.createdAtTs ? formatTimestamp(params.createdAtTs) : "",
    updatedAtTs: params.updatedAtTs,
    updatedAt: params.updatedAtTs ? formatTimestamp(params.updatedAtTs) : "",
    deletedAtTs: params.deletedAtTs,
    isNew: params.isNew,
  };
}

function cloneUser(user: UserRecord): UserRecord {
  return createUserRecord({
    id: user.id,
    name: user.name,
    phone: user.phone,
    passwordHash: user.passwordHash,
    author: user.author,
    authorUserId: user.authorUserId,
    roles: user.roles,
    isActive: user.isActive,
    createdAtTs: user.createdAtTs,
    updatedAtTs: user.updatedAtTs,
    deletedAtTs: user.deletedAtTs,
    isNew: user.isNew,
  });
}

function areRolesEqual(left: UserRole[], right: UserRole[]): boolean {
  if (left.length !== right.length) {
    return false;
  }

  const sortedLeft = [...left].sort();
  const sortedRight = [...right].sort();

  return sortedLeft.every((role, index) => role === sortedRight[index]);
}

function getDefaultAuthorUserId(): number | null {
  return currentSession.value?.userId ?? null;
}

function getDefaultAuthorName(): string | null {
  return currentSession.value?.userName ?? null;
}

async function openBrigadierCreateOrder(productId: number) {
  brigadierModalMode.value = "create";
  brigadierModalOrderId.value = null;
  brigadierModalLoading.value = true;
  brigadierModalError.value = "";
  brigadierSaveLoading.value = false;
  brigadierModalQuantity.value = "1";
  brigadierModalPlannedCompletionDate.value = "";
  brigadierModalDefectQuantity.value = "0";
  brigadierModalOrderNumber.value = "";
  brigadierModalLeatherTypeId.value = "";
  brigadierModalLeatherTypeNameDraft.value = "";
  brigadierModalHasSpentTime.value = false;
  brigadierModalAssignments.value = [];

  try {
    const [product, allOrders, leatherTypesForSelect] = await Promise.all([
      fetchProduct(productId),
      fetchAllWorkOrders({
        status: "all",
        sortBy: "created",
        sortDirection: "desc",
        pageSize: 100,
      }),
      fetchAllLeatherTypes({
        includeInactive: false,
        sortDirection: "asc",
        pageSize: 100,
      }),
    ]);
    brigadierModalProduct.value = product;
    activeLeatherTypes.value = leatherTypesForSelect;
    brigadierModalLeatherTypeNameDraft.value = "";
    brigadierModalOrderNumber.value = generateNextWorkOrderNumber(allOrders);
    brigadierModalAssignments.value = buildBrigadierAssignments(product.operations);
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    brigadierModalError.value = getErrorMessage(error, "Не удалось загрузить изделие.");
  } finally {
    brigadierModalLoading.value = false;
  }
}

async function openBrigadierManageOrder(order: WorkOrderSummary) {
  brigadierModalMode.value = "manage";
  brigadierModalOrderId.value = order.id;
  brigadierModalLoading.value = true;
  brigadierModalError.value = "";
  brigadierSaveLoading.value = false;
  brigadierModalQuantity.value = String(order.quantity);
  brigadierModalPlannedCompletionDate.value = order.plannedCompletionDate ?? "";
  brigadierModalDefectQuantity.value = String(order.defectQuantity);
  brigadierModalOrderNumber.value = order.orderNumber;
  brigadierModalLeatherTypeId.value =
    order.leatherTypeId === null ? "" : String(order.leatherTypeId);
  brigadierModalLeatherTypeNameDraft.value = order.leatherTypeName ?? "";
  brigadierModalHasSpentTime.value = order.hasSpentTime;
  brigadierModalAssignments.value = [];

  try {
    const [product, orderDetail, leatherTypesForSelect] = await Promise.all([
      fetchProduct(order.productId),
      fetchWorkOrder(order.id),
      fetchAllLeatherTypes({
        includeInactive: true,
        sortDirection: "asc",
        pageSize: 100,
      }),
    ]);
    brigadierModalProduct.value = product;
    activeLeatherTypes.value = leatherTypesForSelect.filter(
      (leatherType) =>
        leatherType.isActive || leatherType.id === orderDetail.leatherTypeId,
    );
    brigadierModalLeatherTypeId.value =
      orderDetail.leatherTypeId === null ? "" : String(orderDetail.leatherTypeId);
    brigadierModalLeatherTypeNameDraft.value =
      activeLeatherTypes.value.find((item) => item.id === orderDetail.leatherTypeId)
        ?.name ?? "";
    brigadierModalHasSpentTime.value = orderDetail.hasSpentTime;
    brigadierModalPlannedCompletionDate.value =
      orderDetail.plannedCompletionDate ?? "";
    brigadierModalAssignments.value = mergeBrigadierAssignments(
      buildBrigadierAssignments(product.operations),
      orderDetail,
    );
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    brigadierModalError.value = getErrorMessage(error, "Не удалось загрузить заказ.");
  } finally {
    brigadierModalLoading.value = false;
  }
}

async function openQualityControlOrder(order: WorkOrderSummary) {
  brigadierModalMode.value = "quality_control";
  brigadierModalOrderId.value = order.id;
  brigadierModalLoading.value = true;
  brigadierModalError.value = "";
  brigadierSaveLoading.value = false;
  brigadierModalQuantity.value = String(order.quantity);
  brigadierModalPlannedCompletionDate.value = order.plannedCompletionDate ?? "";
  brigadierModalDefectQuantity.value = String(order.defectQuantity ?? 0);
  brigadierModalOrderNumber.value = order.orderNumber;
  brigadierModalLeatherTypeId.value =
    order.leatherTypeId === null ? "" : String(order.leatherTypeId);
  brigadierModalLeatherTypeNameDraft.value = order.leatherTypeName ?? "";
  brigadierModalHasSpentTime.value = order.hasSpentTime;
  brigadierModalAssignments.value = [];

  try {
    const [product, orderDetail, leatherTypesForSelect] = await Promise.all([
      fetchProduct(order.productId),
      fetchWorkOrder(order.id),
      fetchAllLeatherTypes({
        includeInactive: true,
        sortDirection: "asc",
        pageSize: 100,
      }),
    ]);
    brigadierModalProduct.value = product;
    activeLeatherTypes.value = leatherTypesForSelect.filter(
      (leatherType) =>
        leatherType.isActive || leatherType.id === orderDetail.leatherTypeId,
    );
    brigadierModalQuantity.value = String(orderDetail.quantity);
    brigadierModalPlannedCompletionDate.value =
      orderDetail.plannedCompletionDate ?? "";
    brigadierModalDefectQuantity.value = String(orderDetail.defectQuantity);
    brigadierModalLeatherTypeId.value =
      orderDetail.leatherTypeId === null ? "" : String(orderDetail.leatherTypeId);
    brigadierModalLeatherTypeNameDraft.value =
      activeLeatherTypes.value.find((item) => item.id === orderDetail.leatherTypeId)
        ?.name ?? "";
    brigadierModalHasSpentTime.value = orderDetail.hasSpentTime;
    brigadierModalAssignments.value = mergeBrigadierAssignments(
      buildBrigadierAssignments(product.operations),
      orderDetail,
    );
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    brigadierModalError.value = getErrorMessage(error, "Не удалось загрузить заказ.");
  } finally {
    brigadierModalLoading.value = false;
  }

  if (
    brigadierModalMode.value === "quality_control" &&
    brigadierModalOrderId.value === order.id &&
    !brigadierModalError.value
  ) {
    await focusBrigadierDefectQuantityInput();
  }
}

async function focusBrigadierDefectQuantityInput() {
  await nextTick();

  const input = document.querySelector<HTMLInputElement>(
    '[data-field="brigadier-defect-quantity"]',
  );
  input?.focus();
  input?.select();
}

async function toggleWorkOrderTakenStatus(order: WorkOrderSummary, isTaken: boolean) {
  setWorkOrderBusy(order.id, true);
  brigadierOrdersError.value = "";

  try {
    await updateWorkOrderTakenStatus(order.id, isTaken);
    await loadWorkOrders();
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    brigadierOrdersError.value = getErrorMessage(
      error,
      "Не удалось обновить состояние заказа.",
    );
  } finally {
    setWorkOrderBusy(order.id, false);
  }
}

async function confirmWorkOrderAction() {
  const pendingAction = workOrderActionConfirm.value;
  if (!pendingAction) {
    return;
  }

  const { order, kind } = pendingAction;
  setWorkOrderBusy(order.id, true);
  brigadierOrdersError.value = "";

  try {
    if (kind === "send_to_quality_control") {
      await updateWorkOrderQualityControlStatus(order.id, true);
    } else if (kind === "return_to_work") {
      await updateWorkOrderQualityControlStatus(order.id, false);
    } else if (kind === "return_to_quality_control") {
      await updateWorkOrderStatus(order.id, false);
    } else if (kind === "return_to_created") {
      await updateWorkOrderTakenStatus(order.id, false);
    } else if (kind === "delete") {
      await updateWorkOrderDeletedStatus(order.id, true);
    } else {
      await updateWorkOrderDeletedStatus(order.id, false);
    }

    await loadWorkOrders();
    workOrderActionConfirm.value = null;
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    brigadierOrdersError.value = getErrorMessage(
      error,
      "Не удалось выполнить действие с заказом.",
    );
  } finally {
    setWorkOrderBusy(order.id, false);
  }
}

async function printWorkOrder(order: WorkOrderSummary) {
  setWorkOrderPrintBusy(order.id, true);
  brigadierOrdersError.value = "";
  printableWorkOrder.value = null;
  printableWorkOrderQrCode.value = "";

  try {
    const orderDetails = await fetchWorkOrder(order.id);
    const orderTimersUrl = getWorkerOrderTimersUrl(orderDetails.id);
    printableWorkOrderQrCode.value = await QRCode.toDataURL(orderTimersUrl, {
      errorCorrectionLevel: "M",
      margin: 4,
      width: 512,
    });
    printableWorkOrder.value = orderDetails;
    await nextTick();
    await waitForPrintableQrImages();
    const clearPrintableWorkOrder = () => {
      printableWorkOrder.value = null;
      printableWorkOrderQrCode.value = "";
      window.removeEventListener("afterprint", clearPrintableWorkOrder);
    };
    window.addEventListener("afterprint", clearPrintableWorkOrder, { once: true });
    window.print();
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    brigadierOrdersError.value = getErrorMessage(
      error,
      "Не удалось подготовить заказ к печати.",
    );
  } finally {
    setWorkOrderPrintBusy(order.id, false);
  }
}

function getWorkerOrderTimersUrl(orderId: number): string {
  const configuredAppUrl = import.meta.env.VITE_PUBLIC_APP_URL?.trim();
  const publicAppUrl = configuredAppUrl || window.location.origin;
  return new URL(`/worker/orders/${orderId}/timers`, publicAppUrl).toString();
}

async function waitForPrintableQrImages() {
  const qrImages = document.querySelectorAll<HTMLImageElement>(
    ".print-order-qr img",
  );
  await Promise.all([...qrImages].map((image) => image.decode()));
}

function closeBrigadierOrderModal() {
  clearBrigadierAssignmentDropdownCloseTimeout();
  clearBrigadierLeatherTypeDropdownCloseTimeout();
  isBrigadierSaveConfirmOpen.value = false;
  brigadierOpenAssignmentDropdownId.value = null;
  isBrigadierLeatherTypeDropdownOpen.value = false;
  brigadierModalMode.value = null;
  brigadierModalProduct.value = null;
  brigadierModalOrderId.value = null;
  brigadierModalAssignments.value = [];
  brigadierModalQuantity.value = "1";
  brigadierModalPlannedCompletionDate.value = "";
  brigadierModalDefectQuantity.value = "0";
  brigadierModalOrderNumber.value = "";
  brigadierModalLeatherTypeId.value = "";
  brigadierModalLeatherTypeNameDraft.value = "";
  brigadierModalHasSpentTime.value = false;
  brigadierModalLoading.value = false;
  brigadierModalError.value = "";
  brigadierSaveLoading.value = false;
}

function buildBrigadierAssignments(
  operations: OperationNode[],
  parents: string[] = [],
): BrigadierOrderAssignment[] {
  return operations.flatMap((operation) => {
    const nextParents = [...parents, operation.name];

    if (operation.children.length === 0) {
      return [
        {
          operationId: operation.id,
          operationLabel: nextParents.join(" / "),
          workerUserId: null,
          workerName: "",
        },
      ];
    }

    return buildBrigadierAssignments(operation.children, nextParents);
  });
}

function mergeBrigadierAssignments(
  baseAssignments: BrigadierOrderAssignment[],
  orderDetail: WorkOrderDetail,
): BrigadierOrderAssignment[] {
  const savedByOperation = new Map(
    orderDetail.assignments.map((assignment) => [assignment.operationId, assignment]),
  );

  return baseAssignments.map((assignment) => {
    const savedAssignment = savedByOperation.get(assignment.operationId);

    if (!savedAssignment) {
      return assignment;
    }

    return {
      ...assignment,
      workerUserId: savedAssignment.workerUserId,
      workerName: savedAssignment.workerUserName ?? "",
    };
  });
}

function handleBrigadierQuantityInput(event: Event) {
  if (!isBrigadierQuantityEditable.value) {
    return;
  }

  const target = event.target;

  if (!(target instanceof HTMLInputElement)) {
    return;
  }

  brigadierModalQuantity.value = target.value.replace(/[^\d]/g, "");
}

function handleBrigadierDefectQuantityInput(event: Event) {
  const target = event.target;

  if (!(target instanceof HTMLInputElement)) {
    return;
  }

  brigadierModalDefectQuantity.value = target.value.replace(/[^\d]/g, "");
}

function handleBrigadierOrderNumberInput(event: Event) {
  const target = event.target;

  if (!(target instanceof HTMLInputElement)) {
    return;
  }

  brigadierModalOrderNumber.value = target.value;
}

function handleBrigadierLeatherTypeInput(event: Event) {
  if (!isBrigadierLeatherTypeEditable.value) {
    return;
  }

  const target = event.target;

  if (!(target instanceof HTMLInputElement)) {
    return;
  }

  const nextName = target.value;
  const normalizedName = normalizeName(nextName);
  const matchedLeatherType =
    activeLeatherTypes.value.find(
      (item) => normalizeName(item.name) === normalizedName,
    ) ?? null;

  clearBrigadierLeatherTypeDropdownCloseTimeout();
  isBrigadierLeatherTypeDropdownOpen.value = true;
  brigadierModalLeatherTypeNameDraft.value =
    matchedLeatherType?.name ?? nextName;
  brigadierModalLeatherTypeId.value =
    matchedLeatherType === null ? "" : String(matchedLeatherType.id);
}

function handleBrigadierAssignmentInput(operationId: number, event: Event) {
  if (!isBrigadierAssignmentsEditable.value) {
    return;
  }

  const target = event.target;

  if (!(target instanceof HTMLInputElement)) {
    return;
  }

  const nextName = target.value;
  const normalizedName = normalizeName(nextName);
  const matchedWorker =
    brigadierWorkerUsers.value.find(
      (user) => normalizeName(user.name) === normalizedName,
    ) ?? null;

  clearBrigadierAssignmentDropdownCloseTimeout();
  brigadierOpenAssignmentDropdownId.value = operationId;
  brigadierModalAssignments.value = brigadierModalAssignments.value.map((assignment) =>
    assignment.operationId === operationId
      ? {
          ...assignment,
          workerName: nextName,
          workerUserId: matchedWorker?.id ?? null,
        }
      : assignment,
  );
}

function clearBrigadierAssignmentDropdownCloseTimeout() {
  if (brigadierDropdownCloseTimeoutId !== null) {
    window.clearTimeout(brigadierDropdownCloseTimeoutId);
    brigadierDropdownCloseTimeoutId = null;
  }
}

function openBrigadierAssignmentDropdown(operationId: number) {
  if (!isBrigadierAssignmentsEditable.value) {
    return;
  }

  clearBrigadierAssignmentDropdownCloseTimeout();
  brigadierOpenAssignmentDropdownId.value = operationId;
}

function closeBrigadierAssignmentDropdown() {
  clearBrigadierAssignmentDropdownCloseTimeout();
  brigadierOpenAssignmentDropdownId.value = null;
}

function scheduleBrigadierAssignmentDropdownClose(operationId: number) {
  if (!isBrigadierAssignmentsEditable.value) {
    return;
  }

  clearBrigadierAssignmentDropdownCloseTimeout();
  brigadierDropdownCloseTimeoutId = window.setTimeout(() => {
    if (brigadierOpenAssignmentDropdownId.value === operationId) {
      brigadierOpenAssignmentDropdownId.value = null;
    }
    brigadierDropdownCloseTimeoutId = null;
  }, 120);
}

function isBrigadierAssignmentDropdownOpen(operationId: number): boolean {
  return brigadierOpenAssignmentDropdownId.value === operationId;
}

function getBrigadierAssignmentOptions(assignment: BrigadierOrderAssignment): UserRecord[] {
  const normalizedQuery = normalizeName(assignment.workerName);
  const selectedWorker = brigadierWorkerUsers.value.find(
    (user) => user.id === assignment.workerUserId,
  );
  const selectedWorkerName = normalizeName(selectedWorker?.name ?? "");
  const shouldFilterByQuery =
    normalizedQuery !== "" && normalizedQuery !== selectedWorkerName;

  return [...brigadierWorkerUsers.value]
    .filter(
      (user) =>
        user.id === assignment.workerUserId ||
        !shouldFilterByQuery ||
        normalizeName(user.name).includes(normalizedQuery),
    )
    .sort((left, right) => {
      const leftPriority = left.id === assignment.workerUserId ? 0 : 1;
      const rightPriority = right.id === assignment.workerUserId ? 0 : 1;

      if (leftPriority !== rightPriority) {
        return leftPriority - rightPriority;
      }

      return left.name.localeCompare(right.name, "ru");
    });
}

function selectBrigadierAssignmentWorker(operationId: number, user: UserRecord) {
  if (!isBrigadierAssignmentsEditable.value) {
    return;
  }

  brigadierModalAssignments.value = brigadierModalAssignments.value.map((assignment) =>
    assignment.operationId === operationId
      ? {
          ...assignment,
          workerName: user.name,
          workerUserId: user.id,
        }
      : assignment,
  );
  closeBrigadierAssignmentDropdown();
}

function clearBrigadierAssignment(operationId: number) {
  if (!isBrigadierAssignmentsEditable.value) {
    return;
  }

  brigadierModalAssignments.value = brigadierModalAssignments.value.map((assignment) =>
    assignment.operationId === operationId
      ? {
          ...assignment,
          workerName: "",
          workerUserId: null,
        }
      : assignment,
  );
  openBrigadierAssignmentDropdown(operationId);
}

function clearBrigadierLeatherTypeDropdownCloseTimeout() {
  if (brigadierLeatherTypeDropdownCloseTimeoutId !== null) {
    window.clearTimeout(brigadierLeatherTypeDropdownCloseTimeoutId);
    brigadierLeatherTypeDropdownCloseTimeoutId = null;
  }
}

function openBrigadierLeatherTypeDropdown() {
  if (!isBrigadierLeatherTypeEditable.value) {
    return;
  }

  clearBrigadierLeatherTypeDropdownCloseTimeout();
  isBrigadierLeatherTypeDropdownOpen.value = true;
}

function closeBrigadierLeatherTypeDropdown() {
  clearBrigadierLeatherTypeDropdownCloseTimeout();
  isBrigadierLeatherTypeDropdownOpen.value = false;
}

function scheduleBrigadierLeatherTypeDropdownClose() {
  if (!isBrigadierLeatherTypeEditable.value) {
    return;
  }

  clearBrigadierLeatherTypeDropdownCloseTimeout();
  brigadierLeatherTypeDropdownCloseTimeoutId = window.setTimeout(() => {
    isBrigadierLeatherTypeDropdownOpen.value = false;
    brigadierLeatherTypeDropdownCloseTimeoutId = null;
  }, 120);
}

function getBrigadierLeatherTypeOptions(): LeatherTypeRecord[] {
  const normalizedQuery = normalizeName(brigadierModalLeatherTypeNameDraft.value);
  const selectedLeatherType = activeLeatherTypes.value.find(
    (item) => String(item.id) === brigadierModalLeatherTypeId.value,
  );
  const selectedLeatherTypeName = normalizeName(selectedLeatherType?.name ?? "");
  const shouldFilterByQuery =
    normalizedQuery !== "" && normalizedQuery !== selectedLeatherTypeName;

  return [...activeLeatherTypes.value]
    .filter(
      (item) =>
        String(item.id) === brigadierModalLeatherTypeId.value ||
        !shouldFilterByQuery ||
        normalizeName(item.name).includes(normalizedQuery),
    )
    .sort((left, right) => {
      const leftPriority =
        String(left.id) === brigadierModalLeatherTypeId.value ? 0 : 1;
      const rightPriority =
        String(right.id) === brigadierModalLeatherTypeId.value ? 0 : 1;

      if (leftPriority !== rightPriority) {
        return leftPriority - rightPriority;
      }

      return left.name.localeCompare(right.name, "ru");
    });
}

function selectBrigadierLeatherType(leatherTypeId: number | null) {
  if (!isBrigadierLeatherTypeEditable.value) {
    return;
  }

  brigadierModalLeatherTypeId.value =
    leatherTypeId === null ? "" : String(leatherTypeId);
  brigadierModalLeatherTypeNameDraft.value =
    leatherTypeId === null
      ? ""
      : activeLeatherTypes.value.find((item) => item.id === leatherTypeId)?.name ?? "";
  closeBrigadierLeatherTypeDropdown();
}

function clearBrigadierLeatherType() {
  if (!isBrigadierLeatherTypeEditable.value) {
    return;
  }

  brigadierModalLeatherTypeId.value = "";
  brigadierModalLeatherTypeNameDraft.value = "";
  openBrigadierLeatherTypeDropdown();
}

function getBrigadierAssignmentError(assignment: BrigadierOrderAssignment): string {
  if (assignment.workerUserId !== null) {
    return "";
  }

  return assignment.workerName.trim() ? "Выберите исполнителя из списка." : "";
}

function scrollToBrigadierSaveIssue() {
  const selector = brigadierSaveIssue.value?.selector;

  if (!selector) {
    return;
  }

  const target = document.querySelector<HTMLElement>(selector);

  if (!target) {
    return;
  }

  target.scrollIntoView({
    behavior: "smooth",
    block: "center",
    inline: "nearest",
  });

  if (target instanceof HTMLInputElement || target instanceof HTMLButtonElement) {
    target.focus({ preventScroll: true });
  }
}

function formatDuration(totalMinutes: number): string {
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;

  if (hours === 0) {
    return `${minutes} мин`;
  }

  if (minutes === 0) {
    return `${hours} ч`;
  }

  return `${hours} ч ${minutes} мин`;
}

function formatPlannedCompletionDate(value: string | null): string {
  if (!value) {
    return "—";
  }

  const [year, month, day] = value.split("-");
  return year && month && day ? `${day}.${month}.${year}` : value;
}

function isWorkOrderOverdue(order: WorkOrderSummary): boolean {
  if (
    !order.plannedCompletionDate ||
    order.completedAtTs !== null ||
    order.deletedAtTs !== null
  ) {
    return false;
  }

  const today = new Date();
  const todayIso = [
    today.getFullYear(),
    String(today.getMonth() + 1).padStart(2, "0"),
    String(today.getDate()).padStart(2, "0"),
  ].join("-");
  return order.plannedCompletionDate < todayIso;
}

function formatTimerDuration(totalMs: number): string {
  const totalSeconds = Math.max(0, Math.floor(totalMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;

  return [hours, minutes, seconds]
    .map((value) => String(value).padStart(2, "0"))
    .join(":");
}

function calculateAverageDuration(totalMs: number, quantity: number): number {
  return quantity > 0 ? Math.floor(totalMs / quantity) : 0;
}

function formatDurationCompact(totalMs: number): string {
  const totalMinutes = Math.max(0, Math.floor(totalMs / 60000));
  const hours = Math.floor(totalMinutes / 60);
  const minutes = totalMinutes % 60;

  if (hours === 0) {
    return `${minutes}м`;
  }

  if (minutes === 0) {
    return `${hours}ч`;
  }

  return `${hours}ч ${minutes}м`;
}

function formatPercentage(value: number): string {
  return `${Math.round(value * 100)}%`;
}

function formatStatisticsDate(value: string): string {
  const [year, month, day] = value.split("-");
  return `${day}.${month}`;
}

function parseOrderIdFromTimerId(timerId: string): number | null {
  const parts = timerId.split(":");
  if (parts.length === 4 && parts[0] === "worker" && parts[1] === "operation") {
    return Number.parseInt(parts[2], 10);
  }
  return null;
}

function parseOperationIdFromTimerId(timerId: string): number | null {
  const parts = timerId.split(":");
  if (parts.length === 4 && parts[0] === "worker" && parts[1] === "operation") {
    return Number.parseInt(parts[3], 10);
  }
  return null;
}

function getStatisticsStackSegmentStyle(totalMs: number, chartMax: number, color: string): string {
  const heightPercent = chartMax > 0 ? (totalMs / chartMax) * 100 : 0;
  return `height: ${heightPercent}%; background: ${color};`;
}

function getStatisticsBarStyle(totalMs: number, chartMax: number): string {
  const widthPercent = chartMax > 0 ? (totalMs / chartMax) * 100 : 0;
  return `width: ${widthPercent}%;`;
}

async function selectStatisticsPeriod(days: (typeof statisticsPeriodOptions)[number]) {
  if (
    statisticsPeriodMode.value === "preset" &&
    statisticsPeriodDays.value === days &&
    statisticsOverview.value
  ) {
    return;
  }

  statisticsPeriodMode.value = "preset";
  statisticsPeriodDays.value = days;
  syncStatisticsDateRangeToDays(days);
  if (canViewStatistics.value) {
    await loadStatistics();
  }
}

function selectCustomStatisticsPeriod() {
  statisticsPeriodMode.value = "custom";
}

async function applyCustomStatisticsPeriod() {
  statisticsPeriodMode.value = "custom";
  if (canViewStatistics.value) {
    await loadStatistics();
  }
}

function estimateWorkOrderMinutes(
  quantity: number,
  assignments: BrigadierOrderAssignment[],
): number {
  const baseMinutes = assignments.reduce(
    (total, assignment, index) =>
      total + 18 + Math.min(10, assignment.operationLabel.length % 11) + index,
    0,
  );

  return baseMinutes * quantity;
}

function requestBrigadierOrderSave() {
  if (!isBrigadierSaveAvailable.value) {
    return;
  }

  if (!brigadierModalCanSave.value || !brigadierModalProduct.value) {
    scrollToBrigadierSaveIssue();
    return;
  }

  isBrigadierSaveConfirmOpen.value = true;
}

function closeBrigadierSaveConfirm() {
  if (brigadierSaveLoading.value) {
    return;
  }

  isBrigadierSaveConfirmOpen.value = false;
}

async function saveBrigadierOrder() {
  if (!isBrigadierSaveAvailable.value) {
    closeBrigadierSaveConfirm();
    return;
  }

  if (!brigadierModalCanSave.value || !brigadierModalProduct.value) {
    closeBrigadierSaveConfirm();
    scrollToBrigadierSaveIssue();
    return;
  }

  brigadierSaveLoading.value = true;
  brigadierModalError.value = "";

  const quantity = Number.parseInt(brigadierModalQuantity.value, 10);
  const leatherTypeId = brigadierModalLeatherTypeId.value
    ? Number.parseInt(brigadierModalLeatherTypeId.value, 10)
    : null;
  const assignments = brigadierModalAssignments.value.map((assignment) => ({ ...assignment }));
  const estimatedMinutes = estimateWorkOrderMinutes(quantity, assignments);
  const isCreateMode = brigadierModalMode.value === "create";
  const shouldUpdatePlannedCompletionDate =
    !isCreateMode &&
    Boolean(brigadierModalPlannedCompletionDate.value) &&
    isBrigadierPlannedCompletionDateChanged.value;

  try {
    if (shouldUpdatePlannedCompletionDate && brigadierCurrentOrder.value) {
      await updateWorkOrderPlannedCompletionDate(
        brigadierCurrentOrder.value.id,
        brigadierModalPlannedCompletionDate.value,
      );
    }

    if (isQualityControlOrderModal.value && brigadierCurrentOrder.value) {
      await acceptWorkOrderQualityControl(
        brigadierCurrentOrder.value.id,
        Number.parseInt(brigadierModalDefectQuantity.value, 10),
      );
      brigadierTab.value = "completed";
    } else if (
      !isCreateMode &&
      brigadierCurrentOrder.value &&
      (isBrigadierOrderAttributesEditable.value ||
        isBrigadierAssignmentsEditable.value)
    ) {
      await updateWorkOrderAssignments(brigadierCurrentOrder.value.id, {
        leather_type_id: leatherTypeId,
        quantity,
        estimated_minutes: estimatedMinutes,
        assignments: assignments.map((assignment) => ({
          operation_id: assignment.operationId,
          worker_user_id: assignment.workerUserId,
        })),
      });
    } else if (isCreateMode) {
      await createWorkOrder({
        order_number: brigadierModalOrderNumber.value.trim(),
        planned_completion_date: brigadierModalPlannedCompletionDate.value,
        product_id: brigadierModalProduct.value.id,
        leather_type_id: leatherTypeId,
        quantity,
        estimated_minutes: estimatedMinutes,
        assignments: assignments.map((assignment) => ({
          operation_id: assignment.operationId,
          worker_user_id: assignment.workerUserId,
        })),
      });
    }

    if (isCreateMode) {
      brigadierTab.value = "created";
    }
    await loadWorkOrders();
    closeBrigadierOrderModal();
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    isBrigadierSaveConfirmOpen.value = false;
    brigadierModalError.value = getErrorMessage(error, "Не удалось сохранить заказ.");
  } finally {
    brigadierSaveLoading.value = false;
  }
}

function generateNextWorkOrderNumber(orders: WorkOrderSummary[]): string {
  const maxOrderIndex = orders.reduce((maxValue, order) => {
    const match = order.orderNumber.match(/(\d+)$/);

    if (!match) {
      return maxValue;
    }

    return Math.max(maxValue, Number.parseInt(match[1], 10));
  }, 0);

  return `FC-${String(maxOrderIndex + 1).padStart(4, "0")}`;
}

async function persistUserChanges(user: UserRecord) {
  if (!editingUserDraft.value) {
    return;
  }

  usersError.value = "";

  try {
    let savedUser: UserRecord;
    if (user.isNew) {
      savedUser = await createUserApi({
        name: editingUserDraft.value.name.trim(),
        phone: editingUserDraft.value.phone.trim(),
        roles: editingUserDraft.value.roles,
        is_active: editingUserDraft.value.isActive,
        author_user_id: editingUserDraft.value.authorUserId,
      });
    } else {
      savedUser = await updateUserApi(user.id, {
        name: editingUserDraft.value.name.trim(),
        phone: editingUserDraft.value.phone.trim(),
        roles: editingUserDraft.value.roles,
        is_active: editingUserDraft.value.isActive,
        author_user_id: editingUserDraft.value.authorUserId,
      });
    }
    if (savedUser.id === currentSession.value?.userId) {
      currentSession.value = await fetchCurrentSession();
    }

    editingUserId.value = null;
    editingUserDraft.value = null;
    await loadUsers();
    await loadProducts();
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    usersError.value = getErrorMessage(error, "Не удалось сохранить пользователя.");
  }
}

async function removeUser(user: UserRecord) {
  if (user.isNew) {
    users.value = users.value.filter((item) => item.id !== user.id);
    if (editingUserId.value === user.id) {
      editingUserId.value = null;
      editingUserDraft.value = null;
    }
    closeUserDeleteConfirmation();
    return;
  }

  usersError.value = "";

  try {
    await deleteUserApi(user.id);
    closeUserDeleteConfirmation();
    if (editingUserId.value === user.id) {
      editingUserId.value = null;
      editingUserDraft.value = null;
    }
    await loadUsers();
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    usersError.value = getErrorMessage(error, "Не удалось удалить пользователя.");
  }
}

async function handleResetUserPassword(user: UserRecord) {
  if (isUserLocked(user.id)) {
    return;
  }

  usersError.value = "";

  try {
    await resetUserPasswordApi(user.id);
    await loadUsers();

    if (currentSession.value?.userId === user.id) {
      redirectToAuth("Пароль текущего пользователя был сброшен. Войдите снова.");
    }
  } catch (error) {
    if (isUnauthorizedError(error)) {
      redirectToAuth(getErrorMessage(error, "Требуется аутентификация."));
      return;
    }
    usersError.value = getErrorMessage(error, "Не удалось сбросить пароль.");
  }
}
</script>

<template>
  <main class="page" :class="{ 'page--printing': printableWorkOrder }">
    <section v-if="authInitializing" class="auth-shell">
      <div class="auth-card">
        <p class="section-label">FlowCraft</p>
        <h2>Проверка сессии</h2>
        <p class="auth-card__description">Подготавливаю рабочее пространство пользователя.</p>
      </div>
    </section>

    <section v-else-if="!currentSession" class="auth-shell">
      <form class="auth-card" @submit.prevent="void submitAuthentication()">
        <div class="auth-card__head">
          <div class="brand-logo-frame brand-logo-frame--auth">
            <img
              :src="flowcraftLogoUrl"
              alt="FlowCraft"
              class="brand-logo brand-logo--auth"
            />
          </div>
          <div>
            <p class="section-label">Аутентификация</p>
            <h2>{{ authRequiresPasswordSetup ? "Задайте пароль" : "Вход в систему" }}</h2>
            <p class="auth-card__description">
              {{
                authRequiresPasswordSetup
                  ? `Для пользователя ${authSetupUserName || authPhone} пароль еще не задан.`
                  : "Введите номер телефона и пароль пользователя."
              }}
            </p>
          </div>
        </div>

        <label class="field">
          <span class="field__label">Номер телефона</span>
          <input
            v-model="authPhone"
            type="text"
            class="text-input"
            autocomplete="username"
            placeholder="+7 999 123-45-67"
            :readonly="authRequiresPasswordSetup"
          />
        </label>

        <label v-if="!authRequiresPasswordSetup" class="field">
          <span class="field__label">Пароль</span>
          <input
            v-model="authPassword"
            type="password"
            class="text-input"
            autocomplete="current-password"
            placeholder="Введите пароль"
          />
        </label>

        <template v-else>
          <label class="field">
            <span class="field__label">Новый пароль</span>
            <input
              v-model="authNewPassword"
              type="password"
              class="text-input"
              autocomplete="new-password"
              placeholder="Не менее 8 символов"
            />
          </label>

          <label class="field">
            <span class="field__label">Подтверждение пароля</span>
            <input
              v-model="authConfirmPassword"
              type="password"
              class="text-input"
              autocomplete="new-password"
              placeholder="Повторите пароль"
            />
          </label>
        </template>

        <p v-if="authError" class="field-error">{{ authError }}</p>

        <div class="auth-card__actions">
          <button type="submit" class="primary-button" :disabled="authSubmitting">
            <span class="button-content">
              <span class="button-icon button-icon--key" aria-hidden="true" />
              <span>
                {{
                  authSubmitting
                    ? "Обработка..."
                    : authRequiresPasswordSetup
                      ? "Сохранить пароль"
                      : "Войти"
                }}
              </span>
            </span>
          </button>
        </div>
      </form>
    </section>

    <section v-else class="shell">
      <header class="header">
        <nav class="tabs" aria-label="Разделы">
          <button
            v-for="tab in availableTabs"
            :key="tab.id"
            type="button"
            class="tab-button"
            :class="{ 'tab-button--active': activeTab === tab.id }"
            @click="setActiveTab(tab.id)"
          >
            <span class="button-content">
              <span class="role-icon" :class="`role-icon--${tab.icon}`" aria-hidden="true" />
              <span>{{ tab.label }}</span>
            </span>
          </button>
        </nav>

        <div class="current-user-card">
          <div class="current-user-card__identity">
            <span class="section-label">Текущий пользователь</span>
            <strong>{{ currentSession.userName }}</strong>
          </div>
          <div class="current-user-card__actions">
            <button type="button" class="ghost-button" @click="openChangePasswordModal">
              <span class="button-content">
                <span class="button-icon button-icon--key" aria-hidden="true" />
                <span class="current-user-card__action-label">Изменить пароль</span>
              </span>
            </button>
            <button type="button" class="ghost-button" @click="void handleLogout()">
              <span class="button-content">
                <span class="button-icon button-icon--logout" aria-hidden="true" />
                <span class="current-user-card__action-label">Выйти</span>
              </span>
            </button>
          </div>
        </div>

        <div class="brand-block">
          <div class="brand-logo-frame">
            <img
              :src="flowcraftLogoUrl"
              alt="FlowCraft"
              class="brand-logo"
            />
          </div>
        </div>
      </header>

      <section v-if="activeTab === 'worker'">
        <article class="constructor-panel worker-panel">
          <div class="panel-head worker-panel__head">
            <div>
              <h2>Учет времени исполнителя</h2>
              <p class="worker-panel__subtitle">
                {{
                  currentWorker
                    ? `Текущий исполнитель: ${currentWorker.name}`
                    : "Нет активного исполнителя"
                }}
              </p>
            </div>

            <div class="worker-panel__actions">
              <button
                type="button"
                class="secondary-button"
                :disabled="!currentWorker"
                @click="void openWorkerQrScanner()"
              >
                <span class="button-content">
                  <span class="button-icon button-icon--search" aria-hidden="true" />
                  <span>Сканировать QR</span>
                </span>
              </button>

              <button
                type="button"
                class="primary-button"
                :disabled="!currentWorker || workerTimerSubmitting"
                @click="isWorkerDayActive ? requestEndWorkerDay() : void startWorkerDay()"
              >
                <span class="button-content">
                  <span
                    class="button-icon"
                    :class="isWorkerDayActive ? 'button-icon--stop' : 'button-icon--play'"
                    aria-hidden="true"
                  />
                  <span>{{ isWorkerDayActive ? "Закончить рабочий день" : "Начать рабочий день" }}</span>
                </span>
              </button>
            </div>
          </div>

          <div v-if="!currentWorker" class="empty-table-state">
            <p>Добавьте активного пользователя с ролью исполнителя, чтобы открыть рабочий экран.</p>
          </div>

          <template v-else>
            <div class="worker-summary">
              <div class="worker-summary__card">
                <span class="section-label">Статус дня</span>
                <strong>{{ isWorkerDayActive ? "Смена идет" : "Смена не начата" }}</strong>
                <span class="worker-summary__value">{{ formatTimerDuration(workerDayElapsedMs) }}</span>
              </div>

              <div v-if="shouldShowWorkerActiveTimerCard" class="worker-summary__card">
                <span class="section-label">Активный таймер</span>
                <strong>{{ workerActiveTimer?.label ?? "Нет активного таймера" }}</strong>
                <span class="worker-summary__value">
                  {{
                    workerActiveTimer
                      ? formatTimerDuration(getWorkerTimerElapsedMs(workerActiveTimer.id))
                      : "00:00:00"
                  }}
                </span>
              </div>
            </div>

            <div class="worker-timer-bar">
              <button
                v-for="timer in workerPrimaryTimers"
                :key="timer.id"
                type="button"
                class="worker-timer-button"
                :class="{ 'worker-timer-button--active': isWorkerTimerActive(timer.id) }"
                :disabled="!isWorkerDayActive || workerTimerSubmitting"
                @click="void activateWorkerTimer(timer.id)"
              >
                <span class="worker-timer-button__heading">
                  <span
                    class="button-icon"
                    :class="`button-icon--timer-${timer.kind}`"
                    aria-hidden="true"
                  />
                  <span class="worker-timer-button__label">{{ timer.label }}</span>
                </span>
                <span class="worker-timer-button__value">
                  {{ formatTimerDuration(getWorkerTimerElapsedMs(timer.id)) }}
                </span>
              </button>

              <button
                v-if="workerIdleTimer"
                type="button"
                class="worker-timer-button worker-timer-button--secondary"
                :class="{ 'worker-timer-button--active': isWorkerTimerActive(workerIdleTimer.id) }"
                :disabled="!isWorkerDayActive || workerTimerSubmitting"
                @click="void activateWorkerTimer(workerIdleTimer.id)"
              >
                <span class="worker-timer-button__heading">
                  <span
                    class="button-icon"
                    :class="`button-icon--timer-${workerIdleTimer.kind}`"
                    aria-hidden="true"
                  />
                  <span class="worker-timer-button__label">{{ workerIdleTimer.label }}</span>
                </span>
                <span class="worker-timer-button__value">
                  {{ formatTimerDuration(getWorkerTimerElapsedMs(workerIdleTimer.id)) }}
                </span>
              </button>
            </div>

            <div class="toolbar worker-filter-toolbar">
              <label class="field field--inline">
                <span class="field__label">Отображать операции</span>
                <div class="assignment-input-wrap worker-status-filter">
                  <input
                    :value="workerAssignmentStatusFilterLabel"
                    type="text"
                    class="text-input text-input--selectlike worker-filter-select"
                    readonly
                    autocomplete="off"
                    @focus="openWorkerAssignmentStatusDropdown"
                    @click="openWorkerAssignmentStatusDropdown"
                    @blur="scheduleWorkerAssignmentStatusDropdownClose"
                  />
                  <span class="worker-status-filter__chevron" aria-hidden="true" />
                  <div
                    v-if="isWorkerAssignmentStatusDropdownOpen"
                    class="assignment-dropdown worker-status-filter__dropdown"
                  >
                    <button
                      v-for="option in workerAssignmentStatusOptions"
                      :key="option.value"
                      type="button"
                      class="assignment-dropdown__option"
                      :class="{
                        'assignment-dropdown__option--selected':
                          workerAssignmentStatusFilter === option.value,
                      }"
                      @mousedown.prevent
                      @click="selectWorkerAssignmentStatusFilter(option.value)"
                    >
                      <span>{{ option.label }}</span>
                    </button>
                  </div>
                </div>
              </label>
            </div>

            <div v-if="workerAssignmentsError" class="banner banner--error">
              <p>{{ workerAssignmentsError }}</p>
              <button type="button" class="ghost-button" @click="void loadWorkerWorkspace()">
                <span class="button-content">
                  <span class="button-icon button-icon--refresh" aria-hidden="true" />
                  <span>Повторить</span>
                </span>
              </button>
            </div>

            <div v-else-if="workerAssignmentsLoading" class="banner">
              <p>Загрузка назначенных операций...</p>
            </div>

            <template v-else>
              <div v-if="workerOrderFocusMessage" class="banner">
                <p>{{ workerOrderFocusMessage }}</p>
              </div>

              <div
                v-if="workerTimerGroups.length === 0 && !workerOrderFocusMessage"
                class="empty-table-state"
              >
                <p>{{ getWorkerAssignmentsEmptyMessage() }}</p>
              </div>

              <div v-else class="worker-groups">
              <section
                v-for="group in workerTimerGroups"
                :key="group.groupKey"
                class="worker-group"
                :class="{
                  'worker-group--focused': workerOrderRouteId === Number(group.groupKey),
                }"
                :data-worker-order-id="group.groupKey"
              >
                <button
                  type="button"
                  class="worker-group__head"
                  @click="toggleWorkerGroup(group.groupKey)"
                >
                  <span class="worker-group__title">
                    <span class="button-icon button-icon--package" aria-hidden="true" />
                    <h3>
                      {{ group.orderNumber }} · {{ group.productLabel }} ({{ formatWorkerGroupProductMeta(group) }})
                    </h3>
                  </span>
                  <span
                    class="worker-group__chevron"
                    :class="{
                      'worker-group__chevron--expanded':
                        workerGroupExpanded[group.groupKey],
                    }"
                    aria-hidden="true"
                  />
                </button>

                <div
                  v-if="workerGroupExpanded[group.groupKey]"
                  class="worker-group__timers"
                >
                  <div
                    v-for="timer in group.timers"
                    :key="timer.id"
                    class="worker-operation-row"
                  >
                    <button
                      type="button"
                      class="worker-timer-button worker-timer-button--operation"
                      :class="{ 'worker-timer-button--active': isWorkerTimerActive(timer.id) }"
                      :disabled="
                        !isWorkerDayActive ||
                        workerTimerSubmitting ||
                        timer.assignmentStatus !== 'in_work'
                      "
                      @click="void activateWorkerTimer(timer.id)"
                    >
                      <span class="worker-timer-button__meta">
                        <span class="worker-timer-button__heading">
                          <span class="button-icon button-icon--timer-operation" aria-hidden="true" />
                          <span class="worker-timer-button__order">{{ timer.orderNumber }}</span>
                          <span class="worker-timer-button__label">{{ timer.label }}</span>
                        </span>
                      </span>
                      <span class="worker-timer-button__value">
                        {{ formatTimerDuration(getWorkerTimerElapsedMs(timer.id)) }}
                      </span>
                    </button>
                    <div class="worker-operation-row__actions">
                      <button
                        v-if="timer.assignmentStatus === 'in_work'"
                        type="button"
                        class="action-link"
                        :disabled="workerTimerSubmitting"
                        @click="requestWorkerAssignmentStatusChange(timer, 'hidden')"
                      >
                        <span class="button-content">
                          <span class="button-icon button-icon--delete" aria-hidden="true" />
                          <span>Скрыть</span>
                        </span>
                      </button>
                      <button
                        v-if="timer.assignmentStatus === 'in_work'"
                        type="button"
                        class="action-link"
                        :disabled="workerTimerSubmitting"
                        @click="requestWorkerAssignmentStatusChange(timer, 'completed')"
                      >
                        <span class="button-content">
                          <span class="button-icon button-icon--check" aria-hidden="true" />
                          <span>Выполнено</span>
                        </span>
                      </button>
                      <button
                        v-else
                        type="button"
                        class="action-link"
                        :disabled="workerTimerSubmitting"
                        @click="requestWorkerAssignmentStatusChange(timer, 'in_work')"
                      >
                        <span class="button-content">
                          <span class="button-icon button-icon--refresh" aria-hidden="true" />
                          <span>Вернуть в работу</span>
                        </span>
                      </button>
                    </div>
                  </div>
                </div>
              </section>
              </div>
            </template>
          </template>
        </article>
      </section>

      <section v-else-if="activeTab === 'brigadier'">
        <article class="constructor-panel">
          <div class="panel-head panel-head--stacked">
            <div>
              <h2>Управление заказами</h2>
            </div>

            <div
              class="subtabs subtabs--work-orders"
              role="tablist"
              aria-label="Разделы бригадира"
            >
              <button
                type="button"
                class="subtab-button"
                :class="{ 'subtab-button--active': brigadierTab === 'orders' }"
                @click="setBrigadierTab('orders')"
              >
                <span class="button-content">
                  <span class="button-icon button-icon--orders" aria-hidden="true" />
                  <span>Новый заказ</span>
                </span>
              </button>
              <button
                v-for="statusTab in workOrderStatusTabs"
                :key="statusTab.id"
                type="button"
                class="subtab-button"
                :class="{ 'subtab-button--active': brigadierTab === statusTab.id }"
                @click="setBrigadierTab(statusTab.id)"
              >
                <span class="button-content">
                  <span
                    class="button-icon"
                    :class="`button-icon--${statusTab.icon}`"
                    aria-hidden="true"
                  />
                  <span>{{ statusTab.label }}</span>
                </span>
              </button>
            </div>
          </div>

          <template v-if="brigadierTab !== 'orders'">
            <div v-if="brigadierOrdersError" class="banner banner--error">
              <p>{{ brigadierOrdersError }}</p>
              <button type="button" class="ghost-button" @click="loadWorkOrders">
                <span class="button-content">
                  <span class="button-icon button-icon--refresh" aria-hidden="true" />
                  <span>Повторить</span>
                </span>
              </button>
            </div>

            <div v-else-if="brigadierOrdersLoading" class="banner">
              <p>Загрузка заказов...</p>
            </div>

            <div v-else>
              <div class="toolbar work-orders-toolbar">
                <label class="field field--inline">
                  <span class="field__label">Поиск по заказам</span>
                  <div class="filter-input-wrap">
                    <input
                      v-model="workOrderSearchDraft"
                      type="text"
                      class="text-input text-input--with-action"
                      placeholder="Номер заказа или изделие"
                      @keydown.enter.prevent="applyWorkOrderSearch"
                    />
                    <button
                      v-if="workOrderSearchDraft || workOrderFilter"
                      type="button"
                      class="field-action"
                      aria-label="Очистить поиск"
                      title="Очистить поиск"
                      @click="clearWorkOrderSearch"
                    >
                      <span class="field-action__icon" aria-hidden="true" />
                    </button>
                  </div>
                </label>
              </div>

              <div v-if="filteredWorkOrders.length === 0" class="empty-table-state">
                <p>Заказы по выбранным условиям не найдены.</p>
              </div>

              <div v-else class="table-wrap desktop-only work-orders-table-wrap">
                <table class="products-table brigadier-table">
                  <thead>
                    <tr>
                      <th>
                        <button
                          type="button"
                          class="sort-header-button"
                          :class="{
                            'sort-header-button--active':
                              isWorkOrderSortFieldActive('order_number'),
                          }"
                          @click="toggleWorkOrderSort('order_number')"
                        >
                          <span>Номер заказа</span>
                          <span
                            class="sort-header-button__icon"
                            :class="`sort-header-button__icon--${getWorkOrderSortDirection('order_number')}`"
                            aria-hidden="true"
                          />
                        </button>
                      </th>
                      <th>
                        <button
                          type="button"
                          class="sort-header-button"
                          :class="{
                            'sort-header-button--active':
                              isWorkOrderSortFieldActive('name'),
                          }"
                          @click="toggleWorkOrderSort('name')"
                        >
                          <span>Наименование</span>
                          <span
                            class="sort-header-button__icon"
                            :class="`sort-header-button__icon--${getWorkOrderSortDirection('name')}`"
                            aria-hidden="true"
                          />
                        </button>
                      </th>
                      <th>Вид кожи</th>
                      <th>Количество изделий</th>
                      <th>
                        <button
                          type="button"
                          class="sort-header-button"
                          :class="{
                            'sort-header-button--active':
                              isWorkOrderSortFieldActive('planned_completion'),
                          }"
                          @click="toggleWorkOrderSort('planned_completion')"
                        >
                          <span>Плановая дата сдачи</span>
                          <span
                            class="sort-header-button__icon"
                            :class="`sort-header-button__icon--${getWorkOrderSortDirection('planned_completion')}`"
                            aria-hidden="true"
                          />
                        </button>
                      </th>
                      <th v-if="workOrderStatusTab === 'quality_control'">
                        <button
                          type="button"
                          class="sort-header-button"
                          :class="{
                            'sort-header-button--active':
                              isWorkOrderSortFieldActive('quality_control'),
                          }"
                          @click="toggleWorkOrderSort('quality_control')"
                        >
                          <span>Дата передачи в ОТК</span>
                          <span
                            class="sort-header-button__icon"
                            :class="`sort-header-button__icon--${getWorkOrderSortDirection('quality_control')}`"
                            aria-hidden="true"
                          />
                        </button>
                      </th>
                      <template v-else>
                        <th>
                          <button
                            type="button"
                            class="sort-header-button"
                            :class="{
                              'sort-header-button--active':
                                isWorkOrderSortFieldActive('created'),
                            }"
                            @click="toggleWorkOrderSort('created')"
                          >
                            <span>Время создания</span>
                            <span
                              class="sort-header-button__icon"
                              :class="`sort-header-button__icon--${getWorkOrderSortDirection('created')}`"
                              aria-hidden="true"
                            />
                          </button>
                        </th>
                        <th v-if="workOrderStatusTab !== 'created'">
                          <button
                            type="button"
                            class="sort-header-button"
                            :class="{
                              'sort-header-button--active':
                                isWorkOrderSortFieldActive('taken'),
                            }"
                            @click="toggleWorkOrderSort('taken')"
                          >
                            <span>Время взятия в работу</span>
                            <span
                              class="sort-header-button__icon"
                              :class="`sort-header-button__icon--${getWorkOrderSortDirection('taken')}`"
                              aria-hidden="true"
                            />
                          </button>
                        </th>
                        <th v-if="workOrderStatusTab === 'deleted'">
                          <button
                            type="button"
                            class="sort-header-button"
                            :class="{
                              'sort-header-button--active':
                                isWorkOrderSortFieldActive('completed'),
                            }"
                            @click="toggleWorkOrderSort('completed')"
                          >
                            <span>Время выполнения</span>
                            <span
                              class="sort-header-button__icon"
                              :class="`sort-header-button__icon--${getWorkOrderSortDirection('completed')}`"
                              aria-hidden="true"
                            />
                          </button>
                        </th>
                        <th v-if="workOrderStatusTab === 'completed'">
                          <button
                            type="button"
                            class="sort-header-button"
                            :class="{
                              'sort-header-button--active':
                                isWorkOrderSortFieldActive('completed'),
                            }"
                            @click="toggleWorkOrderSort('completed')"
                          >
                            <span>Время проведения ОТК</span>
                            <span
                              class="sort-header-button__icon"
                              :class="`sort-header-button__icon--${getWorkOrderSortDirection('completed')}`"
                              aria-hidden="true"
                            />
                          </button>
                        </th>
                        <th v-if="workOrderStatusTab === 'completed'">
                          <button
                            type="button"
                            class="sort-header-button"
                            :class="{
                              'sort-header-button--active':
                                isWorkOrderSortFieldActive('defect'),
                            }"
                            @click="toggleWorkOrderSort('defect')"
                          >
                            <span>Количество брака</span>
                            <span
                              class="sort-header-button__icon"
                              :class="`sort-header-button__icon--${getWorkOrderSortDirection('defect')}`"
                              aria-hidden="true"
                            />
                          </button>
                        </th>
                        <th>Исполнители</th>
                        <th>Суммарное время</th>
                      </template>
                      <th>Действия</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="order in filteredWorkOrders" :key="order.id">
                      <td>{{ order.orderNumber }}</td>
                      <td>{{ order.productName }}</td>
                      <td>{{ order.leatherTypeName ?? "вид кожи не указан" }}</td>
                      <td>{{ order.quantity }} шт.</td>
                      <td
                        :class="{
                          'work-order-deadline--overdue': isWorkOrderOverdue(order),
                        }"
                      >
                        {{ formatPlannedCompletionDate(order.plannedCompletionDate) }}
                      </td>
                      <td v-if="workOrderStatusTab === 'quality_control'">
                        {{ order.qualityControlAt ?? "—" }}
                      </td>
                      <template v-else>
                        <td>{{ order.createdAt }}</td>
                        <td v-if="workOrderStatusTab !== 'created'">
                          {{ order.takenAt ?? "—" }}
                        </td>
                        <td v-if="workOrderStatusTab === 'deleted'">
                          {{ order.completedAt ?? "—" }}
                        </td>
                        <td v-if="workOrderStatusTab === 'completed'">
                          {{ order.completedAt ?? "—" }}
                        </td>
                        <td v-if="workOrderStatusTab === 'completed'">
                          {{ order.defectQuantity }} шт.
                        </td>
                        <td>
                          <button
                            type="button"
                            class="secondary-button"
                            @click="openBrigadierManageOrder(order)"
                          >
                            <span class="button-content">
                              <span class="button-icon button-icon--people" aria-hidden="true" />
                              <span>{{ order.assignmentsCount }} назначений</span>
                            </span>
                          </button>
                        </td>
                        <td>
                          <button
                            type="button"
                            class="duration-badge duration-badge--button"
                            :aria-label="`Показать детализацию времени заказа ${order.orderNumber}`"
                            @click="void openWorkOrderTimeBreakdown(order)"
                          >
                            {{ formatDuration(order.totalSpentMinutes) }}
                          </button>
                        </td>
                      </template>
                      <td>
                        <div class="table-actions">
                          <button
                            v-if="workOrderStatusTab === 'quality_control'"
                            type="button"
                            class="action-link"
                            @click="openBrigadierManageOrder(order)"
                          >
                            <span class="button-content">
                              <span class="button-icon button-icon--edit" aria-hidden="true" />
                              <span>Изменить срок</span>
                            </span>
                          </button>
                          <button
                            v-if="workOrderStatusTab !== 'quality_control'"
                            type="button"
                            class="action-link"
                            :disabled="isWorkOrderPrintBusy(order.id)"
                            @click="void printWorkOrder(order)"
                          >
                            <span class="button-content">
                              <span class="button-icon button-icon--print" aria-hidden="true" />
                              <span>{{ isWorkOrderPrintBusy(order.id) ? "Подготовка..." : "Печать" }}</span>
                            </span>
                          </button>
                          <button
                            v-if="workOrderStatusTab === 'created'"
                            type="button"
                            class="action-link"
                            :disabled="isWorkOrderBusy(order.id)"
                            @click="void toggleWorkOrderTakenStatus(order, true)"
                          >
                            <span class="button-content">
                              <span class="button-icon button-icon--play" aria-hidden="true" />
                              <span>Взять в работу</span>
                            </span>
                          </button>
                          <button
                            v-if="workOrderStatusTab === 'in_work'"
                            type="button"
                            class="action-link"
                            :disabled="isWorkOrderBusy(order.id)"
                            @click="openWorkOrderActionConfirm(order, 'send_to_quality_control')"
                          >
                            <span class="button-content">
                              <span class="button-icon button-icon--check" aria-hidden="true" />
                              <span>Передать в ОТК</span>
                            </span>
                          </button>
                          <button
                            v-if="workOrderStatusTab === 'quality_control'"
                            type="button"
                            class="action-link"
                            :disabled="!canAcceptQualityControl || isWorkOrderBusy(order.id)"
                            @click="openQualityControlOrder(order)"
                          >
                            <span class="button-content">
                              <span class="button-icon button-icon--check" aria-hidden="true" />
                              <span>Принять</span>
                            </span>
                          </button>
                          <button
                            v-if="workOrderStatusTab === 'quality_control'"
                            type="button"
                            class="action-link"
                            :disabled="isWorkOrderBusy(order.id)"
                            @click="openWorkOrderActionConfirm(order, 'return_to_work')"
                          >
                            <span class="button-content">
                              <span class="button-icon button-icon--in-work" aria-hidden="true" />
                              <span>Вернуть в работу</span>
                            </span>
                          </button>
                          <button
                            v-if="workOrderStatusTab === 'in_work'"
                            type="button"
                            class="action-link"
                            :disabled="isWorkOrderBusy(order.id)"
                            @click="openWorkOrderActionConfirm(order, 'return_to_created')"
                          >
                            <span class="button-content">
                              <span class="button-icon button-icon--refresh" aria-hidden="true" />
                              <span>Вернуть в созданные</span>
                            </span>
                          </button>
                          <button
                            v-if="workOrderStatusTab === 'completed'"
                            type="button"
                            class="action-link"
                            :disabled="isWorkOrderBusy(order.id)"
                            @click="openWorkOrderActionConfirm(order, 'return_to_quality_control')"
                          >
                            <span class="button-content">
                              <span class="button-icon button-icon--check" aria-hidden="true" />
                              <span>Вернуть на ОТК</span>
                            </span>
                          </button>
                          <button
                            v-if="workOrderStatusTab === 'deleted'"
                            type="button"
                            class="action-link"
                            :disabled="isWorkOrderBusy(order.id)"
                            @click="openWorkOrderActionConfirm(order, 'restore')"
                          >
                            <span class="button-content">
                              <span class="button-icon button-icon--refresh" aria-hidden="true" />
                              <span>Восстановить</span>
                            </span>
                          </button>
                          <button
                            v-if="workOrderStatusTab !== 'deleted' && workOrderStatusTab !== 'quality_control'"
                            type="button"
                            class="action-link action-link--danger"
                            :disabled="isWorkOrderBusy(order.id)"
                            @click="openWorkOrderActionConfirm(order, 'delete')"
                          >
                            <span class="button-content">
                              <span class="button-icon button-icon--delete" aria-hidden="true" />
                              <span>Удалить</span>
                            </span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div
                v-if="filteredWorkOrders.length > 0"
                class="mobile-list mobile-only work-orders-mobile-list"
              >
                <article
                  v-for="order in filteredWorkOrders"
                  :key="`mobile-order-${order.id}`"
                  class="mobile-card"
                >
                  <div class="mobile-card__head">
                    <strong>{{ order.orderNumber }}</strong>
                    <button
                      type="button"
                      class="duration-badge duration-badge--button"
                      :aria-label="`Показать детализацию времени заказа ${order.orderNumber}`"
                      @click="void openWorkOrderTimeBreakdown(order)"
                    >
                      {{ formatDuration(order.totalSpentMinutes) }}
                    </button>
                  </div>
                  <div class="mobile-card__meta">
                    <span>{{ order.productName }}</span>
                    <span>Вид кожи: {{ order.leatherTypeName ?? "вид кожи не указан" }}</span>
                    <span>Количество изделий: {{ order.quantity }} шт.</span>
                    <span
                      :class="{
                        'work-order-deadline--overdue': isWorkOrderOverdue(order),
                      }"
                    >
                      Плановая сдача:
                      {{ formatPlannedCompletionDate(order.plannedCompletionDate) }}
                    </span>
                    <span>Создан: {{ order.createdAt }}</span>
                    <span v-if="workOrderStatusTab !== 'created'">
                      В работе с {{ order.takenAt ?? "—" }}
                    </span>
                    <span v-if="workOrderStatusTab === 'quality_control'">
                      Передан в ОТК: {{ order.qualityControlAt ?? "—" }}
                    </span>
                    <span v-if="workOrderStatusTab === 'deleted'">
                      Выполнен: {{ order.completedAt ?? "—" }}
                    </span>
                    <span v-if="workOrderStatusTab === 'completed'">
                      ОТК проведен: {{ order.completedAt ?? "—" }}
                    </span>
                    <span v-if="workOrderStatusTab === 'completed'">
                      Брак: {{ order.defectQuantity }} шт.
                    </span>
                    <span v-if="workOrderStatusTab === 'deleted'">
                      Удален: {{ order.deletedAt ?? "—" }}
                    </span>
                  </div>
                  <button
                    type="button"
                    class="secondary-button"
                    @click="openBrigadierManageOrder(order)"
                  >
                    <span class="button-content">
                      <span class="button-icon button-icon--people" aria-hidden="true" />
                      <span>{{ order.assignmentsCount }} назначений</span>
                    </span>
                  </button>
                  <button
                    v-if="workOrderStatusTab !== 'quality_control'"
                    type="button"
                    class="action-link"
                    :disabled="isWorkOrderPrintBusy(order.id)"
                    @click="void printWorkOrder(order)"
                  >
                    <span class="button-content">
                      <span class="button-icon button-icon--print" aria-hidden="true" />
                      <span>{{ isWorkOrderPrintBusy(order.id) ? "Подготовка..." : "Печать" }}</span>
                    </span>
                  </button>
                  <button
                    v-if="workOrderStatusTab === 'created'"
                    type="button"
                    class="action-link"
                    :disabled="isWorkOrderBusy(order.id)"
                    @click="void toggleWorkOrderTakenStatus(order, true)"
                  >
                    <span class="button-content">
                      <span class="button-icon button-icon--play" aria-hidden="true" />
                      <span>Взять в работу</span>
                    </span>
                  </button>
                  <button
                    v-if="workOrderStatusTab === 'in_work'"
                    type="button"
                    class="action-link"
                    :disabled="isWorkOrderBusy(order.id)"
                    @click="openWorkOrderActionConfirm(order, 'send_to_quality_control')"
                  >
                    <span class="button-content">
                      <span class="button-icon button-icon--check" aria-hidden="true" />
                      <span>Передать в ОТК</span>
                    </span>
                  </button>
                  <button
                    v-if="workOrderStatusTab === 'quality_control'"
                    type="button"
                    class="action-link"
                    :disabled="!canAcceptQualityControl || isWorkOrderBusy(order.id)"
                    @click="openQualityControlOrder(order)"
                  >
                    <span class="button-content">
                      <span class="button-icon button-icon--check" aria-hidden="true" />
                      <span>Принять</span>
                    </span>
                  </button>
                  <button
                    v-if="workOrderStatusTab === 'quality_control'"
                    type="button"
                    class="action-link"
                    :disabled="isWorkOrderBusy(order.id)"
                    @click="openWorkOrderActionConfirm(order, 'return_to_work')"
                  >
                    <span class="button-content">
                      <span class="button-icon button-icon--in-work" aria-hidden="true" />
                      <span>Вернуть в работу</span>
                    </span>
                  </button>
                  <button
                    v-if="workOrderStatusTab === 'in_work'"
                    type="button"
                    class="action-link"
                    :disabled="isWorkOrderBusy(order.id)"
                    @click="openWorkOrderActionConfirm(order, 'return_to_created')"
                  >
                    <span class="button-content">
                      <span class="button-icon button-icon--refresh" aria-hidden="true" />
                      <span>Вернуть в созданные</span>
                    </span>
                  </button>
                  <button
                    v-if="workOrderStatusTab === 'completed'"
                    type="button"
                    class="action-link"
                    :disabled="isWorkOrderBusy(order.id)"
                    @click="openWorkOrderActionConfirm(order, 'return_to_quality_control')"
                  >
                    <span class="button-content">
                      <span class="button-icon button-icon--check" aria-hidden="true" />
                      <span>Вернуть на ОТК</span>
                    </span>
                  </button>
                  <button
                    v-if="workOrderStatusTab === 'deleted'"
                    type="button"
                    class="action-link"
                    :disabled="isWorkOrderBusy(order.id)"
                    @click="openWorkOrderActionConfirm(order, 'restore')"
                  >
                    <span class="button-content">
                      <span class="button-icon button-icon--refresh" aria-hidden="true" />
                      <span>Восстановить</span>
                    </span>
                  </button>
                  <button
                    v-if="workOrderStatusTab !== 'deleted' && workOrderStatusTab !== 'quality_control'"
                    type="button"
                    class="action-link action-link--danger"
                    :disabled="isWorkOrderBusy(order.id)"
                    @click="openWorkOrderActionConfirm(order, 'delete')"
                  >
                    <span class="button-content">
                      <span class="button-icon button-icon--delete" aria-hidden="true" />
                      <span>Удалить</span>
                    </span>
                  </button>
                </article>
              </div>

              <div v-if="filteredWorkOrders.length > 0" class="pagination-bar">
                <span>
                  Показаны {{ workOrdersPageStart }}–{{ workOrdersPageEnd }}
                  из {{ workOrdersTotal }}
                </span>
                <div class="pagination-bar__actions">
                  <button
                    type="button"
                    class="secondary-button"
                    :disabled="workOrdersPage <= 1"
                    @click="goToWorkOrdersPage(workOrdersPage - 1)"
                  >
                    Назад
                  </button>
                  <span>{{ workOrdersPage }} / {{ workOrdersPages }}</span>
                  <button
                    type="button"
                    class="secondary-button"
                    :disabled="workOrdersPage >= workOrdersPages"
                    @click="goToWorkOrdersPage(workOrdersPage + 1)"
                  >
                    Вперед
                  </button>
                </div>
              </div>
            </div>
          </template>

          <template v-else>
            <div class="toolbar">
              <label class="field field--inline">
                <span class="field__label">Поиск по изделиям</span>
                <div class="filter-input-wrap">
                  <input
                    v-model="brigadierProductFilter"
                    type="text"
                    class="text-input text-input--with-action"
                    placeholder="Например, сумка"
                  />
                  <button
                    v-if="brigadierProductFilter"
                    type="button"
                    class="field-action"
                    aria-label="Очистить фильтр"
                    title="Очистить фильтр"
                    @click="brigadierProductFilter = ''"
                  >
                    <span class="field-action__icon" aria-hidden="true" />
                  </button>
                </div>
              </label>
            </div>

            <div v-if="listError" class="banner banner--error">
              <p>{{ listError }}</p>
              <button type="button" class="ghost-button" @click="loadProducts">
                <span class="button-content">
                  <span class="button-icon button-icon--refresh" aria-hidden="true" />
                  <span>Повторить</span>
                </span>
              </button>
            </div>

            <div v-if="listLoading" class="banner">
              <p>Загрузка изделий...</p>
            </div>

            <div v-else>
              <div class="table-wrap desktop-only">
                <table class="products-table brigadier-table">
                  <thead>
                    <tr>
                      <th>
                        <button
                          type="button"
                          class="sort-header-button"
                          :class="{
                            'sort-header-button--active':
                              isBrigadierSortFieldActive('name'),
                          }"
                          @click="toggleBrigadierSort('name')"
                        >
                          <span>Наименование</span>
                          <span
                            class="sort-header-button__icon"
                            :class="`sort-header-button__icon--${getBrigadierSortDirection('name')}`"
                            aria-hidden="true"
                          />
                        </button>
                      </th>
                      <th>Версия</th>
                      <th>
                        <button
                          type="button"
                          class="sort-header-button"
                          :class="{
                            'sort-header-button--active':
                              isBrigadierSortFieldActive('created'),
                          }"
                          @click="toggleBrigadierSort('created')"
                        >
                          <span>Дата создания</span>
                          <span
                            class="sort-header-button__icon"
                            :class="`sort-header-button__icon--${getBrigadierSortDirection('created')}`"
                            aria-hidden="true"
                          />
                        </button>
                      </th>
                      <th>Действие</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="product in filteredBrigadierProducts" :key="product.id">
                      <td>{{ product.name }}</td>
                      <td>{{ product.version }}</td>
                      <td>{{ product.createdAt }}</td>
                      <td>
                        <button
                          type="button"
                          class="primary-button"
                          @click="openBrigadierCreateOrder(product.id)"
                        >
                          <span class="button-content">
                            <span class="button-icon button-icon--play" aria-hidden="true" />
                            <span>Взять в работу</span>
                          </span>
                        </button>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>

              <div class="mobile-list mobile-only">
                <article
                  v-for="product in filteredBrigadierProducts"
                  :key="`mobile-product-${product.id}`"
                  class="mobile-card"
                >
                  <div class="mobile-card__head mobile-card__head--stacked">
                    <strong>{{ product.name }}</strong>
                    <span class="mobile-card__version">Версия {{ product.version }}</span>
                  </div>
                  <div class="mobile-card__meta">
                    <span>Создано {{ product.createdAt }}</span>
                  </div>
                  <button
                    type="button"
                    class="primary-button"
                    @click="openBrigadierCreateOrder(product.id)"
                  >
                    <span class="button-content">
                      <span class="button-icon button-icon--play" aria-hidden="true" />
                      <span>Взять в работу</span>
                    </span>
                  </button>
                </article>
              </div>
            </div>

            <div
              v-if="!listLoading && filteredBrigadierProducts.length === 0"
              class="empty-table-state"
            >
              <p>По текущему фильтру изделия не найдены.</p>
            </div>
          </template>
        </article>
      </section>

      <section v-else-if="activeTab === 'stats'">
        <article class="constructor-panel statistics-panel">
          <div class="panel-head statistics-panel__head">
            <div>
              <h2>Статистика производства</h2>
              <p class="worker-panel__subtitle">
                Последнее обновление:
                {{ statisticsOverview ? formatTimestamp(statisticsOverview.generatedAtTs) : "—" }}
              </p>
            </div>

            <div class="statistics-toolbar">
              <div class="statistics-period-control">
                <div class="segmented-control statistics-presets" role="group" aria-label="Период статистики">
                  <button
                    v-for="days in statisticsPeriodOptions"
                    :key="days"
                    type="button"
                    class="segmented-control__button"
                    :class="{
                      'segmented-control__button--active':
                        statisticsPeriodMode === 'preset' && statisticsPeriodDays === days,
                    }"
                    @click="void selectStatisticsPeriod(days)"
                  >
                    {{ days }} дн.
                  </button>
                </div>

                <div
                  class="statistics-date-range"
                  :class="{ 'statistics-date-range--active': statisticsPeriodMode === 'custom' }"
                >
                  <label class="statistics-date-field">
                    <span class="statistics-date-field__label">С</span>
                    <input
                      v-model="statisticsDateFrom"
                      type="date"
                      class="statistics-date-field__input"
                      @input="selectCustomStatisticsPeriod"
                    />
                  </label>
                  <span class="statistics-date-range__divider" aria-hidden="true" />
                  <label class="statistics-date-field">
                    <span class="statistics-date-field__label">По</span>
                    <input
                      v-model="statisticsDateTo"
                      type="date"
                      class="statistics-date-field__input"
                      @input="selectCustomStatisticsPeriod"
                    />
                  </label>
                  <button
                    type="button"
                    class="ghost-button statistics-date-range__apply"
                    :disabled="statisticsLoading"
                    @click="void applyCustomStatisticsPeriod()"
                  >
                    Показать
                  </button>
                </div>
              </div>

              <div class="statistics-toolbar__actions">
                <button
                  type="button"
                  class="primary-button statistics-refresh-button"
                  :disabled="statisticsLoading"
                  @click="void loadStatistics()"
                >
                  <span class="button-content">
                    <span class="button-icon button-icon--refresh" aria-hidden="true" />
                    <span>Обновить</span>
                  </span>
                </button>

                <button
                  type="button"
                  class="primary-button statistics-export-button"
                  :disabled="statisticsLoading || statisticsExportLoading"
                  @click="void exportStatisticsXlsx()"
                >
                  <span class="button-content">
                    <span class="button-icon button-icon--save" aria-hidden="true" />
                    <span>{{ statisticsExportLoading ? "Выгрузка..." : "XLSX" }}</span>
                  </span>
                </button>
              </div>
            </div>
          </div>

          <div v-if="statisticsError" class="banner banner--error">
            <p>{{ statisticsError }}</p>
          </div>

          <div v-else-if="statisticsLoading" class="banner">
            <p>Загрузка статистики...</p>
          </div>

          <div v-else-if="!statisticsOverview" class="empty-table-state">
            <p>Статистика пока недоступна.</p>
          </div>

          <template v-else>
            <div class="statistics-kpis">
              <article class="statistics-kpi-card">
                <span class="section-label">Всего учтено</span>
                <strong>{{ formatDurationCompact(statisticsOverview.kpis.totalTrackedMs) }}</strong>
              </article>
              <article class="statistics-kpi-card">
                <span class="section-label">Операции</span>
                <strong>{{ formatDurationCompact(statisticsOverview.kpis.operationMs) }}</strong>
              </article>
              <article class="statistics-kpi-card">
                <span class="section-label">Подготовка</span>
                <strong>{{ formatDurationCompact(statisticsOverview.kpis.preparationMs) }}</strong>
              </article>
              <article class="statistics-kpi-card">
                <span class="section-label">Перерыв</span>
                <strong>{{ formatDurationCompact(statisticsOverview.kpis.breakMs) }}</strong>
              </article>
              <article class="statistics-kpi-card">
                <span class="section-label">Простой</span>
                <strong>{{ formatDurationCompact(statisticsOverview.kpis.idleMs) }}</strong>
              </article>
              <article class="statistics-kpi-card">
                <span class="section-label">Полезное время</span>
                <strong>{{ formatPercentage(statisticsOverview.kpis.productiveRatio) }}</strong>
              </article>
              <article class="statistics-kpi-card">
                <span class="section-label">Активные заказы</span>
                <strong>{{ statisticsOverview.kpis.activeOrdersCount }}</strong>
              </article>
            </div>

            <div class="statistics-grid">
              <section class="statistics-card statistics-card--wide">
                <div class="statistics-card__head">
                  <h3>Структура рабочего времени по дням</h3>
                </div>

                <div class="statistics-legend" aria-label="Легенда статистики">
                  <span class="statistics-legend__item">
                    <span class="statistics-legend__swatch statistics-legend__swatch--operation" aria-hidden="true" />
                    <span>Операции</span>
                  </span>
                  <span class="statistics-legend__item">
                    <span class="statistics-legend__swatch statistics-legend__swatch--preparation" aria-hidden="true" />
                    <span>Подготовка</span>
                  </span>
                  <span class="statistics-legend__item">
                    <span class="statistics-legend__swatch statistics-legend__swatch--break" aria-hidden="true" />
                    <span>Перерыв</span>
                  </span>
                  <span class="statistics-legend__item">
                    <span class="statistics-legend__swatch statistics-legend__swatch--idle" aria-hidden="true" />
                    <span>Простой</span>
                  </span>
                </div>

                <div class="stacked-chart">
                  <div
                    v-for="day in statisticsOverview.dailyBreakdown"
                    :key="day.date"
                    class="stacked-chart__item"
                  >
                    <div class="stacked-chart__column">
                      <span
                        class="stacked-chart__segment stacked-chart__segment--operation"
                        :style="getStatisticsStackSegmentStyle(day.operationMs, statisticsDailyMax, 'var(--color-primary)')"
                      />
                      <span
                        class="stacked-chart__segment stacked-chart__segment--preparation"
                        :style="getStatisticsStackSegmentStyle(day.preparationMs, statisticsDailyMax, 'var(--color-success)')"
                      />
                      <span
                        class="stacked-chart__segment stacked-chart__segment--break"
                        :style="getStatisticsStackSegmentStyle(day.breakMs, statisticsDailyMax, 'var(--color-warning)')"
                      />
                      <span
                        class="stacked-chart__segment stacked-chart__segment--idle"
                        :style="getStatisticsStackSegmentStyle(day.idleMs, statisticsDailyMax, 'var(--color-danger)')"
                      />
                    </div>
                    <span class="stacked-chart__value">{{ formatDurationCompact(day.totalMs) }}</span>
                    <span class="stacked-chart__label">{{ formatStatisticsDate(day.date) }}</span>
                  </div>
                </div>
              </section>

              <section class="statistics-card">
                <div class="statistics-card__head">
                  <h3>Трудоемкие операции</h3>
                </div>

                <div v-if="statisticsOverview.topOperations.length === 0" class="empty-table-state">
                  <p>Пока нет данных по операциям.</p>
                </div>
                <div v-else class="statistics-bars">
                  <article
                    v-for="item in statisticsOverview.topOperations"
                    :key="item.operationId"
                    class="statistics-bar-row"
                  >
                    <div class="statistics-bar-row__meta">
                      <strong>{{ item.operationName }}</strong>
                      <span>{{ item.productName }} · {{ item.productVersion }}</span>
                    </div>
                    <div class="statistics-bar-row__meta statistics-bar-row__meta--secondary">
                      <span>{{ formatDurationCompact(item.totalMs) }} · ср. {{ formatDurationCompact(item.averageMs) }}</span>
                    </div>
                    <div class="statistics-bar-row__track">
                      <span
                        class="statistics-bar-row__fill"
                        :style="getStatisticsBarStyle(item.totalMs, statisticsOperationMax)"
                      />
                    </div>
                  </article>
                </div>
              </section>

              <section class="statistics-card">
                <div class="statistics-card__head">
                  <h3>Заказы по трудозатратам</h3>
                </div>

                <div v-if="statisticsOverview.topOrders.length === 0" class="empty-table-state">
                  <p>Пока нет данных по заказам.</p>
                </div>
                <div v-else class="statistics-bars">
                  <article
                    v-for="item in statisticsOverview.topOrders"
                    :key="item.orderId"
                    class="statistics-bar-row"
                  >
                    <div class="statistics-bar-row__meta">
                      <strong>{{ item.orderNumber }} · {{ item.productName }} · {{ item.productVersion }}</strong>
                      <span>{{ formatDurationCompact(item.totalMs) }}</span>
                    </div>
                    <div class="statistics-bar-row__track">
                      <span
                        class="statistics-bar-row__fill statistics-bar-row__fill--muted"
                        :style="getStatisticsBarStyle(item.totalMs, statisticsOrderMax)"
                      />
                    </div>
                  </article>
                </div>
              </section>

              <section class="statistics-card statistics-card--wide">
                <div class="statistics-card__head">
                  <h3>Загрузка сотрудников</h3>
                </div>

                <div v-if="statisticsOverview.workers.length === 0" class="empty-table-state">
                  <p>Пока нет данных по сотрудникам.</p>
                </div>
                <div v-else class="statistics-bars">
                  <article
                    v-for="item in statisticsOverview.workers"
                    :key="item.userId"
                    class="statistics-bar-row"
                  >
                    <div class="statistics-bar-row__meta">
                      <strong>{{ item.userName }}</strong>
                      <span>
                        {{ formatDurationCompact(item.totalMs) }}
                        · операции {{ formatDurationCompact(item.operationMs) }}
                        · простой {{ formatDurationCompact(item.idleMs) }}
                        · {{ formatPercentage(item.productiveRatio) }}
                      </span>
                    </div>
                    <div class="statistics-bar-row__track">
                      <span
                        class="statistics-bar-row__fill statistics-bar-row__fill--success"
                        :style="getStatisticsBarStyle(item.totalMs, statisticsWorkerMax)"
                      />
                    </div>
                  </article>
                </div>
              </section>

              <section class="statistics-card">
                <div class="statistics-card__head">
                  <h3>Простой по дням</h3>
                </div>

                <div class="mini-chart">
                  <div
                    v-for="day in statisticsOverview.idleByDay"
                    :key="day.date"
                    class="mini-chart__item"
                  >
                    <span
                      class="mini-chart__bar"
                      :style="getStatisticsStackSegmentStyle(day.idleMs, statisticsIdleMax, 'var(--color-danger)')"
                    />
                    <span class="mini-chart__label">{{ formatStatisticsDate(day.date) }}</span>
                  </div>
                </div>
              </section>
            </div>
          </template>
        </article>
      </section>

      <section v-else-if="activeTab === 'reports'">
        <ReportsPanel
          :products="products"
        />
      </section>

      <section v-else-if="activeTab === 'constructor'">
        <article class="constructor-panel">
          <div class="panel-head panel-head--stacked">
            <div>
              <h2>Конструктор</h2>
            </div>

            <div class="subtabs" role="tablist" aria-label="Разделы конструктора">
              <button
                type="button"
                class="subtab-button"
                :class="{ 'subtab-button--active': constructorTab === 'products' }"
                @click="constructorTab = 'products'"
              >
                <span class="button-content">
                  <span class="button-icon button-icon--package" aria-hidden="true" />
                  <span>Изделия и дерево операций</span>
                </span>
              </button>
              <button
                type="button"
                class="subtab-button"
                :class="{ 'subtab-button--active': constructorTab === 'directories' }"
                @click="constructorTab = 'directories'"
              >
                <span class="button-content">
                  <span class="button-icon button-icon--orders" aria-hidden="true" />
                  <span>Справочники</span>
                </span>
              </button>
            </div>
          </div>

          <template v-if="constructorTab === 'products'">
            <div class="panel-head">
              <div>
                <h2>Изделия и дерево операций</h2>
              </div>

              <button type="button" class="primary-button" @click="startCreateProduct">
                <span class="button-content">
                  <span class="button-icon button-icon--plus" aria-hidden="true" />
                  <span>Создать новое изделие</span>
                </span>
              </button>
            </div>

            <div class="toolbar">
              <label class="field field--inline">
                <span class="field__label">Фильтр по имени</span>
                <div class="filter-input-wrap">
                  <input
                    v-model="productFilter"
                    type="text"
                    class="text-input text-input--with-action"
                    placeholder="Например, кошелек"
                  />
                  <button
                    v-if="productFilter"
                    type="button"
                    class="field-action"
                    aria-label="Очистить фильтр"
                    title="Очистить фильтр"
                    @click="productFilter = ''"
                  >
                    <span class="field-action__icon" aria-hidden="true" />
                  </button>
                </div>
              </label>

              <div class="field field--inline">
                <span class="field__label">Отображение</span>
                <div class="segmented-control" role="group" aria-label="Отображение изделий">
                  <button
                    v-for="option in visibilityOptions"
                    :key="option.value"
                    type="button"
                    class="segmented-control__button segmented-control__button--icon"
                    :class="{
                      'segmented-control__button--active':
                        productVisibility === option.value,
                    }"
                    :title="option.label"
                    :aria-label="option.label"
                    @click="productVisibility = option.value"
                  >
                    <span
                      class="toolbar-icon"
                      :class="`toolbar-icon--${option.icon}`"
                      aria-hidden="true"
                    />
                  </button>
                </div>
              </div>

              <div class="field field--inline">
                <span class="field__label">Сортировка</span>
                <div class="segmented-control segmented-control--wrap" role="group" aria-label="Сортировка изделий">
                  <button
                    v-for="option in sortOptions"
                    :key="option.field"
                    type="button"
                    class="segmented-control__button segmented-control__button--icon"
                    :class="{
                      'segmented-control__button--active':
                        isSortFieldActive(option.field),
                    }"
                    :title="`${option.label} (${getSortDirection(option.field) === 'asc' ? 'по возрастанию' : 'по убыванию'})`"
                    :aria-label="`${option.label} (${getSortDirection(option.field) === 'asc' ? 'по возрастанию' : 'по убыванию'})`"
                    @click="toggleProductSort(option.field)"
                  >
                    <span
                      class="toolbar-icon"
                      :class="[
                        `toolbar-icon--${option.icon}`,
                        `toolbar-icon--${getSortDirection(option.field)}`,
                      ]"
                      aria-hidden="true"
                    />
                  </button>
                </div>
              </div>
            </div>

            <div v-if="listError" class="banner banner--error">
              <p>{{ listError }}</p>
              <button type="button" class="ghost-button" @click="loadProducts">
                <span class="button-content">
                  <span class="button-icon button-icon--refresh" aria-hidden="true" />
                  <span>Повторить</span>
                </span>
              </button>
            </div>

            <div v-if="listLoading" class="banner">
              <p>Загрузка изделий...</p>
            </div>

            <div v-else class="table-wrap">
              <table class="products-table">
                <thead>
                  <tr>
                    <th>Наименование</th>
                    <th>Версия</th>
                    <th>Автор</th>
                    <th>Дата создания</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="product in filteredProducts" :key="product.id">
                    <td>
                      <button
                        type="button"
                        class="table-link"
                        :disabled="isProductBusy(product.id)"
                        @click="startViewProduct(product.id)"
                      >
                        <span class="button-content">
                          <span class="button-icon button-icon--edit" aria-hidden="true" />
                          <span>{{ product.name }}</span>
                        </span>
                      </button>
                    </td>
                    <td>{{ product.version }}</td>
                    <td>{{ product.author }}</td>
                    <td>{{ product.createdAt }}</td>
                    <td>
                      <div class="table-actions">
                        <button
                          type="button"
                          class="action-link"
                          :disabled="isProductBusy(product.id)"
                          @click="startViewProduct(product.id)"
                        >
                          <span class="button-content">
                            <span class="button-icon button-icon--view" aria-hidden="true" />
                            <span>Просмотр ({{ product.operationsCount }} этапов)</span>
                          </span>
                        </button>
                        <button
                          type="button"
                          class="action-link"
                          :disabled="isProductBusy(product.id)"
                          @click="toggleProductStatus(product)"
                        >
                          <span class="button-content">
                            <span
                              class="button-icon"
                              :class="product.isActive ? 'button-icon--pause' : 'button-icon--check'"
                              aria-hidden="true"
                            />
                            <span>
                              {{
                                isProductBusy(product.id)
                                  ? "Обновление..."
                                  : product.isActive
                                    ? "Деактивировать"
                                    : "Активировать"
                              }}
                            </span>
                          </span>
                        </button>
                        <button
                          type="button"
                          class="action-link"
                          :disabled="isProductBusy(product.id)"
                          @click="startCopyProduct(product.id)"
                        >
                          <span class="button-content">
                            <span class="button-icon button-icon--copy" aria-hidden="true" />
                            <span>Копировать</span>
                          </span>
                        </button>
                        <button
                          type="button"
                          class="action-link action-link--danger"
                          :disabled="isProductBusy(product.id)"
                          @click="openDeleteConfirmation(product)"
                        >
                          <span class="button-content">
                            <span class="button-icon button-icon--delete" aria-hidden="true" />
                            <span>Удалить</span>
                          </span>
                        </button>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div
              v-if="!listLoading && filteredProducts.length === 0"
              class="empty-table-state"
            >
              <p>По текущему фильтру изделия не найдены.</p>
            </div>
          </template>

          <template v-else>
            <div class="panel-head panel-head--stacked">
              <div>
                <h2>Справочники</h2>
              </div>

              <div class="subtabs" role="tablist" aria-label="Справочники конструктора">
                <button
                  type="button"
                  class="subtab-button"
                  :class="{
                    'subtab-button--active':
                      constructorDirectoryTab === 'operation-catalog',
                  }"
                  @click="constructorDirectoryTab = 'operation-catalog'"
                >
                  <span class="button-content">
                    <span class="button-icon button-icon--orders" aria-hidden="true" />
                    <span>Операции</span>
                  </span>
                </button>
                <button
                  type="button"
                  class="subtab-button"
                  :class="{
                    'subtab-button--active':
                      constructorDirectoryTab === 'leather-types',
                  }"
                  @click="constructorDirectoryTab = 'leather-types'"
                >
                  <span class="button-content">
                    <span class="button-icon button-icon--package" aria-hidden="true" />
                    <span>Виды кожи</span>
                  </span>
                </button>
              </div>
            </div>

            <template v-if="constructorDirectoryTab === 'operation-catalog'">
              <form class="dictionary-form" @submit.prevent="void submitOperationCatalogEntry()">
                <label class="field">
                  <span class="field__label">Новая операция</span>
                  <input
                    v-model="operationCatalogName"
                    type="text"
                    class="text-input"
                    placeholder="Например, Крой"
                  />
                  <p
                    v-if="operationCatalogName && operationCatalogNameError"
                    class="field-error"
                  >
                    {{ operationCatalogNameError }}
                  </p>
                </label>
                <button
                  type="submit"
                  class="primary-button"
                  :disabled="
                    operationCatalogSaveLoading ||
                    Boolean(operationCatalogNameError)
                  "
                >
                  <span class="button-content">
                    <span class="button-icon button-icon--plus" aria-hidden="true" />
                    <span>
                      {{
                        operationCatalogSaveLoading
                          ? "Сохранение..."
                          : "Добавить"
                      }}
                    </span>
                  </span>
                </button>
              </form>

              <div class="toolbar">
                <label class="field field--inline">
                  <span class="field__label">Поиск по наименованию</span>
                  <div class="filter-input-wrap">
                    <input
                      v-model="operationCatalogSearchDraft"
                      type="text"
                      class="text-input text-input--with-action"
                      placeholder="Например, крой"
                      @keydown.enter.prevent="applyOperationCatalogSearch"
                    />
                    <button
                      v-if="operationCatalogSearchDraft || operationCatalogFilter"
                      type="button"
                      class="field-action"
                      aria-label="Очистить поиск"
                      title="Очистить поиск"
                      @click="clearOperationCatalogSearch"
                    >
                      <span class="field-action__icon" aria-hidden="true" />
                    </button>
                  </div>
                </label>

                <label class="checkbox-field">
                  <input
                    v-model="showInactiveOperationCatalogEntries"
                    type="checkbox"
                  />
                  <span>Показывать деактивированные</span>
                </label>

                <div class="field field--inline">
                  <span class="field__label">Сортировка</span>
                  <div class="segmented-control segmented-control--wrap" role="group" aria-label="Сортировка операций">
                    <button
                      type="button"
                      class="segmented-control__button segmented-control__button--icon segmented-control__button--active"
                      :title="`Сортировка по наименованию (${operationCatalogSortDirection === 'asc' ? 'по возрастанию' : 'по убыванию'})`"
                      :aria-label="`Сортировка по наименованию (${operationCatalogSortDirection === 'asc' ? 'по возрастанию' : 'по убыванию'})`"
                      @click="toggleOperationCatalogSort"
                    >
                      <span
                        class="toolbar-icon"
                        :class="[
                          'toolbar-icon--name',
                          `toolbar-icon--${operationCatalogSortDirection}`,
                        ]"
                        aria-hidden="true"
                      />
                    </button>
                  </div>
                </div>
              </div>

              <div
                v-if="operationCatalogSaveError || operationCatalogError"
                class="banner banner--error"
              >
                <p>{{ operationCatalogSaveError || operationCatalogError }}</p>
                <button type="button" class="ghost-button" @click="loadOperationCatalog">
                  <span class="button-content">
                    <span class="button-icon button-icon--refresh" aria-hidden="true" />
                    <span>Повторить</span>
                  </span>
                </button>
              </div>

              <div v-if="operationCatalogLoading" class="banner">
                <p>Загрузка операций...</p>
              </div>

              <div
                v-else-if="operationCatalogEntries.length === 0"
                class="empty-table-state"
              >
                <p>Операции по выбранным условиям не найдены.</p>
              </div>

              <template v-else>
                <div class="table-wrap">
                  <table class="products-table dictionary-table">
                    <thead>
                      <tr>
                        <th>Наименование</th>
                        <th>Действия</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr
                        v-for="entry in operationCatalogEntries"
                        :key="entry.id"
                      >
                        <td>{{ entry.name }}</td>
                        <td>
                          <div class="table-actions">
                            <button
                              type="button"
                              class="action-link"
                              :disabled="isOperationCatalogEntryBusy(entry.id)"
                              @click="void toggleOperationCatalogEntryStatus(entry)"
                            >
                              <span class="button-content">
                                <span
                                  class="button-icon"
                                  :class="entry.isActive ? 'button-icon--pause' : 'button-icon--check'"
                                  aria-hidden="true"
                                />
                                <span>
                                  {{
                                    isOperationCatalogEntryBusy(entry.id)
                                      ? "Обновление..."
                                      : entry.isActive
                                        ? "Деактивировать"
                                        : "Активировать"
                                  }}
                                </span>
                              </span>
                            </button>
                          </div>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <div class="pagination-bar">
                  <span>
                    Показаны {{ operationCatalogPageStart }}–{{ operationCatalogPageEnd }}
                    из {{ operationCatalogTotal }}
                  </span>
                  <div class="pagination-bar__actions">
                    <button
                      type="button"
                      class="secondary-button"
                      :disabled="operationCatalogPage <= 1"
                      @click="goToOperationCatalogPage(operationCatalogPage - 1)"
                    >
                      Назад
                    </button>
                    <span>{{ operationCatalogPage }} / {{ operationCatalogPages }}</span>
                    <button
                      type="button"
                      class="secondary-button"
                      :disabled="operationCatalogPage >= operationCatalogPages"
                      @click="goToOperationCatalogPage(operationCatalogPage + 1)"
                    >
                      Вперед
                    </button>
                  </div>
                </div>
              </template>
            </template>

            <template v-if="constructorDirectoryTab === 'leather-types'">
              <form class="dictionary-form" @submit.prevent="void submitLeatherType()">
                <label class="field">
                  <span class="field__label">Новый вид кожи</span>
                  <input
                    v-model="leatherTypeName"
                    type="text"
                    class="text-input"
                    placeholder="Например, Краст"
                  />
                  <p v-if="leatherTypeName && leatherTypeNameError" class="field-error">
                    {{ leatherTypeNameError }}
                  </p>
                </label>
                <button
                  type="submit"
                  class="primary-button"
                  :disabled="leatherTypeSaveLoading || Boolean(leatherTypeNameError)"
                >
                  <span class="button-content">
                    <span class="button-icon button-icon--plus" aria-hidden="true" />
                    <span>{{ leatherTypeSaveLoading ? "Сохранение..." : "Добавить" }}</span>
                  </span>
                </button>
              </form>

              <div class="toolbar">
                <label class="field field--inline">
                  <span class="field__label">Поиск по наименованию</span>
                  <div class="filter-input-wrap">
                    <input
                      v-model="leatherTypeSearchDraft"
                      type="text"
                      class="text-input text-input--with-action"
                      placeholder="Например, краст"
                      @keydown.enter.prevent="applyLeatherTypeSearch"
                    />
                    <button
                      v-if="leatherTypeSearchDraft || leatherTypeFilter"
                      type="button"
                      class="field-action"
                      aria-label="Очистить поиск"
                      title="Очистить поиск"
                      @click="clearLeatherTypeSearch"
                    >
                      <span class="field-action__icon" aria-hidden="true" />
                    </button>
                  </div>
                </label>

                <label class="checkbox-field">
                  <input
                    v-model="showInactiveLeatherTypes"
                    type="checkbox"
                  />
                  <span>Показывать деактивированные</span>
                </label>

                <div class="field field--inline">
                  <span class="field__label">Сортировка</span>
                  <div class="segmented-control segmented-control--wrap" role="group" aria-label="Сортировка видов кожи">
                    <button
                      type="button"
                      class="segmented-control__button segmented-control__button--icon segmented-control__button--active"
                      :title="`Сортировка по наименованию (${leatherTypeSortDirection === 'asc' ? 'по возрастанию' : 'по убыванию'})`"
                      :aria-label="`Сортировка по наименованию (${leatherTypeSortDirection === 'asc' ? 'по возрастанию' : 'по убыванию'})`"
                      @click="toggleLeatherTypeSort"
                    >
                      <span
                        class="toolbar-icon"
                        :class="[
                          'toolbar-icon--name',
                          `toolbar-icon--${leatherTypeSortDirection}`,
                        ]"
                        aria-hidden="true"
                      />
                    </button>
                  </div>
                </div>
              </div>

              <div v-if="leatherTypeError || leatherTypesError" class="banner banner--error">
                <p>{{ leatherTypeError || leatherTypesError }}</p>
                <button type="button" class="ghost-button" @click="loadLeatherTypes">
                  <span class="button-content">
                    <span class="button-icon button-icon--refresh" aria-hidden="true" />
                    <span>Повторить</span>
                  </span>
                </button>
              </div>

              <div v-if="leatherTypesLoading" class="banner">
                <p>Загрузка видов кожи...</p>
              </div>

              <div v-else-if="leatherTypes.length === 0" class="empty-table-state">
                <p>Виды кожи по выбранным условиям не найдены.</p>
              </div>

              <template v-else>
                <div class="table-wrap">
                  <table class="products-table dictionary-table">
                    <thead>
                      <tr>
                        <th>Наименование</th>
                        <th>Действия</th>
                      </tr>
                    </thead>
                    <tbody>
                      <tr v-for="leatherType in leatherTypes" :key="leatherType.id">
                        <td>{{ leatherType.name }}</td>
                        <td>
                          <div class="table-actions">
                            <button
                              type="button"
                              class="action-link"
                              :disabled="isLeatherTypeBusy(leatherType.id)"
                              @click="void toggleLeatherTypeStatus(leatherType)"
                            >
                              <span class="button-content">
                                <span
                                  class="button-icon"
                                  :class="leatherType.isActive ? 'button-icon--pause' : 'button-icon--check'"
                                  aria-hidden="true"
                                />
                                <span>
                                  {{
                                    isLeatherTypeBusy(leatherType.id)
                                      ? "Обновление..."
                                      : leatherType.isActive
                                        ? "Деактивировать"
                                        : "Активировать"
                                  }}
                                </span>
                              </span>
                            </button>
                          </div>
                        </td>
                      </tr>
                    </tbody>
                  </table>
                </div>

                <div class="pagination-bar">
                  <span>
                    Показаны {{ leatherTypesPageStart }}–{{ leatherTypesPageEnd }}
                    из {{ leatherTypesTotal }}
                  </span>
                  <div class="pagination-bar__actions">
                    <button
                      type="button"
                      class="secondary-button"
                      :disabled="leatherTypesPage <= 1"
                      @click="goToLeatherTypesPage(leatherTypesPage - 1)"
                    >
                      Назад
                    </button>
                    <span>{{ leatherTypesPage }} / {{ leatherTypesPages }}</span>
                    <button
                      type="button"
                      class="secondary-button"
                      :disabled="leatherTypesPage >= leatherTypesPages"
                      @click="goToLeatherTypesPage(leatherTypesPage + 1)"
                    >
                      Вперед
                    </button>
                  </div>
                </div>
              </template>
            </template>
          </template>
        </article>
      </section>

      <section v-else>
        <article class="constructor-panel">
          <div class="panel-head">
            <div>
              <h2>Пользователи и доступы</h2>
            </div>

            <button
              type="button"
              class="primary-button"
              :disabled="editingUserId !== null"
              @click="startCreateUser"
            >
              <span class="button-content">
                <span class="button-icon button-icon--plus" aria-hidden="true" />
                <span>Добавить пользователя</span>
              </span>
            </button>
          </div>

          <div class="toolbar">
            <label class="field field--inline">
              <span class="field__label">Фильтр по имени</span>
              <div class="filter-input-wrap">
                <input
                  v-model="userFilter"
                  type="text"
                  class="text-input text-input--with-action"
                  placeholder="Например, Анна"
                />
                <button
                  v-if="userFilter"
                  type="button"
                  class="field-action"
                  aria-label="Очистить фильтр"
                  title="Очистить фильтр"
                  @click="userFilter = ''"
                >
                  <span class="field-action__icon" aria-hidden="true" />
                </button>
              </div>
            </label>

            <div class="field field--inline">
              <span class="field__label">Отображение</span>
              <div class="segmented-control" role="group" aria-label="Отображение пользователей">
                <button
                  v-for="option in visibilityOptions"
                  :key="option.value"
                  type="button"
                  class="segmented-control__button segmented-control__button--icon"
                  :class="{
                    'segmented-control__button--active':
                      userVisibility === option.value,
                  }"
                  :title="option.label"
                  :aria-label="option.label"
                  @click="userVisibility = option.value"
                >
                  <span
                    class="toolbar-icon"
                    :class="`toolbar-icon--${option.icon}`"
                    aria-hidden="true"
                  />
                </button>
              </div>
            </div>

            <div class="field field--inline">
              <span class="field__label">Сортировка</span>
              <div class="segmented-control" role="group" aria-label="Сортировка пользователей">
                <button
                  v-for="option in userSortOptions"
                  :key="option.field"
                  type="button"
                  class="segmented-control__button segmented-control__button--icon"
                  :class="{
                    'segmented-control__button--active':
                      isUserSortFieldActive(option.field),
                  }"
                  :title="`${option.label} (${getUserSortDirection(option.field) === 'asc' ? 'по возрастанию' : 'по убыванию'})`"
                  :aria-label="`${option.label} (${getUserSortDirection(option.field) === 'asc' ? 'по возрастанию' : 'по убыванию'})`"
                  @click="toggleUserSort(option.field)"
                >
                  <span
                    class="toolbar-icon"
                    :class="[
                      `toolbar-icon--${option.icon}`,
                      `toolbar-icon--${getUserSortDirection(option.field)}`,
                    ]"
                    aria-hidden="true"
                  />
                </button>
              </div>
            </div>
          </div>

          <div v-if="usersError" class="banner banner--error">
            <p>{{ usersError }}</p>
            <button type="button" class="ghost-button" @click="loadUsers">
              <span class="button-content">
                <span class="button-icon button-icon--refresh" aria-hidden="true" />
                <span>Повторить</span>
              </span>
            </button>
          </div>

          <div v-if="usersLoading" class="banner">
            <p>Загрузка пользователей...</p>
          </div>

          <div v-else class="table-wrap">
            <table class="products-table users-table">
              <thead>
                <tr>
                  <th>Имя</th>
                  <th>Телефон</th>
                  <th>Автор</th>
                  <th>Права</th>
                  <th>Статус</th>
                  <th>Дата создания</th>
                  <th>Дата изменения</th>
                  <th>Действия</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="user in filteredUsers"
                  :key="user.id"
                  :class="{
                    'table-row--locked': isUserLocked(user.id),
                    'table-row--editing': isEditingUser(user.id),
                  }"
                >
                  <td>
                    <div v-if="isEditingUser(user.id)" class="user-cell">
                      <input
                        :value="editingUserDraft?.name ?? ''"
                        type="text"
                        class="text-input users-table__input"
                        placeholder="Имя пользователя"
                        @input="handleUserNameInput(user.id, $event)"
                      />
                      <p v-if="getUserNameError(user)" class="field-error">
                        {{ getUserNameError(user) }}
                      </p>
                    </div>
                    <button
                      v-else
                      type="button"
                      class="table-link"
                      :disabled="isUserLocked(user.id)"
                      @click="startEditUser(user)"
                    >
                      <span class="button-content">
                        <span class="button-icon button-icon--edit" aria-hidden="true" />
                        <span>{{ getDisplayedUser(user).name || "Без имени" }}</span>
                      </span>
                    </button>
                  </td>
                  <td>
                    <div v-if="isEditingUser(user.id)" class="user-cell">
                      <input
                        :value="editingUserDraft?.phone ?? ''"
                        type="text"
                        class="text-input users-table__input"
                        placeholder="+7 999 123-45-67"
                        @input="handleUserPhoneInput(user.id, $event)"
                      />
                      <p v-if="getUserPhoneError(user)" class="field-error">
                        {{ getUserPhoneError(user) }}
                      </p>
                    </div>
                    <span v-else>{{ getDisplayedUser(user).phone || "—" }}</span>
                  </td>
                  <td>{{ getDisplayedUser(user).author || "—" }}</td>
                  <td>
                    <div class="user-cell">
                      <div class="role-group">
                        <button
                          v-for="role in userRoleOptions"
                          :key="role.value"
                          type="button"
                          class="role-button"
                          :class="{
                            'role-button--active':
                              getDisplayedUser(user).roles.includes(role.value),
                          }"
                          :title="role.label"
                          :aria-label="role.label"
                          :disabled="isUserLocked(user.id)"
                          @click="handleUserRoleAction(user, role.value)"
                        >
                          <span
                            class="role-icon"
                            :class="`role-icon--${role.icon}`"
                            aria-hidden="true"
                          />
                        </button>
                      </div>
                      <p v-if="getUserRolesError(user)" class="field-error">
                        {{ getUserRolesError(user) }}
                      </p>
                    </div>
                  </td>
                  <td>
                    <span
                      class="user-status"
                      :class="{
                        'user-status--active': getDisplayedUser(user).isActive,
                        'user-status--inactive': !getDisplayedUser(user).isActive,
                      }"
                    >
                      {{ getDisplayedUser(user).isActive ? "Активен" : "Деактивирован" }}
                    </span>
                  </td>
                  <td>{{ getDisplayedUser(user).createdAt || "—" }}</td>
                  <td>{{ getDisplayedUser(user).updatedAt || "—" }}</td>
                  <td>
                    <div class="table-actions">
                      <button
                        type="button"
                        class="action-link"
                        :disabled="isUserLocked(user.id)"
                        @click="handleUserStatusAction(user)"
                      >
                        <span class="button-content">
                          <span
                            class="button-icon"
                            :class="getDisplayedUser(user).isActive ? 'button-icon--pause' : 'button-icon--check'"
                            aria-hidden="true"
                          />
                          <span>
                            {{
                              getDisplayedUser(user).isActive
                                ? "Деактивировать"
                                : "Активировать"
                            }}
                          </span>
                        </span>
                      </button>
                      <button
                        v-if="getDisplayedUser(user).passwordHash"
                        type="button"
                        class="action-link"
                        :disabled="isUserLocked(user.id)"
                        @click="void handleResetUserPassword(user)"
                      >
                        <span class="button-content">
                          <span class="button-icon button-icon--reset-password" aria-hidden="true" />
                          <span>Сбросить пароль</span>
                        </span>
                      </button>
                      <button
                        type="button"
                        class="action-link action-link--danger"
                        :disabled="isUserLocked(user.id)"
                        @click="openUserDeleteConfirmation(user)"
                      >
                        <span class="button-content">
                          <span class="button-icon button-icon--delete" aria-hidden="true" />
                          <span>Удалить</span>
                        </span>
                      </button>
                      <button
                        v-if="isEditingUser(user.id)"
                        type="button"
                        class="action-link"
                        :disabled="!canSaveUser(user)"
                        @click="saveUserChanges(user)"
                      >
                        <span class="button-content">
                          <span class="button-icon button-icon--save" aria-hidden="true" />
                          <span>Сохранить изменения</span>
                        </span>
                      </button>
                      <button
                        v-if="isEditingUser(user.id)"
                        type="button"
                        class="action-link"
                        @click="cancelUserEdit"
                      >
                        <span class="button-content">
                          <span class="button-icon button-icon--close" aria-hidden="true" />
                          <span>Отменить изменения</span>
                        </span>
                      </button>
                    </div>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>

          <div
            v-if="!usersLoading && filteredUsers.length === 0"
            class="empty-table-state"
          >
            <p>По текущему фильтру пользователи не найдены.</p>
          </div>
        </article>
      </section>
    </section>

    <div
      v-if="changePasswordModalOpen"
      class="modal-backdrop"
      @click.self="closeChangePasswordModal"
    >
      <section class="confirm-modal" role="dialog" aria-modal="true">
        <div class="confirm-modal__content">
          <p class="confirm-modal__eyebrow">Пароль пользователя</p>
          <h2>Изменить пароль</h2>

          <label class="field">
            <span class="field__label">Текущий пароль</span>
            <input
              v-model="changePasswordCurrent"
              type="password"
              class="text-input"
              autocomplete="current-password"
              placeholder="Если пароль уже задан"
            />
          </label>

          <label class="field">
            <span class="field__label">Новый пароль</span>
            <input
              v-model="changePasswordNext"
              type="password"
              class="text-input"
              autocomplete="new-password"
              placeholder="Не менее 8 символов"
            />
          </label>

          <label class="field">
            <span class="field__label">Подтверждение нового пароля</span>
            <input
              v-model="changePasswordConfirm"
              type="password"
              class="text-input"
              autocomplete="new-password"
              placeholder="Повторите новый пароль"
            />
          </label>

          <p v-if="changePasswordError" class="field-error">{{ changePasswordError }}</p>
        </div>

        <div class="confirm-modal__actions">
          <button type="button" class="ghost-button" @click="closeChangePasswordModal">
            <span class="button-content">
              <span class="button-icon button-icon--close" aria-hidden="true" />
              <span>Отменить</span>
            </span>
          </button>
          <button
            type="button"
            class="primary-button"
            :disabled="changePasswordSaving"
            @click="void submitPasswordChange()"
          >
            <span class="button-content">
              <span class="button-icon button-icon--save" aria-hidden="true" />
              <span>{{ changePasswordSaving ? "Сохранение..." : "Сохранить пароль" }}</span>
            </span>
          </button>
        </div>
      </section>
    </div>

    <div
      v-if="isBrigadierOrderModalOpen"
      class="modal-backdrop"
      @click.self="closeBrigadierOrderModal"
    >
      <section class="modal brigadier-modal" role="dialog" aria-modal="true">
        <div class="modal__head">
          <div>
            <h2>{{ brigadierModalTitle }}</h2>
            <p class="modal__description">{{ brigadierModalDescription }}</p>
          </div>

          <button
            type="button"
            class="ghost-button"
            @click="closeBrigadierOrderModal"
          >
            <span class="button-content">
              <span class="button-icon button-icon--close" aria-hidden="true" />
              <span>Закрыть</span>
            </span>
          </button>
        </div>

        <div v-if="brigadierModalError" class="banner banner--error">
          <p>{{ brigadierModalError }}</p>
        </div>

        <div v-if="brigadierModalLoading" class="banner">
          <p>Загрузка заказа...</p>
        </div>

        <form
          v-else-if="brigadierModalProduct"
          class="order-form"
          @submit.prevent="requestBrigadierOrderSave"
        >
          <div class="order-form__header">
            <div class="order-form__summary">
              <div class="summary-card">
                <span class="section-label">Изделие</span>
                <strong>
                  {{ brigadierModalProduct.name }} · {{ brigadierModalProduct.version }}
                </strong>
                <label class="field summary-card__field">
                  <span class="field__label">Вид кожи</span>
                  <div class="assignment-input-wrap">
                    <div
                      v-if="!isBrigadierLeatherTypeEditable"
                      class="operation-text"
                    >
                      {{ brigadierModalLeatherTypeName ?? "вид кожи не указан" }}
                    </div>
                    <input
                      v-else
                      :value="brigadierModalLeatherTypeNameDraft"
                      type="text"
                      class="text-input text-input--with-clear"
                      autocomplete="off"
                      placeholder="Не выбран"
                      data-field="brigadier-leather-type"
                      @input="handleBrigadierLeatherTypeInput"
                      @focus="openBrigadierLeatherTypeDropdown"
                      @click="openBrigadierLeatherTypeDropdown"
                      @blur="scheduleBrigadierLeatherTypeDropdownClose"
                    />
                    <button
                      v-if="
                        (brigadierModalLeatherTypeId ||
                          brigadierModalLeatherTypeNameDraft) &&
                        isBrigadierLeatherTypeEditable
                      "
                      type="button"
                      class="field-action field-action--right"
                      aria-label="Очистить вид кожи"
                      title="Очистить вид кожи"
                      @mousedown.prevent
                      @click="clearBrigadierLeatherType"
                    >
                      <span class="field-action__icon" aria-hidden="true" />
                    </button>
                    <div
                      v-if="isBrigadierLeatherTypeDropdownOpen && isBrigadierLeatherTypeEditable"
                      class="assignment-dropdown"
                    >
                      <button
                        type="button"
                        class="assignment-dropdown__option"
                        :class="{
                          'assignment-dropdown__option--selected':
                            !brigadierModalLeatherTypeId,
                        }"
                        @mousedown.prevent
                        @click="selectBrigadierLeatherType(null)"
                      >
                        <span>Не выбран</span>
                      </button>
                      <button
                        v-for="leatherType in getBrigadierLeatherTypeOptions()"
                        :key="leatherType.id"
                        type="button"
                        class="assignment-dropdown__option"
                        :class="{
                          'assignment-dropdown__option--selected':
                            brigadierModalLeatherTypeId === String(leatherType.id),
                        }"
                        @mousedown.prevent
                        @click="selectBrigadierLeatherType(leatherType.id)"
                      >
                        <span>{{ leatherType.name }}</span>
                      </button>
                      <div
                        v-if="getBrigadierLeatherTypeOptions().length === 0"
                        class="assignment-dropdown__empty"
                      >
                        Справочник видов кожи пуст.
                      </div>
                    </div>
                    <p v-if="brigadierLeatherTypeError" class="field-error">
                      {{ brigadierLeatherTypeError }}
                    </p>
                  </div>
                </label>
                <label
                  v-if="isQualityControlOrderModal"
                  class="field summary-card__field"
                >
                  <span class="field__label">Количество брака</span>
                  <input
                    :value="brigadierModalDefectQuantity"
                    type="number"
                    min="0"
                    step="1"
                    :max="brigadierModalQuantity"
                    inputmode="numeric"
                    class="text-input"
                    data-field="brigadier-defect-quantity"
                    placeholder="0"
                    @input="handleBrigadierDefectQuantityInput"
                  />
                  <p v-if="brigadierDefectQuantityError" class="field-error">
                    {{ brigadierDefectQuantityError }}
                  </p>
                </label>
              </div>
            </div>

            <div class="order-form__meta">
              <label class="field">
                <span class="field__label">Номер заказа</span>
                <input
                  :value="brigadierModalOrderNumber"
                  type="text"
                  class="text-input"
                  data-field="brigadier-order-number"
                  :readonly="brigadierModalMode !== 'create'"
                  placeholder="Например, FC-0001"
                  @input="handleBrigadierOrderNumberInput"
                />
                <p v-if="brigadierOrderNumberError" class="field-error">
                  {{ brigadierOrderNumberError }}
                </p>
              </label>

              <label class="field order-form__quantity">
                <span class="field__label">Количество изделий</span>
                <div
                  v-if="!isBrigadierQuantityEditable"
                  class="operation-text"
                >
                  {{ brigadierModalQuantity }} шт.
                </div>
                <input
                  v-else
                  :value="brigadierModalQuantity"
                  type="text"
                  inputmode="numeric"
                  class="text-input"
                  data-field="brigadier-quantity"
                  placeholder="Например, 12"
                  @input="handleBrigadierQuantityInput"
                />
                <p v-if="brigadierQuantityError" class="field-error">
                  {{ brigadierQuantityError }}
                </p>
              </label>

              <label class="field">
                <span class="field__label">Плановая дата сдачи</span>
                <input
                  v-model="brigadierModalPlannedCompletionDate"
                  type="date"
                  class="text-input"
                  data-field="brigadier-planned-completion-date"
                />
                <p v-if="brigadierPlannedCompletionDateError" class="field-error">
                  {{ brigadierPlannedCompletionDateError }}
                </p>
              </label>
            </div>
          </div>

          <section class="order-assignments">
            <div class="operations-section__head">
              <div>
                <span class="field__label">Назначение исполнителей</span>
                <p class="field__hint">
                  {{
                    isBrigadierAssignmentsEditable
                      ? "Для каждой операции выберите исполнителя с ролью `исполнитель`."
                      : "Назначения исполнителей доступны только для просмотра."
                  }}
                </p>
              </div>
            </div>

            <div v-if="brigadierWorkerUsers.length === 0" class="banner banner--error">
              <p>Нет активных пользователей с ролью исполнителя.</p>
            </div>

            <div v-if="brigadierModalAssignments.length === 0" class="empty-table-state">
              <p>У этого изделия нет назначаемых операций.</p>
            </div>

            <div v-else class="assignment-list">
              <div
                v-for="assignment in brigadierModalAssignments"
                :key="assignment.operationId"
                class="assignment-row"
              >
                <div class="assignment-row__label">
                  {{ assignment.operationLabel }}
                </div>
                <div class="assignment-row__control">
                  <div class="assignment-input-wrap">
                    <input
                      :value="assignment.workerName"
                      type="text"
                      class="text-input text-input--with-clear"
                      autocomplete="off"
                      :readonly="!isBrigadierAssignmentsEditable"
                      :data-brigadier-operation-id="assignment.operationId"
                      placeholder="Выберите исполнителя"
                      @input="handleBrigadierAssignmentInput(assignment.operationId, $event)"
                      @focus="openBrigadierAssignmentDropdown(assignment.operationId)"
                      @click="openBrigadierAssignmentDropdown(assignment.operationId)"
                      @blur="scheduleBrigadierAssignmentDropdownClose(assignment.operationId)"
                    />
                    <button
                      v-if="assignment.workerName && isBrigadierAssignmentsEditable"
                      type="button"
                      class="field-action field-action--right"
                      aria-label="Очистить исполнителя"
                      title="Очистить исполнителя"
                      @mousedown.prevent
                      @click="clearBrigadierAssignment(assignment.operationId)"
                    >
                      <span class="field-action__icon" aria-hidden="true" />
                    </button>
                    <div
                      v-if="
                        isBrigadierAssignmentDropdownOpen(assignment.operationId) &&
                        isBrigadierAssignmentsEditable
                      "
                      class="assignment-dropdown"
                    >
                      <button
                        v-for="worker in getBrigadierAssignmentOptions(assignment)"
                        :key="worker.id"
                        type="button"
                        class="assignment-dropdown__option"
                        :class="{
                          'assignment-dropdown__option--selected':
                            assignment.workerUserId === worker.id,
                        }"
                        @mousedown.prevent
                        @click="selectBrigadierAssignmentWorker(assignment.operationId, worker)"
                      >
                        <span>{{ worker.name }}</span>
                      </button>
                      <div
                        v-if="getBrigadierAssignmentOptions(assignment).length === 0"
                        class="assignment-dropdown__empty"
                      >
                        Ничего не найдено.
                      </div>
                    </div>
                  </div>
                  <p
                    v-if="
                      isBrigadierAssignmentsEditable &&
                      getBrigadierAssignmentError(assignment)
                    "
                    class="field-error"
                  >
                    {{ getBrigadierAssignmentError(assignment) }}
                  </p>
                </div>
              </div>
            </div>
          </section>

          <div class="modal__actions">
            <button
              v-if="brigadierSaveIssue"
              type="button"
              class="field-error-link field-error--actions"
              @click="scrollToBrigadierSaveIssue"
            >
              {{ brigadierSaveIssue.message }}
            </button>

            <button
              v-if="isBrigadierSaveAvailable"
              type="submit"
              class="primary-button"
              :disabled="!brigadierModalCanSave || brigadierSaveLoading"
            >
              <span class="button-content">
                <span class="button-icon button-icon--save" aria-hidden="true" />
                <span>{{ brigadierSaveLoading ? "Сохранение..." : brigadierModalSaveLabel }}</span>
              </span>
            </button>

            <button
              type="button"
              class="ghost-button"
              @click="closeBrigadierOrderModal"
            >
              <span class="button-content">
                <span class="button-icon button-icon--close" aria-hidden="true" />
                <span>{{ isBrigadierSaveAvailable ? "Отменить" : "Закрыть" }}</span>
              </span>
            </button>
          </div>
        </form>
      </section>
    </div>

    <div
      v-if="isBrigadierSaveConfirmOpen"
      class="modal-backdrop"
      @click.self="closeBrigadierSaveConfirm"
    >
      <section class="confirm-modal" role="dialog" aria-modal="true">
        <div class="confirm-modal__content">
          <p class="confirm-modal__eyebrow">Подтверждение сохранения</p>
          <h2>{{ brigadierSaveConfirmTitle }}</h2>
          <dl class="confirm-modal__details">
            <div>
              <dt>Заказ</dt>
              <dd>{{ brigadierModalOrderNumber || "—" }}</dd>
            </div>
            <div>
              <dt>Изделие</dt>
              <dd>
                {{ brigadierModalProduct?.name || "—" }}
                <template v-if="brigadierModalProduct">
                  · {{ brigadierModalProduct.version }}
                </template>
              </dd>
            </div>
            <div>
              <dt>Вид кожи</dt>
              <dd>{{ brigadierModalLeatherTypeName ?? "Не выбран" }}</dd>
            </div>
            <div>
              <dt>Количество</dt>
              <dd>{{ brigadierModalQuantity }} шт.</dd>
            </div>
            <div v-if="isQualityControlOrderModal">
              <dt>Брак</dt>
              <dd>{{ brigadierModalDefectQuantity || "0" }} шт.</dd>
            </div>
          </dl>
          <p class="confirm-modal__description">
            {{ brigadierSaveConfirmDescription }}
          </p>
        </div>

        <div class="confirm-modal__actions">
          <button
            type="button"
            class="ghost-button"
            :disabled="brigadierSaveLoading"
            @click="closeBrigadierSaveConfirm"
          >
            <span class="button-content">
              <span class="button-icon button-icon--close" aria-hidden="true" />
              <span>Отменить</span>
            </span>
          </button>
          <button
            type="button"
            class="primary-button"
            :disabled="brigadierSaveLoading"
            @click="void saveBrigadierOrder()"
          >
            <span class="button-content">
              <span class="button-icon button-icon--save" aria-hidden="true" />
              <span>{{ brigadierSaveLoading ? "Сохранение..." : "Подтвердить" }}</span>
            </span>
          </button>
        </div>
      </section>
    </div>

    <div
      v-if="workOrderActionConfirm"
      class="modal-backdrop"
      @click.self="closeWorkOrderActionConfirm"
    >
      <section class="confirm-modal" role="dialog" aria-modal="true">
        <div class="confirm-modal__content">
          <p class="confirm-modal__eyebrow">Подтверждение действия</p>
          <h2>{{ workOrderActionConfirmTitle }}</h2>
          <dl class="confirm-modal__details">
            <div>
              <dt>Заказ</dt>
              <dd>{{ workOrderActionConfirm.order.orderNumber }}</dd>
            </div>
            <div>
              <dt>Изделие</dt>
              <dd>
                {{ workOrderActionConfirm.order.productName }}
                · {{ workOrderActionConfirm.order.productVersion }}
              </dd>
            </div>
            <div>
              <dt>Вид кожи</dt>
              <dd>{{ workOrderActionConfirm.order.leatherTypeName ?? "вид кожи не указан" }}</dd>
            </div>
            <div>
              <dt>Количество</dt>
              <dd>{{ workOrderActionConfirm.order.quantity }} шт.</dd>
            </div>
          </dl>
          <p class="confirm-modal__description">
            {{ workOrderActionConfirmDescription }}
          </p>
        </div>

        <div class="confirm-modal__actions">
          <button
            type="button"
            class="ghost-button"
            :disabled="isWorkOrderBusy(workOrderActionConfirm.order.id)"
            @click="closeWorkOrderActionConfirm"
          >
            <span class="button-content">
              <span class="button-icon button-icon--close" aria-hidden="true" />
              <span>Отменить</span>
            </span>
          </button>
          <button
            type="button"
            :class="isWorkOrderActionConfirmDanger
              ? 'ghost-button ghost-button--danger confirm-modal__delete'
              : 'primary-button'"
            :disabled="isWorkOrderBusy(workOrderActionConfirm.order.id)"
            @click="void confirmWorkOrderAction()"
          >
            <span class="button-content">
              <span
                class="button-icon"
                :class="workOrderActionConfirmIcon"
                aria-hidden="true"
              />
              <span>{{ workOrderActionConfirmLabel }}</span>
            </span>
          </button>
        </div>
      </section>
    </div>

    <div
      v-if="workOrderTimeBreakdownModal"
      class="modal-backdrop"
      @click.self="closeWorkOrderTimeBreakdown"
    >
      <section class="modal time-breakdown-modal" role="dialog" aria-modal="true">
        <div class="modal__head">
          <div>
            <p class="modal__eyebrow">Суммарное время</p>
            <h2>Детализация времени</h2>
            <p class="modal__description">
              Заказ {{ workOrderTimeBreakdownModal.order.orderNumber }} ·
              {{ workOrderTimeBreakdownModal.order.productName }}
              · {{ workOrderTimeBreakdownModal.order.productVersion }}
              · {{ workOrderTimeBreakdownModal.order.quantity }} шт.
            </p>
          </div>

          <button type="button" class="ghost-button" @click="closeWorkOrderTimeBreakdown">
            <span class="button-content">
              <span class="button-icon button-icon--close" aria-hidden="true" />
              <span>Закрыть</span>
            </span>
          </button>
        </div>

        <div v-if="workOrderTimeBreakdownError" class="banner banner--error">
          <p>{{ workOrderTimeBreakdownError }}</p>
          <button
            type="button"
            class="ghost-button"
            :disabled="workOrderTimeBreakdownLoading"
            @click="void openWorkOrderTimeBreakdown(workOrderTimeBreakdownModal.order)"
          >
            <span class="button-content">
              <span class="button-icon button-icon--refresh" aria-hidden="true" />
              <span>Повторить</span>
            </span>
          </button>
        </div>

        <div v-else-if="workOrderTimeBreakdownLoading" class="banner">
          <p>Загрузка детализации времени...</p>
        </div>

        <template v-else-if="workOrderTimeBreakdownModal.breakdown">
          <div class="table-wrap time-breakdown-table-wrap">
            <table class="products-table time-breakdown-table">
              <thead>
                <tr>
                  <th>Операция</th>
                  <th>Исполнитель</th>
                  <th>Время</th>
                  <th>Норма на операцию</th>
                  <th>Среднее на изделие</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="workOrderTimeBreakdownModal.breakdown.items.length === 0">
                  <td colspan="5" class="time-breakdown-table__empty">
                    По заказу пока нет завершенных таймеров операций.
                  </td>
                </tr>
                <tr
                  v-for="item in workOrderTimeBreakdownModal.breakdown.items"
                  :key="`${item.operationId ?? 'deleted'}:${item.workerUserId}`"
                >
                  <td>{{ item.operationName }}</td>
                  <td>{{ item.workerUserName }}</td>
                  <td>{{ formatTimerDuration(item.elapsedMs) }}</td>
                  <td>
                    {{
                      item.standardTimeSeconds === null
                        ? "Не указана"
                        : formatStandardTimeInput(item.standardTimeSeconds)
                    }}
                  </td>
                  <td>{{ formatTimerDuration(item.averageElapsedMs) }}</td>
                </tr>
              </tbody>
              <tfoot>
                <tr class="time-breakdown-total-row">
                  <th colspan="2" scope="row">Итого</th>
                  <td>
                    <span class="time-breakdown-total-row__label">По всему заказу</span>
                    <strong>
                      {{ formatTimerDuration(workOrderTimeBreakdownModal.breakdown.totalElapsedMs) }}
                    </strong>
                  </td>
                  <td>
                    <span class="time-breakdown-total-row__label">План на изделие</span>
                    <strong>
                      {{
                        formatTimerDuration(
                          workOrderTimeBreakdownModal.breakdown.totalStandardTimeSeconds * 1000,
                        )
                      }}
                    </strong>
                  </td>
                  <td>
                    <span class="time-breakdown-total-row__label">На одно изделие</span>
                    <strong>
                      {{
                        formatTimerDuration(
                          calculateAverageDuration(
                            workOrderTimeBreakdownModal.breakdown.totalElapsedMs,
                            workOrderTimeBreakdownModal.order.quantity,
                          ),
                        )
                      }}
                    </strong>
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </template>
      </section>
    </div>

    <div
      v-if="isModalOpen"
      class="modal-backdrop"
      @click.self="closeProductModal"
    >
      <section class="modal" role="dialog" aria-modal="true">
        <div class="modal__head">
          <div>
            <h2>{{ modalTitle }}</h2>
            <p class="modal__description">{{ modalDescription }}</p>
          </div>

          <button type="button" class="ghost-button" @click="closeProductModal">
            <span class="button-content">
              <span class="button-icon button-icon--close" aria-hidden="true" />
              <span>Закрыть</span>
            </span>
          </button>
        </div>

        <div v-if="modalError" class="banner banner--error">
          <p>{{ modalError }}</p>
        </div>

        <div v-if="modalLoading" class="banner">
          <p>Загрузка изделия...</p>
        </div>

        <form
          v-else
          class="product-form"
          @submit.prevent="saveProductToApi"
        >
          <div class="product-form__header">
            <div class="form-grid">
              <label class="field">
                <span class="field__label">Наименование изделия</span>
                <input
                  v-model="productName"
                  type="text"
                  class="text-input"
                  :readonly="isViewMode"
                  data-field="product-name"
                  placeholder="Например, кошелек Daily Fold"
                />
                <p
                  v-if="shouldShowFieldError(productName, productNameError)"
                  class="field-error"
                >
                  {{ productNameError }}
                </p>
              </label>

              <label class="field">
                <span class="field__label">Версия</span>
                <input
                  v-model="productVersion"
                  type="text"
                  class="text-input"
                  :readonly="isViewMode"
                  data-field="product-version"
                  placeholder="Например, 1.0"
                />
                <p
                  v-if="shouldShowFieldError(productVersion, productVersionError)"
                  class="field-error"
                >
                  {{ productVersionError }}
                </p>
              </label>

              <label class="field">
                <span class="field__label">Стоимость материала, ₽</span>
                <input
                  :value="formatMoneyInput(productMaterialCostCents)"
                  type="number"
                  min="0"
                  step="0.01"
                  class="text-input"
                  data-field="product-material-cost"
                  placeholder="Не указана"
                  @input="handleProductMaterialCostInput"
                />
                <p v-if="productMaterialCostError" class="field-error">
                  {{ productMaterialCostError }}
                </p>
              </label>
            </div>

            <p v-if="productIdentityError" class="field-error field-error--inline">
              {{ productIdentityError }}
            </p>
          </div>

          <section class="operations-section">
            <div class="operations-section__head">
              <div>
                <span class="field__label">Таблица-дерево операций</span>
                <p class="field__hint">
                  Группы вводятся вручную, операции выбираются из справочника и
                  должны быть уникальными в изделии.
                </p>
              </div>
            </div>

            <div
              v-if="operationTree.length === 0"
              class="empty-state empty-state--operations"
            >
              <p>Операции пока не добавлены.</p>
              <p>Начните с корневого этапа, например `Крой` или `Пошив`.</p>
            </div>

            <p
              v-if="shouldShowValidation && operationTreeError"
              class="field-error field-error--section"
            >
              {{ operationTreeError }}
            </p>

            <div class="operation-table-wrap">
              <table class="operation-table">
                <thead>
                  <tr>
                    <th>Операция</th>
                    <th>Тип</th>
                    <th>Цена, ₽</th>
                    <th>Норма на одно изделие, мм:сс</th>
                    <th>Действия</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in flatOperationRows" :key="row.id">
                    <td>
                      <div
                        class="operation-cell"
                        :style="{ '--level': String(row.level) }"
                      >
                        <span v-if="row.level > 0" class="operation-branch" />

                        <div class="operation-editor">
                          <div v-if="isViewMode" class="operation-text">
                            {{ row.name }}
                          </div>
                          <div v-else class="assignment-input-wrap">
                            <input
                              v-if="row.isGroup"
                              :value="row.name"
                              type="text"
                              class="operation-input operation-input--with-action"
                              :data-operation-id="row.id"
                              autocomplete="off"
                              placeholder="Название группы операций"
                              @input="handleOperationGroupNameInput(row.id, $event)"
                            />
                            <input
                              v-else
                              :value="row.name"
                              type="text"
                              class="operation-input operation-input--with-dropdown"
                              :data-operation-id="row.id"
                              autocomplete="off"
                              placeholder="Название операции"
                              @input="handleOperationNameInput(row.id, $event)"
                              @focus="openOperationNameDropdown(row.id)"
                              @click="openOperationNameDropdown(row.id)"
                              @blur="scheduleOperationNameDropdownClose(row.id)"
                            />
                            <button
                              v-if="row.name"
                              type="button"
                              class="field-action field-action--right"
                              aria-label="Очистить операцию"
                              title="Очистить операцию"
                              @mousedown.prevent
                              @click="
                                row.isGroup
                                  ? clearOperationGroupName(row.id)
                                  : clearOperationName(row.id)
                              "
                            >
                              <span class="field-action__icon" aria-hidden="true" />
                            </button>
                            <div
                              v-if="
                                !row.isGroup && isOperationNameDropdownOpen(row.id)
                              "
                              class="assignment-dropdown"
                            >
                              <button
                                v-for="entry in getOperationNameOptions(row)"
                                :key="entry.id"
                                type="button"
                                class="assignment-dropdown__option"
                                :class="{
                                  'assignment-dropdown__option--selected':
                                    normalizeName(row.name) === normalizeName(entry.name),
                                }"
                                @mousedown.prevent
                                @click="selectOperationName(row.id, entry)"
                              >
                                <span>{{ entry.name }}</span>
                              </button>
                              <div
                                v-if="getOperationNameOptions(row).length === 0"
                                class="assignment-dropdown__empty"
                              >
                                Справочник операций пуст.
                              </div>
                            </div>
                          </div>
                          <p
                            v-if="!isViewMode && shouldShowOperationError(row)"
                            class="field-error"
                          >
                            {{ operationErrors[row.id] }}
                          </p>
                        </div>
                      </div>
                    </td>
                    <td>
                      <span
                        class="operation-badge"
                        :class="{
                          'operation-badge--group': row.isGroup,
                          'operation-badge--leaf': !row.isGroup,
                        }"
                      >
                        {{ row.isGroup ? "Группа" : "Операция" }}
                      </span>
                    </td>
                    <td>
                      <span v-if="row.isGroup" class="readonly-note">
                        Цена только у операций
                      </span>
                      <span v-else-if="isViewMode" class="operation-text">
                        {{ formatMoneyInput(row.priceCents) || "Не указана" }}
                      </span>
                      <input
                        v-else
                        :value="formatMoneyInput(row.priceCents)"
                        type="number"
                        min="0"
                        step="0.01"
                        class="operation-input operation-input--price"
                        :aria-label="`Цена операции ${row.name || row.id}`"
                        @input="handleOperationPriceInput(row.id, $event)"
                      />
                      <p
                        v-if="
                          !isViewMode &&
                          (operationErrors[row.id]?.startsWith('Цена') ||
                            operationErrors[row.id]?.startsWith('У группы'))
                        "
                        class="field-error"
                      >
                        {{ operationErrors[row.id] }}
                      </p>
                    </td>
                    <td>
                      <span v-if="row.isGroup" class="readonly-note">
                        Норма только у операций
                      </span>
                      <span v-else-if="isViewMode" class="operation-text">
                        {{ formatStandardTimeInput(row.standardTimeSeconds) || "Не указана" }}
                      </span>
                      <input
                        v-else
                        :value="formatStandardTimeInput(row.standardTimeSeconds)"
                        type="text"
                        inputmode="numeric"
                        class="operation-input operation-input--standard-time"
                        placeholder="мм:сс"
                        :aria-label="`Норма времени операции ${row.name || row.id}`"
                        @input="handleOperationStandardTimeInput(row.id, $event)"
                        @blur="normalizeOperationStandardTimeInput(row.id, $event)"
                      />
                      <p
                        v-if="
                          !isViewMode &&
                          (operationErrors[row.id]?.startsWith('Норма') ||
                            operationErrors[row.id]?.includes('нормы времени'))
                        "
                        class="field-error"
                      >
                        {{ operationErrors[row.id] }}
                      </p>
                    </td>
                    <td>
                      <div class="operation-actions">
                        <span v-if="isViewMode" class="readonly-note">
                          Структура без изменений
                        </span>
                        <template v-else>
                          <button
                            type="button"
                            class="icon-action-button"
                            title="Переместить выше"
                            aria-label="Переместить выше"
                            :disabled="!row.canMoveUp"
                            @click="moveOperationUp(row.id)"
                          >
                            <span
                              class="action-icon action-icon--up"
                              aria-hidden="true"
                            />
                          </button>
                          <button
                            type="button"
                            class="icon-action-button"
                            title="Переместить ниже"
                            aria-label="Переместить ниже"
                            :disabled="!row.canMoveDown"
                            @click="moveOperationDown(row.id)"
                          >
                            <span
                              class="action-icon action-icon--down"
                              aria-hidden="true"
                            />
                          </button>
                          <button
                            type="button"
                            class="icon-action-button"
                            title="Переместить внутрь предыдущей операции"
                            aria-label="Переместить внутрь предыдущей операции"
                            :disabled="!row.canIndent"
                            @click="indentOperation(row.id)"
                          >
                            <span
                              class="action-icon action-icon--indent"
                              aria-hidden="true"
                            />
                          </button>
                          <button
                            type="button"
                            class="icon-action-button"
                            title="Поднять на уровень выше"
                            aria-label="Поднять на уровень выше"
                            :disabled="!row.canOutdent"
                            @click="outdentOperation(row.id)"
                          >
                            <span
                              class="action-icon action-icon--outdent"
                              aria-hidden="true"
                            />
                          </button>
                          <button
                            type="button"
                            class="icon-action-button"
                            title="Создать вложенную операцию"
                            aria-label="Создать вложенную операцию"
                            @click="addChildOperation(row.id)"
                          >
                            <span
                              class="action-icon action-icon--child"
                              aria-hidden="true"
                            />
                          </button>
                          <button
                            type="button"
                            class="icon-action-button"
                            title="Создать следующую операцию"
                            aria-label="Создать следующую операцию"
                            @click="addSiblingOperation(row.id)"
                          >
                            <span
                              class="action-icon action-icon--sibling"
                              aria-hidden="true"
                            />
                          </button>
                          <button
                            type="button"
                            class="ghost-button ghost-button--danger"
                            @click="removeOperation(row.id)"
                          >
                            <span class="button-content">
                              <span class="button-icon button-icon--delete" aria-hidden="true" />
                              <span>Удалить</span>
                            </span>
                          </button>
                        </template>
                      </div>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div v-if="!isViewMode" class="operations-footer">
              <button
                type="button"
                class="secondary-button secondary-button--add"
                data-field="add-root-operation"
                @click="addRootOperation"
              >
                <span class="button-content">
                  <span class="button-icon button-icon--plus" aria-hidden="true" />
                  <span>
                    {{
                      operationTree.length > 0
                        ? "Добавить корневую операцию"
                        : "Добавить первую операцию"
                    }}
                  </span>
                </span>
              </button>
            </div>
          </section>

          <div class="modal__actions">
            <button
              v-if="saveBlockIssue"
              type="button"
              class="field-error-link field-error--actions"
              @click="scrollToSaveBlockIssue"
            >
              {{ saveBlockIssue.message }}
            </button>

            <button
              type="submit"
              class="primary-button"
              :class="{ 'primary-button--blocked': !canSaveProduct && !saveLoading }"
              :aria-disabled="!canSaveProduct"
              :disabled="saveLoading"
            >
              <span class="button-content">
                <span class="button-icon button-icon--save" aria-hidden="true" />
                <span>
                  {{
                    saveLoading
                      ? "Сохранение..."
                      : isViewMode
                        ? "Сохранить стоимость"
                        : "Сохранить изделие"
                  }}
                </span>
              </span>
            </button>

            <button type="button" class="ghost-button" @click="closeProductModal">
              <span class="button-content">
                <span class="button-icon button-icon--close" aria-hidden="true" />
                <span>{{ isViewMode ? "Закрыть" : "Отменить" }}</span>
              </span>
            </button>
          </div>
        </form>
      </section>
    </div>

    <div
      v-if="isDeleteModalOpen && productPendingDelete"
      class="modal-backdrop"
      @click.self="closeDeleteConfirmation"
    >
      <section class="confirm-modal" role="dialog" aria-modal="true">
        <div class="confirm-modal__content">
          <p class="confirm-modal__eyebrow">Подтверждение удаления</p>
          <h2>Удалить изделие?</h2>
          <dl class="confirm-modal__details">
            <div>
              <dt>Наименование</dt>
              <dd>{{ productPendingDelete.name }}</dd>
            </div>
            <div>
              <dt>Версия</dt>
              <dd>{{ productPendingDelete.version }}</dd>
            </div>
          </dl>
          <p class="confirm-modal__description">
            Будет удалено изделие вместе с деревом его операций. Это действие
            нельзя отменить.
          </p>
        </div>

        <div class="confirm-modal__actions">
          <button
            type="button"
            class="ghost-button"
            :disabled="isProductBusy(productPendingDelete.id)"
            @click="closeDeleteConfirmation"
          >
            <span class="button-content">
              <span class="button-icon button-icon--close" aria-hidden="true" />
              <span>Отменить</span>
            </span>
          </button>
          <button
            type="button"
            class="ghost-button ghost-button--danger confirm-modal__delete"
            :disabled="isProductBusy(productPendingDelete.id)"
            @click="handleDeleteProduct(productPendingDelete)"
          >
            <span class="button-content">
              <span class="button-icon button-icon--delete" aria-hidden="true" />
              <span>{{ isProductBusy(productPendingDelete.id) ? "Удаление..." : "Удалить" }}</span>
            </span>
          </button>
        </div>
      </section>
    </div>

    <div
      v-if="isUserDeleteModalOpen && userPendingDelete"
      class="modal-backdrop"
      @click.self="closeUserDeleteConfirmation"
    >
      <section class="confirm-modal" role="dialog" aria-modal="true">
        <div class="confirm-modal__content">
          <p class="confirm-modal__eyebrow">Подтверждение удаления</p>
          <h2>Удалить пользователя?</h2>
          <dl class="confirm-modal__details">
            <div>
              <dt>Имя</dt>
              <dd>{{ userPendingDelete.name || "Без имени" }}</dd>
            </div>
            <div>
              <dt>Статус</dt>
              <dd>{{ userPendingDelete.isActive ? "Активен" : "Деактивирован" }}</dd>
            </div>
          </dl>
          <p class="confirm-modal__description">
            Запись пользователя будет удалена из таблицы. Это действие нельзя
            отменить.
          </p>
        </div>

        <div class="confirm-modal__actions">
          <button
            type="button"
            class="ghost-button"
            @click="closeUserDeleteConfirmation"
          >
            <span class="button-content">
              <span class="button-icon button-icon--close" aria-hidden="true" />
              <span>Отменить</span>
            </span>
          </button>
          <button
            type="button"
            class="ghost-button ghost-button--danger confirm-modal__delete"
            @click="deleteUser(userPendingDelete)"
          >
            <span class="button-content">
              <span class="button-icon button-icon--delete" aria-hidden="true" />
              <span>Удалить</span>
            </span>
          </button>
        </div>
      </section>
    </div>

    <div
      v-if="workerAssignmentStatusConfirm"
      class="modal-backdrop"
      @click.self="closeWorkerAssignmentStatusConfirm"
    >
      <section class="confirm-modal" role="dialog" aria-modal="true">
        <div class="confirm-modal__content">
          <p class="confirm-modal__eyebrow">Подтверждение действия</p>
          <h2>{{ workerAssignmentStatusConfirmTitle }}</h2>
          <dl class="confirm-modal__details">
            <div>
              <dt>Заказ</dt>
              <dd>{{ workerAssignmentStatusConfirm.timer.orderNumber ?? "Без номера" }}</dd>
            </div>
            <div>
              <dt>Операция</dt>
              <dd>{{ workerAssignmentStatusConfirm.timer.label }}</dd>
            </div>
          </dl>
          <p class="confirm-modal__description">
            {{ workerAssignmentStatusConfirmDescription }}
          </p>
        </div>

        <div class="confirm-modal__actions">
          <button
            type="button"
            class="ghost-button"
            :disabled="workerTimerSubmitting"
            @click="closeWorkerAssignmentStatusConfirm"
          >
            <span class="button-content">
              <span class="button-icon button-icon--close" aria-hidden="true" />
              <span>Отменить</span>
            </span>
          </button>
          <button
            type="button"
            :class="workerAssignmentStatusConfirm.status === 'hidden'
              ? 'ghost-button ghost-button--danger confirm-modal__delete'
              : 'ghost-button'"
            :disabled="workerTimerSubmitting"
            @click="void confirmWorkerAssignmentStatusChange()"
          >
            <span class="button-content">
              <span
                class="button-icon"
                :class="workerAssignmentStatusConfirmIcon"
                aria-hidden="true"
              />
              <span>{{ workerAssignmentStatusConfirmLabel }}</span>
            </span>
          </button>
        </div>
      </section>
    </div>

    <div
      v-if="isWorkerQrScannerOpen"
      class="modal-backdrop"
      @click.self="closeWorkerQrScanner"
    >
      <section
        class="confirm-modal worker-qr-scanner-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="worker-qr-scanner-title"
      >
        <div class="confirm-modal__content">
          <p class="confirm-modal__eyebrow">Быстрый переход</p>
          <h2 id="worker-qr-scanner-title">Сканирование QR-кода</h2>
          <p class="confirm-modal__description">
            Наведите камеру на QR-код в печатной форме заказа.
          </p>

          <div class="worker-qr-scanner-preview">
            <video
              ref="workerQrScannerVideo"
              autoplay
              muted
              playsinline
              aria-label="Изображение с камеры для сканирования QR-кода"
            />
            <span class="worker-qr-scanner-frame" aria-hidden="true" />
            <span v-if="workerQrScannerStarting" class="worker-qr-scanner-loading">
              Запуск камеры...
            </span>
          </div>

          <p v-if="workerQrScannerError" class="field-error" role="alert">
            {{ workerQrScannerError }}
          </p>
        </div>

        <div class="confirm-modal__actions">
          <button type="button" class="ghost-button" @click="closeWorkerQrScanner">
            <span class="button-content">
              <span class="button-icon button-icon--close" aria-hidden="true" />
              <span>Закрыть</span>
            </span>
          </button>
        </div>
      </section>
    </div>

    <div
      v-if="isWorkerDayEndConfirmOpen"
      class="modal-backdrop"
      @click.self="closeWorkerDayEndConfirm"
    >
      <section class="confirm-modal" role="dialog" aria-modal="true">
        <div class="confirm-modal__content">
          <p class="confirm-modal__eyebrow">Подтверждение завершения</p>
          <h2>Закончить рабочий день?</h2>
          <p class="confirm-modal__description">
            Будут остановлены текущий активный таймер и рабочая смена исполнителя.
          </p>
        </div>

        <div class="confirm-modal__actions">
          <button
            type="button"
            class="ghost-button"
            @click="closeWorkerDayEndConfirm"
          >
            <span class="button-content">
              <span class="button-icon button-icon--close" aria-hidden="true" />
              <span>Отменить</span>
            </span>
          </button>
          <button
            type="button"
            class="ghost-button ghost-button--danger confirm-modal__delete"
            :disabled="workerTimerSubmitting"
            @click="void endWorkerDay()"
          >
            <span class="button-content">
              <span class="button-icon button-icon--stop" aria-hidden="true" />
              <span>Закончить день</span>
            </span>
          </button>
        </div>
      </section>
    </div>

    <section v-if="printableWorkOrder" class="print-sheet" aria-label="Печатная форма заказа">
      <h1>Заказ {{ printableWorkOrder.orderNumber }}</h1>
      <table class="print-order-table">
        <tbody>
          <tr>
            <th>Изделие</th>
            <td>
              {{ printableWorkOrder.productName }} · {{ printableWorkOrder.productVersion }}
            </td>
          </tr>
          <tr>
            <th>Тип кожи</th>
            <td>{{ printableWorkOrder.leatherTypeName ?? "вид кожи не указан" }}</td>
          </tr>
          <tr>
            <th>Количество</th>
            <td>{{ printableWorkOrder.quantity }} шт.</td>
          </tr>
          <tr>
            <th colspan="2" class="print-order-table__section">
              Список операций с исполнителями
            </th>
          </tr>
          <tr class="print-order-table__head">
            <th>Операция</th>
            <th>Исполнитель</th>
          </tr>
          <tr
            v-for="assignment in printableWorkOrder.assignments"
            :key="assignment.id"
          >
            <td>{{ assignment.operationName }}</td>
            <td>{{ assignment.workerUserName ?? "" }}</td>
          </tr>
          <tr v-if="printableWorkOrder.assignments.length === 0">
            <td colspan="2">Операции с исполнителями не назначены.</td>
          </tr>
        </tbody>
      </table>

      <div v-if="printableWorkOrderQrCode" class="print-order-qr-list">
        <figure
          v-for="copyIndex in PRINT_QR_CODE_COUNT"
          :key="copyIndex"
          class="print-order-qr"
        >
          <img
            :src="printableWorkOrderQrCode"
            :alt="`QR-код таймеров заказа ${printableWorkOrder.orderNumber}`"
          />
          <figcaption>
            <strong>{{ printableWorkOrder.orderNumber }}</strong>
            <span>{{ printableWorkOrder.productName }}</span>
            <span>{{ printableWorkOrder.leatherTypeName ?? "вид кожи не указан" }}</span>
            <span>{{ printableWorkOrder.quantity }} шт.</span>
          </figcaption>
        </figure>
      </div>
    </section>
  </main>
</template>

<style scoped>
.page {
  --color-bg: #f4f7fa;
  --color-surface: #ffffff;
  --color-surface-alt: #e9eef3;
  --color-surface-soft: #e3eff8;
  --color-border: #d6dee6;
  --color-muted: #8a96a3;
  --color-primary: #2f6ea3;
  --color-primary-hover: #245e8e;
  --color-accent-muted: #245e8e;
  --color-text: #1f2a33;
  --color-text-secondary: #5f6b76;
  --color-text-muted: #86919c;
  --color-success: #5e8f74;
  --color-warning: #c39a52;
  --color-danger: #c56b6b;
  --color-neutral: #8a96a3;
  padding: 24px;
  background: var(--color-bg);
  color: var(--color-text);
}

.shell {
  min-height: calc(100vh - 48px);
  padding: 28px;
  border: 1px solid var(--color-border);
  border-radius: 28px;
  background: var(--color-bg);
  box-shadow: 0 20px 44px rgba(31, 42, 51, 0.08);
  backdrop-filter: blur(12px);
}

.auth-shell {
  min-height: calc(100vh - 48px);
  display: grid;
  place-items: center;
}

.auth-card {
  width: min(520px, 100%);
  display: grid;
  gap: 18px;
  padding: 28px;
  border: 1px solid var(--color-border);
  border-radius: 28px;
  background: var(--color-surface);
  box-shadow: 0 18px 36px rgba(31, 42, 51, 0.08);
}

.auth-card__head {
  display: grid;
  gap: 14px;
}

.auth-card__description {
  margin: 10px 0 0;
  color: var(--color-text-secondary);
}

.auth-card__actions {
  display: flex;
  justify-content: flex-end;
}

.header {
  display: flex;
  gap: 14px;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  margin-bottom: 28px;
}

.brand-block {
  flex: 0 0 auto;
  align-self: center;
}

h1,
h2 {
  margin: 0;
  color: var(--color-text);
  font-family: "Sora", "Inter", sans-serif;
}

h2 {
  font-size: 1.5rem;
}

.brand-logo-frame {
  width: clamp(360px, 44vw, 760px);
  height: 180px;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: center;
}

.brand-logo-frame--auth {
  width: min(460px, 100%);
  height: 140px;
}

.brand-logo {
  display: block;
  width: 364%;
  height: 504px;
  object-fit: cover;
  object-position: center;
}

.brand-logo--auth {
  width: 100%;
  height: 100%;
  object-fit: contain;
  object-position: center;
  transform: scale(1.72);
  transform-origin: center;
}

.tabs {
  display: inline-flex;
  gap: 10px;
  padding: 8px;
  border-radius: 18px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  flex-wrap: wrap;
  align-self: center;
}

.current-user-card {
  min-width: 260px;
  display: grid;
  gap: 8px;
  padding: 10px 14px;
  border: 1px solid var(--color-border);
  border-radius: 16px;
  background: var(--color-surface);
  text-align: left;
}

.current-user-card__identity {
  display: flex;
  align-items: baseline;
  gap: 8px;
  flex-wrap: wrap;
}

.current-user-card strong {
  font-size: 1rem;
  line-height: 1;
  font-family: "Sora", "Inter", sans-serif;
}

.current-user-card__roles {
  color: var(--color-text-secondary);
  font-size: 0.85rem;
  line-height: 1;
}

.current-user-card__actions {
  display: flex;
  gap: 8px;
  justify-content: flex-start;
  flex-wrap: wrap;
  margin-top: 0;
}

.current-user-card .section-label {
  margin: 0;
  white-space: nowrap;
}

.current-user-card .ghost-button {
  padding: 8px 10px;
  font-size: 0.86rem;
}

.current-user-card__action-label {
  display: inline;
}

.tab-button,
.primary-button,
.secondary-button,
.ghost-button,
.status-button {
  border: 0;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    background-color 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease,
    opacity 0.18s ease;
}

.tab-button:hover,
.primary-button:hover,
.secondary-button:hover,
.ghost-button:hover,
.status-button:hover {
  transform: translateY(-1px);
}

.primary-button:disabled,
.secondary-button:disabled,
.ghost-button:disabled,
.status-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
  transform: none;
}

.button-content {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.tab-button {
  padding: 14px 20px;
  border-radius: 14px;
  background: transparent;
  color: var(--color-text-secondary);
  font-weight: 600;
}

.tab-button--active {
  background: var(--color-primary);
  color: #fff;
  box-shadow: 0 10px 22px rgba(47, 110, 163, 0.16);
}

.placeholder-panel,
.constructor-panel,
.modal {
  border: 1px solid var(--color-border);
  border-radius: 24px;
  background: var(--color-surface);
  box-shadow: 0 18px 36px rgba(31, 42, 51, 0.08);
}

.placeholder-panel {
  padding: 28px;
}

.placeholder-label,
.section-label {
  margin: 0 0 10px;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.constructor-panel {
  padding: 22px;
}

.panel-head,
.modal__head {
  display: flex;
  gap: 16px;
  align-items: flex-start;
  justify-content: space-between;
}

.panel-head {
  margin-bottom: 20px;
}

.panel-head--stacked {
  flex-direction: column;
  align-items: flex-start;
}

.worker-panel {
  display: grid;
  gap: 22px;
}

.worker-panel__head {
  margin-bottom: 0;
}

.worker-panel__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  flex-wrap: wrap;
}

.worker-panel__subtitle {
  margin: 10px 0 0;
  color: var(--color-text-secondary);
}

.worker-summary {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.worker-summary__card {
  display: grid;
  gap: 8px;
  padding: 18px 20px;
  border-radius: 18px;
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
}

.worker-summary__card strong {
  color: var(--color-text);
  font-size: 1.1rem;
  font-family: "Sora", "Inter", sans-serif;
}

.worker-summary__value {
  font-weight: 700;
  font-size: 2rem;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  color: var(--color-text);
  font-family: "Sora", "Inter", sans-serif;
}

.worker-timer-bar,
.worker-group__timers {
  display: grid;
  gap: 14px;
}

.worker-timer-bar {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.worker-groups {
  display: grid;
  gap: 18px;
}

.worker-group {
  display: grid;
  gap: 14px;
  padding: 18px;
  border-radius: 22px;
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
}

.worker-group--focused {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(47, 110, 163, 0.14);
}

.worker-group__head {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  cursor: pointer;
  text-align: left;
}

.worker-group__head h3 {
  margin: 0;
  color: var(--color-text);
  font-size: 1.05rem;
}

.worker-group__title {
  display: inline-flex;
  align-items: center;
  gap: 12px;
}

.worker-group__chevron {
  width: 12px;
  height: 12px;
  border-right: 2px solid var(--color-text-secondary);
  border-bottom: 2px solid var(--color-text-secondary);
  transform: rotate(45deg);
  transition: transform 0.18s ease;
  flex: 0 0 auto;
}

.worker-group__chevron--expanded {
  transform: rotate(225deg);
}

.statistics-panel {
  display: grid;
  gap: 22px;
}

.statistics-panel__head {
  display: grid;
  grid-template-columns: minmax(220px, auto) minmax(0, 1fr);
  align-items: start;
}

.statistics-toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: start;
  gap: 12px;
  width: 100%;
  min-width: 0;
}

.statistics-period-control {
  display: grid;
  grid-template-columns: auto auto;
  align-items: center;
  justify-content: end;
  gap: 10px;
  min-width: 0;
}

.statistics-presets {
  flex: 0 0 auto;
}

.statistics-date-range {
  display: inline-grid;
  grid-template-columns: minmax(152px, auto) auto minmax(152px, auto) auto;
  align-items: center;
  gap: 8px;
  justify-self: end;
  min-width: 0;
  padding: 6px;
  border: 1px solid var(--color-border);
  border-radius: 16px;
  background: var(--color-surface);
  transition:
    border-color 0.18s ease,
    box-shadow 0.18s ease;
}

.statistics-date-range--active {
  border-color: rgba(47, 110, 163, 0.42);
  box-shadow: 0 10px 22px rgba(47, 110, 163, 0.08);
}

.statistics-date-field {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding-left: 8px;
}

.statistics-date-field__label {
  color: var(--color-text-secondary);
  font-size: 0.78rem;
  font-weight: 800;
}

.statistics-date-field__input {
  width: 152px;
  min-height: 42px;
  border: 0;
  border-radius: 10px;
  padding: 0 10px;
  background: var(--color-surface-alt);
  color: var(--color-text);
  font: inherit;
  font-weight: 700;
}

.statistics-date-field__input:focus-visible {
  outline: 3px solid rgba(47, 110, 163, 0.18);
  outline-offset: 2px;
}

.statistics-date-range__divider {
  width: 1px;
  height: 28px;
  background: var(--color-border);
}

.statistics-date-range__apply {
  min-height: 42px;
  padding: 0 14px;
  background: var(--color-surface-alt);
  color: var(--color-text);
}

.statistics-toolbar__actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-wrap: wrap;
}

.statistics-export-button {
  min-width: 96px;
}

.statistics-refresh-button {
  min-width: 122px;
}

.statistics-kpis {
  display: grid;
  gap: 14px;
  grid-template-columns: repeat(7, minmax(0, 1fr));
}

.statistics-kpi-card,
.statistics-card {
  border: 1px solid var(--color-border);
  border-radius: 20px;
  background: var(--color-surface-alt);
}

.statistics-kpi-card {
  display: grid;
  gap: 10px;
  padding: 16px 18px;
}

.statistics-kpi-card strong {
  font-family: "Sora", "Inter", sans-serif;
  font-size: 1.45rem;
  color: var(--color-text);
}

.statistics-grid {
  display: grid;
  gap: 18px;
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

.statistics-card {
  display: grid;
  gap: 18px;
  padding: 18px;
}

.statistics-card--wide {
  grid-column: span 2;
}

.statistics-card__head h3 {
  margin: 0;
  color: var(--color-text);
  font-size: 1.05rem;
}

.statistics-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
}

.statistics-legend__item {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  color: var(--color-text-secondary);
  font-size: 0.88rem;
}

.statistics-legend__swatch {
  width: 12px;
  height: 12px;
  border-radius: 4px;
}

.statistics-legend__swatch--operation {
  background: var(--color-primary);
}

.statistics-legend__swatch--preparation {
  background: var(--color-success);
}

.statistics-legend__swatch--break {
  background: var(--color-warning);
}

.statistics-legend__swatch--idle {
  background: var(--color-danger);
}

.stacked-chart {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(52px, 1fr));
  align-items: end;
}

.stacked-chart__item {
  display: grid;
  gap: 8px;
  justify-items: center;
}

.stacked-chart__column {
  width: 100%;
  height: 180px;
  display: flex;
  flex-direction: column-reverse;
  justify-content: flex-start;
  overflow: hidden;
  border-radius: 16px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
}

.stacked-chart__segment {
  display: block;
  width: 100%;
  min-height: 0;
}

.stacked-chart__value,
.stacked-chart__label {
  font-size: 0.78rem;
  color: var(--color-text-secondary);
}

.stacked-chart__value {
  font-weight: 700;
  color: var(--color-text);
}

.statistics-bars {
  display: grid;
  gap: 14px;
}

.statistics-bar-row {
  display: grid;
  gap: 8px;
}

.statistics-bar-row__meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
}

.statistics-bar-row__meta--secondary {
  margin-top: -2px;
}

.statistics-bar-row__meta strong {
  color: var(--color-text);
}

.statistics-bar-row__meta span {
  color: var(--color-text-secondary);
  font-size: 0.88rem;
}

.statistics-bar-row__track {
  height: 10px;
  border-radius: 999px;
  background: var(--color-surface);
  overflow: hidden;
}

.statistics-bar-row__fill {
  display: block;
  height: 100%;
  border-radius: 999px;
  background: var(--color-primary);
}

.statistics-bar-row__fill--muted {
  background: var(--color-text-muted);
}

.statistics-bar-row__fill--success {
  background: var(--color-success);
}

.mini-chart {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(36px, 1fr));
  align-items: end;
}

.mini-chart__item {
  display: grid;
  gap: 8px;
  justify-items: center;
}

.mini-chart__bar {
  display: block;
  width: 100%;
  height: 160px;
  min-height: 6px;
  align-self: end;
  border-radius: 14px;
  background: var(--color-danger);
}

.mini-chart__label {
  font-size: 0.76rem;
  color: var(--color-text-secondary);
}

.worker-timer-button {
  position: relative;
  width: 100%;
  padding: 16px 18px;
  border: 1px solid var(--color-border);
  border-radius: 18px;
  background: var(--color-surface);
  color: var(--color-text);
  cursor: pointer;
  display: grid;
  gap: 10px;
  text-align: left;
  transition:
    transform 0.18s ease,
    background-color 0.18s ease,
    box-shadow 0.18s ease,
    border-color 0.18s ease,
    color 0.18s ease,
    opacity 0.18s ease;
}

.worker-timer-button::before {
  content: "";
  position: absolute;
  top: 10px;
  bottom: 10px;
  left: 0;
  width: 0;
  border-radius: 0 999px 999px 0;
  background: var(--color-primary);
  opacity: 0;
  transition:
    width 0.18s ease,
    opacity 0.18s ease;
}

.worker-timer-button:hover {
  transform: translateY(-1px);
  box-shadow: 0 14px 28px rgba(31, 42, 51, 0.08);
}

.worker-timer-button:disabled {
  cursor: not-allowed;
  opacity: 0.55;
  transform: none;
  box-shadow: none;
}

.worker-timer-button--secondary {
  background: var(--color-surface-alt);
}

.worker-timer-button--operation {
  grid-template-columns: minmax(0, 1fr) auto;
  align-items: center;
}

.worker-timer-button--active {
  border-color: var(--color-primary);
  background: linear-gradient(135deg, rgba(47, 110, 163, 0.22), var(--color-surface-soft));
  box-shadow:
    0 0 0 2px rgba(47, 110, 163, 0.18),
    0 18px 32px rgba(47, 110, 163, 0.16);
}

.worker-timer-button--active::before {
  width: 6px;
  opacity: 1;
}

.worker-timer-button--active .worker-timer-button__label,
.worker-timer-button--active .worker-timer-button__value,
.worker-timer-button--active .worker-timer-button__order,
.worker-timer-button--active .button-icon {
  color: var(--color-primary-hover);
}

.worker-timer-button__meta {
  display: grid;
  gap: 6px;
}

.worker-timer-button__heading {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.worker-timer-button__label {
  font-weight: 700;
  font-size: 1.3rem;
  line-height: 1.15;
}

.worker-timer-button__order {
  color: var(--color-primary-hover);
  font-size: 1.15rem;
  font-weight: 800;
  line-height: 1.1;
}

.worker-timer-button__value {
  font-weight: 700;
  font-size: 2rem;
  line-height: 1;
  font-variant-numeric: tabular-nums;
  color: var(--color-text);
  font-family: "Sora", "Inter", sans-serif;
}

.worker-filter-toolbar {
  grid-template-columns: minmax(220px, 320px);
  margin-top: 18px;
}

.worker-filter-select {
  min-width: 0;
}

.worker-status-filter {
  width: 100%;
}

.worker-status-filter .worker-filter-select {
  padding-right: 44px;
}

.worker-status-filter__chevron {
  position: absolute;
  top: 50%;
  right: 16px;
  width: 8px;
  height: 8px;
  border-right: 2px solid var(--color-text-secondary);
  border-bottom: 2px solid var(--color-text-secondary);
  pointer-events: none;
  transform: translateY(-65%) rotate(45deg);
}

.worker-status-filter__dropdown {
  z-index: 30;
}

.worker-operation-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 12px;
  align-items: center;
}

.worker-operation-row__actions {
  display: inline-flex;
  flex-wrap: wrap;
  gap: 12px;
  justify-content: flex-end;
}

.modal__head {
  margin-bottom: 22px;
}

.modal__description {
  margin: 10px 0 0;
  max-width: 56ch;
  color: var(--color-text-secondary);
}

.primary-button {
  padding: 14px 18px;
  border-radius: 16px;
  background: linear-gradient(135deg, var(--color-primary) 0%, var(--color-primary-hover) 100%);
  color: #fff;
  font-weight: 700;
  box-shadow: 0 14px 28px rgba(47, 110, 163, 0.16);
}

.primary-button--blocked {
  opacity: 0.55;
  box-shadow: none;
}

.primary-button--blocked:hover {
  transform: none;
}

.secondary-button {
  padding: 10px 14px;
  border-radius: 12px;
  background: var(--color-surface-alt);
  color: var(--color-text);
  border: 1px solid var(--color-border);
  font-weight: 600;
}

.secondary-button--add {
  width: fit-content;
  background: var(--color-surface-soft);
  color: var(--color-text);
}

.ghost-button {
  padding: 10px 14px;
  border-radius: 12px;
  background: transparent;
  color: var(--color-text-secondary);
  font-weight: 600;
}

.ghost-button--danger {
  color: var(--color-danger);
}

.action-link {
  display: inline-flex;
  align-items: center;
  width: fit-content;
  padding: 4px 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: var(--color-primary-hover);
  font: inherit;
  font-weight: 700;
  line-height: 1.25;
  text-align: left;
  text-decoration: underline;
  text-decoration-color: rgba(36, 94, 142, 0.32);
  text-decoration-thickness: 1px;
  text-underline-offset: 4px;
  cursor: pointer;
  transition:
    color 0.18s ease,
    opacity 0.18s ease,
    text-decoration-color 0.18s ease,
    transform 0.18s ease;
}

.action-link:hover {
  color: var(--color-primary);
  text-decoration-color: currentColor;
  transform: translateY(-1px);
}

.action-link:disabled {
  cursor: not-allowed;
  opacity: 0.5;
  transform: none;
}

.action-link--danger {
  color: var(--color-danger);
  text-decoration-color: rgba(197, 107, 107, 0.36);
}

.action-link--danger:hover {
  color: #a84d4d;
}

.sort-header-button {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 28px;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  font: inherit;
  font-weight: 800;
  text-align: left;
  cursor: pointer;
}

.sort-header-button__icon {
  position: relative;
  width: 10px;
  height: 14px;
  flex: 0 0 10px;
  opacity: 0.42;
}

.sort-header-button__icon::before,
.sort-header-button__icon::after {
  content: "";
  position: absolute;
  left: 1px;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
}

.sort-header-button__icon::before {
  top: 0;
  border-bottom: 5px solid currentColor;
}

.sort-header-button__icon::after {
  bottom: 0;
  border-top: 5px solid currentColor;
}

.sort-header-button--active .sort-header-button__icon {
  opacity: 1;
}

.sort-header-button__icon--asc::after,
.sort-header-button__icon--desc::before {
  opacity: 0.24;
}

.toolbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto auto;
  gap: 16px;
  margin-bottom: 18px;
}

.field {
  display: grid;
  gap: 10px;
  align-content: start;
}

.field--inline {
  align-content: start;
}

.toolbar > .field--inline:not(:first-child) {
  width: fit-content;
  justify-self: start;
}

.dictionary-form {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 16px;
  align-items: start;
  margin-bottom: 18px;
  padding: 16px;
  border: 1px solid var(--color-border);
  border-radius: 18px;
  background: var(--color-surface-alt);
}

.dictionary-form .primary-button {
  align-self: end;
}

.filter-input-wrap {
  position: relative;
}

.segmented-control {
  display: inline-flex;
  gap: 6px;
  padding: 6px;
  border-radius: 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
}

.segmented-control--wrap {
  flex-wrap: wrap;
}

.segmented-control__button {
  border: 0;
  border-radius: 12px;
  padding: 12px 14px;
  background: transparent;
  color: var(--color-text-secondary);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    background-color 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease;
}

.segmented-control__button--icon {
  width: 40px;
  height: 40px;
  padding: 0;
  display: grid;
  place-items: center;
}

.segmented-control__button:hover {
  transform: translateY(-1px);
}

.segmented-control__button--active {
  background: var(--color-primary);
  color: #fff;
  box-shadow: 0 10px 22px rgba(47, 110, 163, 0.12);
}

.field__label {
  font-size: 0.88rem;
  font-weight: 700;
  color: var(--color-text-secondary);
}

.field__hint {
  margin: 6px 0 0;
  font-size: 0.92rem;
  color: var(--color-text-muted);
}

.checkbox-field {
  min-height: 46px;
  align-self: end;
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 12px 14px;
  border: 1px solid var(--color-border);
  border-radius: 14px;
  background: var(--color-surface);
  color: var(--color-text);
  font-weight: 700;
  cursor: pointer;
}

.checkbox-field input {
  width: 18px;
  height: 18px;
  margin: 0;
  accent-color: var(--color-primary);
}

.text-input,
.select-input,
.operation-input,
.operation-text {
  width: 100%;
  border: 1px solid var(--color-border);
  border-radius: 14px;
  background: var(--color-surface);
  color: var(--color-text);
}

.text-input,
.select-input {
  padding: 14px 16px;
}

.text-input--with-action {
  padding-left: 52px;
}

.text-input--with-clear {
  padding-right: 52px;
}

.text-input--selectlike {
  cursor: pointer;
}

.operation-input--with-dropdown,
.operation-input--with-action {
  padding-right: 52px;
}

.field-action {
  position: absolute;
  top: 50%;
  left: 8px;
  transform: translateY(-50%);
  border: 0;
  border-radius: 10px;
  width: 36px;
  height: 36px;
  display: grid;
  place-items: center;
  padding: 0;
  background: var(--color-surface-soft);
  color: var(--color-text-secondary);
  cursor: pointer;
}

.field-action--right {
  left: auto;
  right: 8px;
}

.field-action__icon {
  position: relative;
  width: 14px;
  height: 14px;
}

.field-action__icon::before,
.field-action__icon::after {
  content: "";
  position: absolute;
  top: 6px;
  left: 0;
  width: 14px;
  height: 2px;
  border-radius: 999px;
  background: currentColor;
}

.field-action__icon::before {
  transform: rotate(45deg);
}

.field-action__icon::after {
  transform: rotate(-45deg);
}

.toolbar-icon {
  position: relative;
  width: 18px;
  height: 18px;
  display: inline-block;
}

.toolbar-icon::before,
.toolbar-icon::after {
  content: "";
  position: absolute;
  border-radius: 999px;
  background: currentColor;
}

.toolbar-icon--all::before,
.toolbar-icon--all::after {
  width: 14px;
  height: 2px;
  left: 2px;
}

.toolbar-icon--all::before {
  top: 5px;
  box-shadow: 0 5px 0 0 currentColor;
}

.toolbar-icon--all::after {
  top: 14px;
}

.toolbar-icon--active::before {
  inset: 2px;
  border: 2px solid currentColor;
  background: transparent;
}

.toolbar-icon--active::after {
  width: 6px;
  height: 6px;
  top: 6px;
  left: 6px;
}

.toolbar-icon--inactive::before {
  inset: 2px;
  border: 2px solid currentColor;
  background: transparent;
}

.toolbar-icon--inactive::after {
  width: 16px;
  height: 2px;
  top: 8px;
  left: 1px;
  transform: rotate(-45deg);
}

.toolbar-icon--asc::after {
  width: 10px;
  height: 6px;
  top: 1px;
  left: 4px;
  clip-path: polygon(50% 0, 0 100%, 100% 100%);
}

.toolbar-icon--desc::after {
  width: 10px;
  height: 6px;
  top: 11px;
  left: 4px;
  clip-path: polygon(0 0, 100% 0, 50% 100%);
}

.toolbar-icon--name::before {
  width: 10px;
  height: 2px;
  top: 5px;
  left: 2px;
  box-shadow:
    0 4px 0 0 currentColor,
    0 8px 0 0 currentColor;
}

.toolbar-icon--name::after {
  left: 9px;
}

.toolbar-icon--version::before {
  width: 2px;
  height: 12px;
  top: 3px;
  left: 5px;
  box-shadow: 6px 0 0 0 currentColor;
}

.toolbar-icon--version::after {
  left: 9px;
}

.toolbar-icon--created::before {
  width: 12px;
  height: 12px;
  inset: 3px;
  border: 2px solid currentColor;
  background: transparent;
}

.toolbar-icon--created {
  box-shadow: inset 0 0 0 0 currentColor;
}

.toolbar-icon--created::after {
  width: 2px;
  height: 5px;
  top: 6px;
  left: 8px;
  transform-origin: bottom center;
  box-shadow: 3px -1px 0 0 currentColor;
}

.toolbar-icon--completed::before {
  width: 12px;
  height: 12px;
  inset: 3px;
  border: 2px solid currentColor;
  background: transparent;
  border-radius: 999px;
}

.operation-input,
.operation-text {
  padding: 10px 12px;
}

.operation-text {
  min-height: 44px;
  display: flex;
  align-items: center;
  background: var(--color-surface-alt);
}

.table-wrap,
.operation-table-wrap {
  overflow-x: auto;
}

.products-table,
.operation-table {
  width: 100%;
  border-collapse: collapse;
}

.products-table th,
.products-table td,
.operation-table th,
.operation-table td {
  padding: 16px 14px;
  text-align: left;
  border-bottom: 1px solid var(--color-border);
  vertical-align: top;
}

.products-table th,
.operation-table th {
  font-size: 0.82rem;
  letter-spacing: 0.05em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.products-table tbody tr:last-child td,
.operation-table tbody tr:last-child td {
  border-bottom: 0;
}

.products-table tbody tr td,
.operation-table tbody tr td {
  transition: background-color 0.18s ease;
}

.products-table tbody tr:hover td,
.products-table tbody tr:focus-within td,
.operation-table tbody tr:hover td,
.operation-table tbody tr:focus-within td {
  background: var(--color-surface-soft);
}

.table-row--locked {
  opacity: 0.42;
}

.table-row--locked td {
  pointer-events: none;
}

.table-row--editing td {
  background: var(--color-surface-soft);
}

.status-button {
  min-width: 148px;
  padding: 10px 14px;
  border-radius: 999px;
  font-weight: 700;
}

.status-button--active {
  background: rgba(94, 143, 116, 0.16);
  color: var(--color-text);
}

.status-button--inactive {
  background: rgba(138, 150, 163, 0.14);
  color: var(--color-text-secondary);
}

.user-status {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: fit-content;
  min-width: 118px;
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 0.86rem;
  font-weight: 700;
  text-align: center;
}

.user-status--active {
  background: rgba(94, 143, 116, 0.16);
  color: var(--color-text);
}

.user-status--inactive {
  background: rgba(138, 150, 163, 0.14);
  color: var(--color-text-secondary);
}

.empty-table-state {
  margin-top: 16px;
  padding: 14px 16px;
  border-radius: 16px;
  background: var(--color-surface);
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border);
}

.banner {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
  padding: 14px 16px;
  border-radius: 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
}

.banner p {
  margin: 0;
}

.banner--error {
  background: rgba(197, 107, 107, 0.12);
  color: var(--color-text);
}

.modal-backdrop {
  position: fixed;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(31, 42, 51, 0.24);
  backdrop-filter: blur(8px);
}

.modal {
  width: min(1120px, calc(100vw - 48px));
  max-height: calc(100vh - 48px);
  padding: 24px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.confirm-modal {
  width: min(520px, calc(100vw - 48px));
  padding: 24px;
  border: 1px solid var(--color-border);
  border-radius: 24px;
  background: var(--color-surface);
  box-shadow: 0 18px 36px rgba(31, 42, 51, 0.1);
}

.confirm-modal__content {
  display: grid;
  gap: 12px;
}

.confirm-modal__eyebrow {
  margin: 0;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.modal__eyebrow {
  margin: 0 0 6px;
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.confirm-modal__description {
  margin: 0;
  color: var(--color-text-secondary);
  line-height: 1.55;
}

.confirm-modal__details {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 14px 16px;
  border-radius: 16px;
  background: var(--color-surface-alt);
}

.confirm-modal__details div {
  display: grid;
  gap: 4px;
}

.confirm-modal__details dt {
  font-size: 0.78rem;
  font-weight: 700;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--color-text-muted);
}

.confirm-modal__details dd {
  margin: 0;
  color: var(--color-text);
  font-weight: 600;
}

.confirm-modal__actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
  margin-top: 22px;
  padding-top: 16px;
  border-top: 1px solid var(--color-border);
}

.confirm-modal__delete {
  min-width: 132px;
}

.worker-qr-scanner-modal {
  width: min(560px, calc(100vw - 48px));
}

.worker-qr-scanner-preview {
  position: relative;
  aspect-ratio: 4 / 3;
  overflow: hidden;
  border-radius: 18px;
  background: #111;
}

.worker-qr-scanner-preview video {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: cover;
}

.worker-qr-scanner-frame {
  position: absolute;
  inset: 13%;
  border: 3px solid rgba(255, 255, 255, 0.9);
  border-radius: 18px;
  box-shadow: 0 0 0 999px rgba(17, 17, 17, 0.24);
  pointer-events: none;
}

.worker-qr-scanner-loading {
  position: absolute;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(17, 17, 17, 0.7);
  color: #fff;
  font-weight: 700;
  text-align: center;
}

.product-form {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  gap: 18px;
  min-height: 0;
  flex: 1 1 auto;
  overflow: hidden;
}

.product-form__header {
  display: grid;
  gap: 12px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--color-border);
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  align-items: start;
}

.field-error {
  margin: 0;
  color: var(--color-danger);
  font-size: 0.9rem;
}

.field-error-link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--color-primary);
  font: inherit;
  appearance: none;
  text-decoration: underline;
  text-decoration-thickness: 1px;
  text-underline-offset: 2px;
  cursor: pointer;
}

.field-error-link:hover {
  color: var(--color-primary-hover);
}

.field-error--section {
  margin-top: -6px;
}

.field-error--inline {
  margin-top: -6px;
}

.table-actions {
  display: grid;
  gap: 8px;
  align-items: start;
  justify-items: start;
}

.table-actions .action-link {
  white-space: nowrap;
}

.subtabs {
  display: inline-flex;
  gap: 8px;
  padding: 6px;
  border-radius: 16px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
}

.subtab-button {
  padding: 10px 16px;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: var(--color-text-secondary);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  transition:
    transform 0.18s ease,
    background-color 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease;
}

.subtab-button:hover {
  transform: translateY(-1px);
}

.subtab-button--active {
  background: var(--color-primary);
  color: #fff;
  box-shadow: 0 10px 22px rgba(47, 110, 163, 0.12);
}

.brigadier-table .primary-button {
  padding: 10px 14px;
  box-shadow: 0 10px 18px rgba(47, 110, 163, 0.12);
}

.duration-badge {
  display: inline-flex;
  align-items: center;
  padding: 10px 12px;
  border: 0;
  border-radius: 999px;
  background: var(--color-surface-soft);
  color: var(--color-primary-hover);
  font-weight: 700;
  white-space: nowrap;
  font-family: "Sora", "Inter", sans-serif;
}

.duration-badge--button {
  cursor: pointer;
  transition:
    background 0.18s ease,
    color 0.18s ease,
    transform 0.18s ease;
}

.duration-badge--button:hover {
  background: var(--color-primary);
  color: #fff;
  transform: translateY(-1px);
}

.duration-badge--button:focus-visible {
  outline: 3px solid rgba(47, 110, 163, 0.22);
  outline-offset: 3px;
}

.work-order-deadline--overdue {
  color: var(--color-danger);
  font-weight: 800;
}

.pagination-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  margin-top: 16px;
  color: var(--color-text-secondary);
  font-weight: 700;
}

.pagination-bar__actions {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.pagination-bar .secondary-button:disabled {
  cursor: not-allowed;
  opacity: 0.5;
}

.desktop-only {
  display: block;
}

.mobile-only {
  display: none;
}

.mobile-list {
  display: grid;
  gap: 14px;
}

.mobile-list.mobile-only {
  display: none;
}

.mobile-card {
  display: grid;
  gap: 12px;
  padding: 16px;
  border: 1px solid var(--color-border);
  border-radius: 18px;
  background: var(--color-surface);
  box-shadow: 0 12px 26px rgba(31, 42, 51, 0.05);
}

.mobile-card__head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.mobile-card__head strong {
  font-size: 1rem;
  line-height: 1.2;
  color: var(--color-text);
}

.mobile-card__head--stacked {
  display: grid;
  gap: 6px;
}

.mobile-card__meta {
  display: grid;
  gap: 4px;
  color: var(--color-text-secondary);
  font-size: 0.92rem;
}

.mobile-card > .action-link {
  justify-self: start;
}

.mobile-card__version {
  color: var(--color-primary-hover);
  font-weight: 700;
  font-size: 0.92rem;
}

.print-sheet {
  display: none;
}

.print-order-table {
  width: 100%;
  border-collapse: collapse;
}

.print-order-table th,
.print-order-table td {
  padding: 10px 12px;
  border: 1px solid #1f2a33;
  color: #111;
  text-align: left;
  vertical-align: top;
}

.print-order-table th {
  width: 32%;
  font-weight: 700;
  background: #f1f3f5;
}

.print-order-table__section {
  background: #e4e8ec !important;
  text-align: left;
}

.print-order-table__head th {
  background: #f1f3f5;
}

.print-order-qr-list {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 3mm;
  margin-top: 8mm;
  break-inside: avoid;
  page-break-inside: avoid;
}

.print-order-qr {
  display: grid;
  justify-items: center;
  gap: 1mm;
  margin: 0;
  color: #111;
  text-align: center;
}

.print-order-qr img {
  display: block;
  width: 30mm;
  height: 30mm;
}

.print-order-qr figcaption {
  width: 30mm;
  display: grid;
  gap: 0.5mm;
  font-size: 20px;
  line-height: 1.2;
  overflow-wrap: anywhere;
}

.print-order-qr figcaption strong {
  font-size: 23px;
}

.brigadier-modal {
  width: min(980px, calc(100vw - 48px));
}

.time-breakdown-modal {
  width: min(1040px, calc(100vw - 48px));
}

.time-breakdown-table-wrap {
  margin-top: 0;
}

.time-breakdown-table th:nth-child(n + 3),
.time-breakdown-table td:nth-child(n + 3) {
  text-align: right;
  white-space: nowrap;
}

.time-breakdown-table .time-breakdown-table__empty {
  padding: 24px;
  color: var(--color-text-secondary);
  text-align: center;
}

.time-breakdown-total-row th,
.time-breakdown-total-row td {
  background: var(--color-surface-soft);
  color: var(--color-text);
  font-family: "Sora", "Inter", sans-serif;
  vertical-align: top;
}

.time-breakdown-total-row th {
  text-align: left;
}

.time-breakdown-total-row__label {
  display: block;
  color: var(--color-text-secondary);
  font-weight: 700;
  margin-bottom: 4px;
}

.time-breakdown-total-row strong {
  font-size: 1.15rem;
}

.order-form {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr) auto;
  gap: 18px;
  min-height: 0;
  flex: 1 1 auto;
  overflow: hidden;
}

.order-form__header {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 220px;
  gap: 18px;
  padding-bottom: 14px;
  border-bottom: 1px solid var(--color-border);
}

.order-form__summary {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
}

.order-form__meta {
  display: grid;
  gap: 12px;
}

.summary-card {
  display: grid;
  gap: 6px;
  padding: 14px 16px;
  border-radius: 16px;
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
}

.summary-card strong {
  color: var(--color-text);
}

.summary-card__field {
  margin-top: 8px;
}

.order-form__quantity {
  align-self: start;
}

.order-assignments {
  display: grid;
  gap: 14px;
  min-height: 0;
  overflow: auto;
  padding-right: 6px;
}

.assignment-list {
  display: grid;
  gap: 12px;
  min-width: 0;
}

.assignment-row {
  display: grid;
  grid-template-columns: minmax(220px, 0.9fr) minmax(260px, 1fr);
  gap: 16px;
  align-items: start;
  padding: 16px;
  border-radius: 18px;
  background: var(--color-surface-alt);
  border: 1px solid var(--color-border);
}

.assignment-row__label {
  min-width: 0;
  font-weight: 600;
  color: var(--color-text);
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.assignment-row__control {
  display: grid;
  gap: 8px;
  min-width: 0;
}

.assignment-input-wrap {
  position: relative;
  min-width: 0;
  width: 100%;
}

.assignment-dropdown {
  position: absolute;
  top: calc(100% + 8px);
  left: 0;
  right: 0;
  z-index: 20;
  display: grid;
  gap: 4px;
  max-height: min(280px, 40dvh);
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  padding: 8px;
  overflow-y: auto;
  border: 1px solid var(--color-border);
  border-radius: 16px;
  background: var(--color-surface);
  box-shadow: 0 18px 36px rgba(31, 42, 51, 0.14);
  -webkit-overflow-scrolling: touch;
}

.assignment-dropdown__option {
  padding: 12px 14px;
  border: 0;
  border-radius: 12px;
  background: transparent;
  color: var(--color-text);
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition:
    background-color 0.18s ease,
    color 0.18s ease;
}

.assignment-dropdown__option:hover,
.assignment-dropdown__option--selected {
  background: var(--color-primary-soft);
  color: var(--color-primary-hover);
}

.assignment-dropdown__empty {
  padding: 12px 14px;
  color: var(--color-text-secondary);
}

.table-link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--color-text);
  font: inherit;
  font-weight: 600;
  text-align: left;
  cursor: pointer;
}

.table-link:hover {
  color: var(--color-primary-hover);
}

.user-cell {
  display: grid;
  gap: 8px;
}

.users-table__input {
  min-width: 220px;
}

.hash-value {
  display: inline-block;
  max-width: 220px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 6px 10px;
  border-radius: 10px;
  background: var(--color-surface-alt);
  color: var(--color-text-secondary);
  font-size: 0.78rem;
}

.role-group {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.role-button {
  width: 40px;
  height: 40px;
  display: grid;
  place-items: center;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-surface);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition:
    transform 0.18s ease,
    background-color 0.18s ease,
    color 0.18s ease,
    box-shadow 0.18s ease,
    opacity 0.18s ease;
}

.role-button:hover {
  transform: translateY(-1px);
}

.role-button:disabled {
  cursor: default;
  opacity: 0.7;
}

.role-button--active {
  background: var(--color-primary);
  color: #fff;
  box-shadow: 0 10px 22px rgba(47, 110, 163, 0.12);
}

.role-icon {
  position: relative;
  width: 18px;
  height: 18px;
  display: inline-block;
}

.role-icon::before,
.role-icon::after {
  content: "";
  position: absolute;
  background: currentColor;
}

.role-icon--worker::before {
  top: 1px;
  left: 5px;
  width: 8px;
  height: 8px;
  border-radius: 999px;
}

.role-icon--worker::after {
  top: 10px;
  left: 3px;
  width: 12px;
  height: 6px;
  border-radius: 999px 999px 4px 4px;
}

.role-icon--brigadier::before {
  top: 1px;
  left: 2px;
  width: 6px;
  height: 6px;
  border-radius: 999px;
  box-shadow: 8px 0 0 0 currentColor;
}

.role-icon--brigadier::after {
  top: 9px;
  left: 1px;
  width: 16px;
  height: 6px;
  border-radius: 999px;
}

.role-icon--constructor::before {
  top: 3px;
  left: 3px;
  width: 12px;
  height: 12px;
  border: 2px solid currentColor;
  background: transparent;
  transform: rotate(45deg);
}

.role-icon--constructor::after {
  top: 8px;
  left: 1px;
  width: 16px;
  height: 2px;
  border-radius: 999px;
}

.role-icon--admin::before {
  top: 1px;
  left: 4px;
  width: 10px;
  height: 14px;
  background: transparent;
  border: 2px solid currentColor;
  border-radius: 10px 10px 6px 6px;
}

.role-icon--admin::after {
  top: 5px;
  left: 7px;
  width: 4px;
  height: 6px;
  border-radius: 999px;
}

.role-icon--quality-control::before {
  top: 2px;
  left: 2px;
  width: 10px;
  height: 10px;
  background: transparent;
  border: 2px solid currentColor;
  border-radius: 999px;
}

.role-icon--quality-control::after {
  top: 12px;
  left: 11px;
  width: 6px;
  height: 2px;
  transform: rotate(45deg);
  transform-origin: left center;
}

.role-icon--stats::before {
  bottom: 2px;
  left: 2px;
  width: 3px;
  height: 8px;
  border-radius: 2px;
  box-shadow: 5px -3px 0 0 currentColor, 10px -6px 0 0 currentColor;
}

.role-icon--stats::after {
  left: 1px;
  right: 1px;
  bottom: 1px;
  height: 2px;
}

.role-icon--users::before {
  top: 2px;
  left: 3px;
  width: 5px;
  height: 5px;
  border-radius: 999px;
  box-shadow: 7px 0 0 0 currentColor;
}

.role-icon--users::after {
  top: 9px;
  left: 1px;
  width: 16px;
  height: 6px;
  border-radius: 999px;
}

.button-icon {
  position: relative;
  width: 16px;
  height: 16px;
  display: inline-block;
  flex: 0 0 auto;
}

.button-icon::before,
.button-icon::after {
  content: "";
  position: absolute;
  background: currentColor;
  border-radius: 999px;
}

.button-icon--play::before {
  top: 2px;
  left: 4px;
  width: 10px;
  height: 12px;
  border-radius: 0;
  clip-path: polygon(0 0, 100% 50%, 0 100%);
}

.button-icon--stop::before {
  inset: 3px;
  border-radius: 3px;
}

.button-icon--pause::before,
.button-icon--pause::after {
  top: 2px;
  width: 4px;
  height: 12px;
}

.button-icon--pause::before {
  left: 3px;
}

.button-icon--pause::after {
  right: 3px;
}

.button-icon--check::before {
  top: 7px;
  left: 2px;
  width: 5px;
  height: 2px;
  transform: rotate(45deg);
}

.button-icon--check::after {
  top: 6px;
  left: 5px;
  width: 9px;
  height: 2px;
  transform: rotate(-45deg);
}

.button-icon--search::before {
  top: 2px;
  left: 2px;
  width: 9px;
  height: 9px;
  border: 2px solid currentColor;
  background: transparent;
  border-radius: 999px;
}

.button-icon--search::after {
  top: 11px;
  left: 10px;
  width: 6px;
  height: 2px;
  transform: rotate(45deg);
  transform-origin: left center;
}

.button-icon--print::before {
  top: 5px;
  left: 2px;
  width: 12px;
  height: 8px;
  border-radius: 2px;
}

.button-icon--print::after {
  top: 1px;
  left: 4px;
  width: 8px;
  height: 14px;
  border: 2px solid currentColor;
  border-radius: 1px;
  background: transparent;
}

.button-icon--refresh::before {
  inset: 1px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  background: transparent;
  border-radius: 999px;
}

.button-icon--refresh::after {
  top: 1px;
  right: 1px;
  width: 6px;
  height: 6px;
  border-radius: 0;
  clip-path: polygon(0 0, 100% 0, 100% 100%);
}

.button-icon--people::before {
  top: 1px;
  left: 2px;
  width: 5px;
  height: 5px;
  border-radius: 999px;
  box-shadow: 7px 0 0 0 currentColor;
}

.button-icon--people::after {
  top: 8px;
  left: 1px;
  width: 14px;
  height: 6px;
}

.button-icon--plus::before,
.button-icon--plus::after {
  top: 7px;
  left: 2px;
  width: 12px;
  height: 2px;
}

.button-icon--plus::after {
  top: 2px;
  left: 7px;
  width: 2px;
  height: 12px;
}

.button-icon--view::before {
  top: 4px;
  left: 1px;
  width: 14px;
  height: 8px;
  border: 2px solid currentColor;
  background: transparent;
  border-radius: 999px;
}

.button-icon--view::after {
  top: 6px;
  left: 6px;
  width: 4px;
  height: 4px;
}

.button-icon--copy::before,
.button-icon--copy::after {
  border: 2px solid currentColor;
  background: transparent;
  border-radius: 3px;
}

.button-icon--copy::before {
  top: 3px;
  left: 5px;
  width: 8px;
  height: 9px;
}

.button-icon--copy::after {
  top: 1px;
  left: 2px;
  width: 8px;
  height: 9px;
}

.button-icon--delete::before {
  top: 4px;
  left: 3px;
  width: 10px;
  height: 9px;
  border: 2px solid currentColor;
  border-top: 0;
  background: transparent;
  border-radius: 0 0 3px 3px;
}

.button-icon--delete::after {
  top: 2px;
  left: 2px;
  width: 12px;
  height: 2px;
  box-shadow: 4px -2px 0 0 currentColor;
}

.button-icon--save::before {
  top: 1px;
  left: 2px;
  width: 12px;
  height: 14px;
  border: 2px solid currentColor;
  background: transparent;
  border-radius: 3px;
}

.button-icon--save::after {
  top: 3px;
  left: 5px;
  width: 6px;
  height: 3px;
  box-shadow: 0 6px 0 0 currentColor;
}

.button-icon--key::before {
  top: 2px;
  left: 2px;
  width: 7px;
  height: 7px;
  border: 2px solid currentColor;
  background: transparent;
  border-radius: 999px;
}

.button-icon--key::after {
  top: 8px;
  left: 8px;
  width: 7px;
  height: 2px;
  box-shadow: 4px 0 0 0 currentColor, 4px 3px 0 0 currentColor;
}

.button-icon--logout::before {
  top: 2px;
  left: 2px;
  width: 8px;
  height: 12px;
  border: 2px solid currentColor;
  border-right: 0;
  background: transparent;
  border-radius: 3px 0 0 3px;
}

.button-icon--logout::after {
  top: 7px;
  right: 1px;
  width: 9px;
  height: 2px;
  box-shadow: -1px -3px 0 -1px currentColor, -1px 3px 0 -1px currentColor;
}

.button-icon--reset-password::before {
  inset: 1px;
  border: 2px solid currentColor;
  border-right-color: transparent;
  background: transparent;
  border-radius: 999px;
}

.button-icon--reset-password::after {
  top: 1px;
  right: 1px;
  width: 6px;
  height: 6px;
  border-radius: 0;
  clip-path: polygon(0 0, 100% 0, 100% 100%);
}

.button-icon--close::before,
.button-icon--close::after {
  top: 7px;
  left: 1px;
  width: 14px;
  height: 2px;
}

.button-icon--close::before {
  transform: rotate(45deg);
}

.button-icon--close::after {
  transform: rotate(-45deg);
}

.button-icon--edit::before {
  top: 2px;
  left: 3px;
  width: 10px;
  height: 3px;
  border-radius: 2px;
  transform: rotate(-45deg);
}

.button-icon--edit::after {
  top: 10px;
  left: 2px;
  width: 4px;
  height: 4px;
  border-radius: 0;
  clip-path: polygon(0 100%, 100% 100%, 100% 0);
}

.button-icon--package::before {
  top: 3px;
  left: 2px;
  width: 12px;
  height: 10px;
  border: 2px solid currentColor;
  background: transparent;
  border-radius: 3px;
}

.button-icon--package::after {
  top: 3px;
  left: 7px;
  width: 2px;
  height: 10px;
}

.button-icon--orders::before {
  top: 2px;
  left: 2px;
  width: 12px;
  height: 12px;
  border: 2px solid currentColor;
  background: transparent;
  border-radius: 3px;
}

.button-icon--orders::after {
  top: 5px;
  left: 5px;
  width: 6px;
  height: 2px;
  box-shadow: 0 4px 0 0 currentColor;
}

.button-icon--in-work::before {
  top: 1px;
  left: 3px;
  width: 10px;
  height: 10px;
  border: 2px solid currentColor;
  background: transparent;
  border-radius: 999px;
}

.button-icon--in-work::after {
  top: 7px;
  left: 8px;
  width: 5px;
  height: 2px;
  transform-origin: left center;
  transform: rotate(-45deg);
}

.button-icon--timer-preparation::before {
  top: 2px;
  left: 2px;
  width: 12px;
  height: 12px;
  border: 2px solid currentColor;
  background: transparent;
  border-radius: 999px;
}

.button-icon--timer-preparation::after {
  top: 7px;
  left: 8px;
  width: 4px;
  height: 2px;
  transform-origin: left center;
  transform: rotate(-45deg);
}

.button-icon--timer-break::before,
.button-icon--timer-break::after,
.button-icon--timer-idle::before,
.button-icon--timer-idle::after,
.button-icon--timer-operation::before,
.button-icon--timer-operation::after {
  background: currentColor;
}

.button-icon--timer-break::before,
.button-icon--timer-break::after {
  top: 2px;
  width: 4px;
  height: 12px;
}

.button-icon--timer-break::before {
  left: 3px;
}

.button-icon--timer-break::after {
  right: 3px;
}

.button-icon--timer-idle::before {
  top: 1px;
  left: 7px;
  width: 2px;
  height: 9px;
}

.button-icon--timer-idle::after {
  bottom: 1px;
  left: 7px;
  width: 2px;
  height: 2px;
}

.button-icon--timer-operation::before {
  top: 3px;
  left: 2px;
  width: 12px;
  height: 10px;
  border: 2px solid currentColor;
  background: transparent;
  border-radius: 3px;
}

.button-icon--timer-operation::after {
  top: 6px;
  left: 5px;
  width: 6px;
  height: 2px;
}

.operations-section {
  display: grid;
  gap: 14px;
  min-height: 0;
  overflow: auto;
  padding-right: 6px;
}

.empty-state--operations {
  padding: 18px;
  border: 1px dashed var(--color-border);
  border-radius: 16px;
  background: var(--color-surface);
}

.empty-state--operations p {
  margin: 0;
}

.empty-state--operations p + p {
  margin-top: 8px;
  color: var(--color-text-secondary);
}

.operation-cell {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  padding-left: calc(var(--level) * 18px);
}

.operation-branch {
  width: 12px;
  height: 1px;
  margin-top: 22px;
  background: var(--color-muted);
  flex: 0 0 auto;
}

.operation-editor {
  width: 100%;
  display: grid;
  gap: 8px;
}

.operation-badge {
  display: inline-flex;
  align-items: center;
  padding: 8px 12px;
  border-radius: 999px;
  font-size: 0.84rem;
  font-weight: 700;
}

.operation-badge--group {
  background: var(--color-surface-alt);
  color: var(--color-text-secondary);
}

.operation-badge--leaf {
  background: var(--color-surface-soft);
  color: var(--color-primary-hover);
}

.operation-actions {
  display: flex;
  gap: 10px;
  align-items: center;
  flex-wrap: wrap;
}

.readonly-note {
  color: var(--color-text-muted);
}

.operations-footer {
  display: flex;
  justify-content: flex-start;
  padding-top: 6px;
}

.icon-action-button {
  position: relative;
  width: 40px;
  height: 40px;
  border: 1px solid var(--color-border);
  border-radius: 12px;
  background: var(--color-surface);
  cursor: pointer;
  transition:
    transform 0.18s ease,
    background-color 0.18s ease,
    box-shadow 0.18s ease;
}

.icon-action-button:disabled {
  cursor: not-allowed;
  opacity: 0.38;
  transform: none;
  box-shadow: none;
}

.icon-action-button:hover {
  transform: translateY(-1px);
  background: var(--color-surface-alt);
  box-shadow: 0 10px 18px rgba(31, 42, 51, 0.08);
}

.icon-action-button:focus-visible {
  outline: 2px solid rgba(47, 110, 163, 0.28);
  outline-offset: 2px;
}

.action-icon {
  position: absolute;
  inset: 0;
}

.action-icon::before,
.action-icon::after {
  content: "";
  position: absolute;
  background: var(--color-text-secondary);
  border-radius: 999px;
}

.action-icon--up::before {
  top: 10px;
  left: 19px;
  width: 2px;
  height: 16px;
}

.action-icon--up::after {
  top: 8px;
  left: 14px;
  width: 12px;
  height: 8px;
  background: var(--color-text-secondary);
  clip-path: polygon(50% 0, 0 100%, 100% 100%);
}

.action-icon--down::before {
  top: 12px;
  left: 19px;
  width: 2px;
  height: 16px;
}

.action-icon--down::after {
  top: 24px;
  left: 14px;
  width: 12px;
  height: 8px;
  background: var(--color-text-secondary);
  clip-path: polygon(0 0, 100% 0, 50% 100%);
}

.action-icon--indent::before {
  top: 11px;
  left: 11px;
  width: 2px;
  height: 14px;
  box-shadow: 8px 0 0 0 rgba(138, 150, 163, 0.28);
}

.action-icon--indent::after {
  top: 23px;
  left: 11px;
  width: 15px;
  height: 2px;
  box-shadow:
    8px -5px 0 -4px var(--color-text-secondary),
    8px 5px 0 -4px var(--color-text-secondary);
}

.action-icon--outdent::before {
  top: 11px;
  left: 27px;
  width: 2px;
  height: 14px;
  box-shadow: -8px 0 0 0 rgba(138, 150, 163, 0.28);
}

.action-icon--outdent::after {
  top: 23px;
  left: 14px;
  width: 15px;
  height: 2px;
  box-shadow:
    -8px -5px 0 -4px var(--color-text-secondary),
    -8px 5px 0 -4px var(--color-text-secondary);
}

.action-icon--child::before {
  top: 9px;
  left: 11px;
  width: 2px;
  height: 12px;
}

.action-icon--child::after {
  top: 19px;
  left: 11px;
  width: 11px;
  height: 2px;
  box-shadow:
    11px 0 0 0 var(--color-text-secondary),
    16px -5px 0 -4px var(--color-text-secondary),
    16px 5px 0 -4px var(--color-text-secondary);
}

.action-icon--sibling::before {
  top: 19px;
  left: 10px;
  width: 14px;
  height: 2px;
}

.action-icon--sibling::after {
  top: 13px;
  left: 16px;
  width: 2px;
  height: 14px;
  box-shadow: 10px 0 0 0 rgba(138, 150, 163, 0.24);
}

.modal__actions {
  display: flex;
  gap: 12px;
  align-items: center;
  justify-content: flex-end;
  padding-top: 14px;
  border-top: 1px solid var(--color-border);
}

.field-error--actions {
  margin-right: auto;
  flex: 1 1 auto;
  display: flex;
  justify-content: center;
  text-align: center;
}

@media (min-width: 761px) and (max-width: 1220px) {
  .work-orders-table-wrap.desktop-only {
    display: none;
  }

  .work-orders-mobile-list.mobile-only {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
  }
}

@media (min-width: 761px) and (max-width: 995px) {
  .subtabs--work-orders {
    width: 100%;
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .subtabs--work-orders .subtab-button {
    justify-content: center;
    min-width: 0;
    padding: 12px 10px;
  }

  .subtabs--work-orders .button-content {
    justify-content: center;
    text-align: center;
  }
}

@media (max-width: 1180px) {
  .statistics-panel__head,
  .statistics-toolbar {
    grid-template-columns: 1fr;
  }

  .statistics-toolbar__actions {
    justify-content: flex-start;
  }
}

@media (max-width: 980px) {
  .toolbar,
  .dictionary-form,
  .form-grid,
  .order-form__header,
  .assignment-row,
  .worker-summary,
  .worker-timer-bar,
  .statistics-kpis,
  .statistics-grid {
    grid-template-columns: 1fr;
  }

  .statistics-card--wide {
    grid-column: span 1;
  }

  .modal-backdrop {
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: 16px;
  }

  .modal {
    max-height: calc(100dvh - 32px);
    min-height: 0;
    overflow-y: auto;
    overflow-x: hidden;
    -webkit-overflow-scrolling: touch;
    overscroll-behavior: contain;
  }

  .confirm-modal {
    max-height: calc(100dvh - 32px);
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
  }

  .product-form,
  .order-form {
    grid-template-rows: auto auto auto;
    overflow: visible;
  }

  .order-assignments,
  .operations-section {
    min-height: auto;
    overflow: visible;
    padding-right: 0;
  }

  .assignment-row {
    grid-template-columns: minmax(0, 1fr);
    min-width: 0;
    overflow: visible;
  }

  .assignment-row__control,
  .assignment-input-wrap {
    min-width: 0;
    width: 100%;
  }

  .assignment-dropdown {
    left: 0;
    right: auto;
    width: 100%;
    max-width: calc(100vw - 60px);
  }

  .statistics-period-control {
    display: grid;
    grid-template-columns: 1fr;
  }

  .statistics-presets {
    width: 100%;
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }

  .statistics-date-range {
    width: 100%;
    grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr) auto;
  }

  .statistics-date-field__input {
    width: 100%;
  }
}

@media (max-width: 1999px) {
  .header {
    justify-content: flex-start;
  }

  .brand-block {
    order: -1;
    flex: 0 0 100%;
    align-self: flex-start;
  }

  .tabs {
    order: 0;
  }

  .current-user-card {
    order: 1;
  }
}

@media print {
  @page {
    size: A4;
    margin: 14mm;
  }

  :global(body) {
    background: #fff !important;
  }

  .page--printing {
    min-height: auto;
    padding: 0;
    background: #fff !important;
    color: #111;
  }

  .page--printing > :not(.print-sheet) {
    display: none !important;
  }

  .print-sheet {
    display: block !important;
    padding: 0;
    background: #fff;
    color: #111;
    font-family: "Times New Roman", serif;
  }

  .print-sheet h1 {
    margin: 0 0 18px;
    color: #111;
    font-size: 22px;
  }

  .print-order-table {
    font-size: 13px;
  }

  .print-order-table th,
  .print-order-table td {
    page-break-inside: avoid;
  }
}

@media (max-width: 760px) {
  .page {
    padding: 10px;
  }

  .shell {
    min-height: auto;
    padding: 14px;
    border-radius: 18px;
  }

  .header,
  .panel-head,
  .modal__head,
  .modal__actions,
  .banner,
  .statistics-toolbar {
    flex-direction: column;
    align-items: stretch;
  }

  .header {
    gap: 12px;
    margin-bottom: 16px;
  }

  .statistics-date-range {
    grid-template-columns: 1fr;
    align-items: stretch;
  }

  .statistics-date-range__divider {
    display: none;
  }

  .statistics-date-field {
    padding-left: 0;
  }

  .statistics-date-range__apply {
    width: 100%;
  }

  .statistics-toolbar__actions {
    display: grid;
    grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  }

  .statistics-toolbar__actions .primary-button {
    width: 100%;
  }

  .brand-block {
    display: flex;
    justify-content: center;
  }

  .header .brand-logo-frame {
    width: min(320px, 86vw);
    height: 88px;
  }

  .header .brand-logo {
    width: 260%;
    height: 180px;
    object-fit: cover;
    object-position: center;
    transform: none;
  }

  .tabs {
    width: 100%;
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(132px, 1fr));
    gap: 8px;
    padding: 6px;
  }

  .tab-button {
    width: 100%;
    min-height: 56px;
  }

  .brand-logo-frame--auth {
    height: 96px;
  }

  .primary-button {
    width: 100%;
  }

  .worker-panel__actions {
    display: grid;
    width: 100%;
  }

  .current-user-card {
    min-width: 0;
    grid-template-columns: minmax(0, 1fr) auto;
    align-items: center;
    gap: 10px;
    padding: 12px 14px;
  }

  .current-user-card__identity {
    min-width: 0;
    gap: 4px;
  }

  .current-user-card .section-label {
    display: none;
  }

  .current-user-card strong {
    display: block;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .current-user-card__actions {
    gap: 6px;
    flex-wrap: nowrap;
  }

  .current-user-card .ghost-button {
    min-width: 40px;
    padding: 8px;
  }

  .current-user-card__action-label {
    display: none;
  }

  .panel-head h2,
  .constructor-panel h2 {
    font-size: 1.15rem;
    line-height: 1.2;
  }

  .worker-panel__subtitle {
    display: none;
  }

  .worker-summary__card {
    padding: 18px;
  }

  .worker-summary__value {
    font-size: 2.4rem;
  }

  .worker-summary {
    grid-template-columns: 1fr;
  }

  .worker-timer-button--operation {
    grid-template-columns: 1fr;
    align-items: start;
  }

  .worker-timer-button--operation .worker-timer-button__meta,
  .worker-timer-button--operation .worker-timer-button__heading {
    min-width: 0;
  }

  .worker-timer-button--operation .worker-timer-button__value {
    justify-self: start;
  }

  .worker-filter-toolbar {
    grid-template-columns: 1fr;
  }

  .worker-filter-select {
    width: 100%;
  }

  .worker-operation-row {
    grid-template-columns: 1fr;
    gap: 8px;
  }

  .worker-operation-row__actions {
    justify-content: flex-start;
  }

  .subtabs {
    width: 100%;
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    padding: 6px;
  }

  .subtab-button {
    justify-content: center;
    min-height: 70px;
    padding: 12px 10px;
  }

  .subtab-button .button-content {
    justify-content: center;
    text-align: center;
  }

  .toolbar {
    gap: 12px;
  }

  .pagination-bar,
  .pagination-bar__actions {
    align-items: stretch;
    flex-direction: column;
  }

  .field__label {
    font-size: 0.82rem;
  }

  .desktop-only {
    display: none !important;
  }

  .mobile-only {
    display: grid;
  }

  .mobile-list.mobile-only {
    display: grid;
  }

  .modal-backdrop {
    display: flex;
    align-items: flex-start;
    justify-content: center;
    padding: 12px;
  }

  .modal {
    width: calc(100vw - 24px);
    max-height: calc(100dvh - 24px);
    min-height: 0;
    padding: 18px;
    margin: 0 auto 24px;
    overflow-y: auto;
    overflow-x: hidden;
    -webkit-overflow-scrolling: touch;
    overscroll-behavior: contain;
  }

  .confirm-modal {
    width: calc(100vw - 24px);
    max-height: calc(100dvh - 24px);
    padding: 18px;
    margin: 0 auto 24px;
    overflow-y: auto;
    -webkit-overflow-scrolling: touch;
  }

  .confirm-modal__actions {
    flex-direction: column-reverse;
    align-items: stretch;
  }

  .product-form,
  .order-form {
    grid-template-rows: auto auto auto;
    overflow: visible;
  }

  .order-assignments,
  .operations-section {
    min-height: auto;
    overflow: visible;
    padding-right: 0;
  }

  .products-table th,
  .products-table td,
  .users-table th,
  .users-table td,
  .operation-table th,
  .operation-table td {
    min-width: 150px;
  }
}
</style>
