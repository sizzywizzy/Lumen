import { useState } from "react";
import { Link, Navigate, useNavigate } from "react-router-dom";
import AuthLayout from "./AuthLayout.jsx";
import Icon from "../../shared/Icon.jsx";
import { useAuth } from "../../shared/AuthContext.jsx";

// Step 1 of the team flow: the producer/director creates the production
// account and becomes its owner. Everyone else joins by invite.
export default function RegisterPage() {
  const { user, register, ready } = useAuth();
  const navigate = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "", production_name: "" });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  if (ready && user) return <Navigate to="/" replace />;

  const set = (key) => (e) => setForm((f) => ({ ...f, [key]: e.target.value }));
  const weak = form.password.length > 0 && form.password.length < 10;

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      await register(form);
      navigate("/", { replace: true });
    } catch (err) {
      setError(String(err.message || err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <AuthLayout
      title="Create a production"
      sub="You'll be the owner, and can invite your director and crew once you're in."
      footer={
        <>
          Already have an account? <Link to="/login" className="auth-link">Sign in</Link>
        </>
      }
    >
      <form className="stack" onSubmit={submit}>
        <label className="field">
          <span className="mono-label">Production name</span>
          <input
            className="input"
            required
            placeholder="Neon Nights"
            value={form.production_name}
            onChange={set("production_name")}
          />
        </label>
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
          <span className={weak ? "body-sm text-warn" : "body-sm muted"}>
            At least 10 characters, mixing letters with numbers or symbols.
          </span>
        </label>
        {error && (
          <div className="banner" data-tone="bad" role="alert">
            <Icon name="error" />
            <span>{error}</span>
          </div>
        )}
        <button className="btn btn--primary btn--lg" type="submit" disabled={busy}>
          <Icon name={busy ? "progress_activity" : "movie"} className={busy ? "spin" : undefined} />
          {busy ? "Creating…" : "Create production"}
        </button>
      </form>
    </AuthLayout>
  );
}
