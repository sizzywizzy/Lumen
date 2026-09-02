import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "./AuthContext.jsx";
import EmptyState from "./EmptyState.jsx";
import { useProject } from "./ProjectContext.jsx";

// Route guard. Everything inside the dashboard requires a session; the
// backend enforces the same rule independently, so this is convenience and
// not the security boundary.
export default function RequireAuth() {
  const { user, ready } = useAuth();
  const location = useLocation();

  if (!ready) {
    return (
      <div className="auth-shell">
        <EmptyState icon="progress_activity" title="Restoring your session…" />
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" replace state={{ from: location.pathname + location.search }} />;
  }

  return <Outlet />;
}

// Blocks a screen when the signed-in member's role is read-only.
export function RequireEditor({ children, fallback = null }) {
  const { canEdit } = useAuth();
  if (!canEdit) return fallback;
  return children;
}

// Convenience for views that need the active production id.
export function useActiveProject() {
  const { projectId } = useProject();
  return projectId;
}
