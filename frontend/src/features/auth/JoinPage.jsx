import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import AuthLayout from "./AuthLayout.jsx";
import Icon from "../../shared/Icon.jsx";
import EmptyState from "../../shared/EmptyState.jsx";
import { api } from "../../lib/api.js";
import { useAuth } from "../../shared/AuthContext.jsx";

// Step 3: redeem an invite. The token arrives in the path (/join/:token) or as
// ?token=, so a producer can paste one link. Signed-in visitors just confirm;
// everyone else creates their own account here — no shared credentials.
export default function JoinPage() {
  const { token: pathToken } = useParams();
  const [params] = useSearchParams();
  const token = pathToken || params.get("token") || "";
  const { user, join, ready, refresh, selectProduction } = useAuth();
  const navigate = useNavigate();

  const [preview, setPreview] = useState(null);
  const [loadError, setLoadError] = useState("");
  const [form, setForm] = useState({ name: "", email: "", password: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!token) {
      setLoadError("This link is missing its invite code.");
      return;
    }
    let cancelled = false;
    api
      .previewInvite(token)
      .then((p) => !cancelled && setPreview(p))
      .catch((e) => !cancelled && setLoadError(String(e.message || e)));
    return () => {
      cancelled = true;
    };
  }, [token, ready, user]);

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const payload = user ? { token } : { token, ...form };
      await join(payload);
      if (preview?.project_id) selectProduction(preview.project_id);
      await refresh().catch(() => {});
      navigate("/", { replace: true });
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  }

  if (loadError) {
    return (
      <AuthLayout title="Invite unavailable" footer={<Link to="/login" className="auth-link">Go to sign in</Link>}>
        <EmptyState icon="link_off" title="This invite can't be opened">
          {loadError}
        </EmptyState>
      </AuthLayout>
    );
  }

  if (!preview) {
    return (
      <AuthLayout title="Checking invite…">
        <EmptyState icon="progress_activity" title="One moment" />
      </AuthLayout>
    );
  }

  if (!preview.active) {
    return (
      <AuthLayout title="Invite no longer valid" footer={<Link to="/login" className="auth-link">Go to sign in</Link>}>
        <EmptyState icon="link_off" title={`Invite to ${preview.production_name}`}>
          This invite has expired, been revoked, or already been used. Ask the producer for a new link.
        </EmptyState>
      </AuthLayout>
    );
  }

  if (preview.already_member) {
    return (
      <AuthLayout title={preview.production_name}>
        <EmptyState icon="task_alt" title="You're already on this production">
          Signed in as {preview.signed_in_as}.
        </EmptyState>
        <button type="button" className="btn btn--primary btn--lg" onClick={() => navigate("/")}>
          <Icon name="dashboard" />
          Open the dashboard
        </button>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout
      title={`Join ${preview.production_name}`}
      sub={
        user
          ? `You'll join as ${preview.role}, signed in as ${preview.signed_in_as}.`
          : `You've been invited as ${preview.role}. Create your own account to accept.`
      }
      footer={
        user ? null : (
          <>
            Already have an account? <Link to="/login" className="auth-link">Sign in first</Link>, then reopen this link.
          </>
        )
      }
    >
      <form className="stack" onSubmit={submit}>
        {!user && (
          <>
            <label className="field">
              <span className="mono-label">Your name</span>
              <input className="input" required autoComplete="name" value={form.name} onChange={set("name")} />
            </label>
            <label className="field">
              <span className="mono-label">Email</span>
              <input
                className="input"
                type="email"
                required
                autoComplete="email"
                value={form.email}
                onChange={set("email")}
              />
            </label>
            <label className="field">
              <span className="mono-label">Password</span>
              <input
                className="input"
                type="password"
                required
                minLength={10}
                autoComplete="new-password"
                value={form.password}
                onChange={set("password")}
              />
              <span className="body-sm muted">
                At least 10 characters, mixing letters with numbers or symbols.
              </span>
            </label>
          </>
        )}
        {error && (
          <div className="banner" data-tone="bad" role="alert">
            <Icon name="error" />
            <span>{error}</span>
          </div>
        )}
        <button className="btn btn--primary btn--lg" type="submit" disabled={busy}>
          <Icon name={busy ? "progress_activity" : "group_add"} className={busy ? "spin" : undefined} />
          {busy ? "Joining…" : `Join as ${preview.role}`}
        </button>
      </form>
    </AuthLayout>
  );
}
