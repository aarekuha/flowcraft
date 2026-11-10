export function createWorkerTimerRequests(onBusyChange: (busy: boolean) => void) {
  const pending = new Set<symbol>();
  let revision = 0;
  let latestRead = 0;
  let activeMutation: symbol | null = null;

  function begin(mutation: boolean) {
    const id = Symbol();
    const read = mutation ? latestRead : ++latestRead;
    const duringMutation = activeMutation !== null;
    if (mutation) {
      revision += 1;
      activeMutation = id;
    }
    const startedRevision = revision;
    pending.add(id);
    onBusyChange(true);
    return {
      isCurrent: () => pending.has(id) && startedRevision === revision && (
        mutation
          ? activeMutation === id
          : !duringMutation && activeMutation === null && read === latestRead
      ),
      finish() {
        pending.delete(id);
        if (mutation && activeMutation === id) {
          activeMutation = null;
          revision += 1;
        }
        onBusyChange(pending.size > 0);
      },
    };
  }

  return {
    beginRead: () => begin(false),
    beginMutation: () => begin(true),
    reset() {
      revision += 1;
      latestRead += 1;
      pending.clear();
      activeMutation = null;
      onBusyChange(false);
    },
  };
}
