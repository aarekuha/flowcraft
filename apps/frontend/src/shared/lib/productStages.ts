export type ProductStageOperation = {
  id: number;
  stageStart: number;
  stageEnd: number;
};

export type ProductStageCellBounds = {
  stage: number;
  left: number;
  right: number;
};

export function resolveProductStageFromPointer(
  cellBounds: ProductStageCellBounds[],
  pointerX: number,
  pointerOffsetX: number,
  boundary: "start" | "end",
): number {
  const orderedBounds = [...cellBounds].sort((left, right) =>
    left.stage - right.stage
  );
  if (orderedBounds.length === 0) {
    return 1;
  }

  const boundaryX = pointerX - pointerOffsetX;
  const firstBounds = orderedBounds[0];
  if (boundaryX <= firstBounds.left) {
    return firstBounds.stage;
  }
  for (const bounds of orderedBounds) {
    const belongsToStage = boundary === "end"
      ? boundaryX <= bounds.right
      : boundaryX < bounds.right;
    if (belongsToStage) {
      return bounds.stage;
    }
  }
  return orderedBounds.at(-1)?.stage ?? 1;
}

export function moveProductOperation<T extends ProductStageOperation>(
  operations: T[],
  operationId: number,
  targetStage: number,
  stageCount: number,
): T[] {
  return operations.map((operation) => {
    if (operation.id !== operationId) {
      return operation;
    }

    const width = operation.stageEnd - operation.stageStart + 1;
    const nextStart = Math.max(1, Math.min(targetStage, stageCount - width + 1));
    return {
      ...operation,
      stageStart: nextStart,
      stageEnd: nextStart + width - 1,
    };
  });
}

export function resizeProductOperation<T extends ProductStageOperation>(
  operations: T[],
  operationId: number,
  boundary: "start" | "end",
  targetStage: number,
): T[] {
  return operations.map((operation) => {
    if (operation.id !== operationId) {
      return operation;
    }

    if (boundary === "start") {
      return {
        ...operation,
        stageStart: Math.min(targetStage, operation.stageEnd),
      };
    }
    return {
      ...operation,
      stageEnd: Math.max(targetStage, operation.stageStart),
    };
  });
}

export function removeProductStage<T extends ProductStageOperation>(
  operations: T[],
  removedStage: number,
  stageCount: number,
): T[] {
  if (stageCount <= 1) {
    return operations;
  }

  return operations.map((operation) => {
    if (operation.stageEnd < removedStage) {
      return operation;
    }
    if (operation.stageStart > removedStage) {
      return {
        ...operation,
        stageStart: operation.stageStart - 1,
        stageEnd: operation.stageEnd - 1,
      };
    }
    if (
      operation.stageStart === removedStage
      && operation.stageEnd === removedStage
    ) {
      const targetStage = Math.max(1, removedStage - 1);
      return {
        ...operation,
        stageStart: targetStage,
        stageEnd: targetStage,
      };
    }

    return {
      ...operation,
      stageStart: Math.min(operation.stageStart, stageCount - 1),
      stageEnd: Math.max(operation.stageStart, operation.stageEnd - 1),
    };
  });
}
