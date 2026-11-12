import type { ObjectDirective } from "vue";

const dialogs = new Map<HTMLElement, () => void>();

function layer(element: HTMLElement): number {
  let level = 0;
  for (let current: HTMLElement | null = element; current; current = current.parentElement) {
    const zIndex = Number.parseInt(window.getComputedStyle(current).zIndex, 10);
    if (Number.isFinite(zIndex)) {
      level = Math.max(level, zIndex);
    }
  }
  return level;
}

function onEscape(event: KeyboardEvent) {
  if (event.key !== "Escape" || event.defaultPrevented || event.isComposing) {
    return;
  }
  const visible = [...dialogs.keys()].filter((element) =>
    element.isConnected && element.getClientRects().length > 0,
  );
  visible.sort((left, right) => {
    const difference = layer(left) - layer(right);
    if (difference) {
      return difference;
    }
    return left.compareDocumentPosition(right) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
  });
  const top = visible.at(-1);
  if (!top) {
    return;
  }
  event.preventDefault();
  event.stopImmediatePropagation();
  if (!event.repeat) {
    dialogs.get(top)?.();
  }
}

export const vEscapeClose: ObjectDirective<HTMLElement, () => void> = {
  mounted(element, binding) {
    if (dialogs.size === 0) {
      window.addEventListener("keydown", onEscape, true);
    }
    dialogs.set(element, binding.value);
  },
  updated(element, binding) {
    dialogs.set(element, binding.value);
  },
  unmounted(element) {
    dialogs.delete(element);
    if (dialogs.size === 0) {
      window.removeEventListener("keydown", onEscape, true);
    }
  },
};
