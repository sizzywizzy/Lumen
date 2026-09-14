import { useAuth } from "../../shared/AuthContext.jsx";
import { useProject } from "../../shared/ProjectContext.jsx";
import { money } from "../../lib/utils.js";
import { budgetSummary, castByRole, hasResults } from "../../lib/production.js";
import { Card, NoPlanYet, RoleBlock } from "./parts.jsx";

export default function CastPage() {
  const { state } = useProject();
  const { canEdit } = useAuth();
  if (!hasResults(state)) return <NoPlanYet canEdit={canEdit} />;

  const roles = castByRole(state);
  const budget = budgetSummary(state);

  return (
    <>
      <div className="page-top">
        <div>
          <h1>Cast</h1>
          <p>
            {roles.length} {roles.length === 1 ? "role" : "roles"} · the top picks cost {money(budget.castFees)} of your{" "}
            {money(budget.cap)} budget
          </p>
        </div>
      </div>

      <div className="dash-grid">
        {roles.map((role) => (
          <Card key={role.roleId} className="col-6">
            <RoleBlock role={role} showWhy />
          </Card>
        ))}
      </div>
    </>
  );
}
