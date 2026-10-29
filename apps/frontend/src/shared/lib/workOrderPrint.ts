export function sortAssignmentsForPrint<T extends { operationKind: string }>(
  assignments: readonly T[],
): T[] {
  const cuttingAssignments: T[] = [];
  const regularAssignments: T[] = [];
  const remainingAssignments: T[] = [];

  for (const assignment of assignments) {
    if (assignment.operationKind === "cutting") {
      cuttingAssignments.push(assignment);
    } else if (assignment.operationKind === "regular") {
      regularAssignments.push(assignment);
    } else {
      remainingAssignments.push(assignment);
    }
  }

  return [
    ...cuttingAssignments,
    ...regularAssignments,
    ...remainingAssignments,
  ];
}
