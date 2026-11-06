export type AssignmentSkillWorker = {
  id: number;
  skillOperationCatalogEntryIds: number[];
};

export function canSelectWorkerForOperation(
  worker: AssignmentSkillWorker,
  operationCatalogEntryId: number | null,
  selectedWorkerId: number | null,
): boolean {
  if (worker.id === selectedWorkerId) {
    return true;
  }
  if (operationCatalogEntryId === null) {
    return false;
  }
  return worker.skillOperationCatalogEntryIds.includes(operationCatalogEntryId);
}

export function workerHasOperationSkill(
  worker: AssignmentSkillWorker,
  operationCatalogEntryId: number | null,
): boolean {
  return (
    operationCatalogEntryId !== null
    && worker.skillOperationCatalogEntryIds.includes(operationCatalogEntryId)
  );
}
