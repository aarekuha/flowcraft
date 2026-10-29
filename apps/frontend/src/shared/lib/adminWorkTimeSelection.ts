export type WorkerListChange = {
  canApply: boolean;
  selectedWorkerMissing: boolean;
};

export function resolveWorkerListChange<T extends { id: number }>(
  selectedWorkerId: number | null,
  nextWorkers: T[],
  confirmDiscardChanges: () => boolean,
): WorkerListChange {
  const selectedWorkerMissing = selectedWorkerId !== null
    && !nextWorkers.some((worker) => worker.id === selectedWorkerId);
  return {
    canApply: !selectedWorkerMissing || confirmDiscardChanges(),
    selectedWorkerMissing,
  };
}
