export type AdminWorkTimeFormPolicyInput = {
  editorActive: boolean;
  editable: boolean;
  dirty: boolean;
  hasBlockingError: boolean;
  saving: boolean;
  advisoryOverlapCheckPending: boolean;
};

export type AdminWorkTimeFormPolicy = {
  canSave: boolean;
  advisoryOverlapCheckPending: boolean;
};

export function resolveAdminWorkTimeFormPolicy(
  input: AdminWorkTimeFormPolicyInput,
): AdminWorkTimeFormPolicy {
  return {
    canSave:
      input.editorActive
      && input.editable
      && input.dirty
      && !input.hasBlockingError
      && !input.saving,
    advisoryOverlapCheckPending: input.advisoryOverlapCheckPending,
  };
}
