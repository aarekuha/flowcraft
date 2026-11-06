import assert from "node:assert/strict";
import test from "node:test";

import { requiresSkillCopyConfirmation } from "../src/shared/lib/userSkills.ts";

test("requires confirmation only for a non-empty skill set", function copyConfirmation() {
  `
  Проверяем подтверждение полной замены навыков:
  - не запрашивать подтверждение для пользователя без навыков
  - запрашивать подтверждение при наличии активных или скрытых навыков
  `;

  assert.equal(requiresSkillCopyConfirmation(0), false);
  assert.equal(requiresSkillCopyConfirmation(1), true);
  assert.equal(requiresSkillCopyConfirmation(4), true);
});
