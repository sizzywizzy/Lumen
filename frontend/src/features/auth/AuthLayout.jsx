import LumenIcon from "../../shared/CameraArt.jsx";
import { LumenWordmark } from "../../shared/LumenLogo.jsx";
import ThemeToggle from "../../shared/ThemeToggle.jsx";

// Centred shell for the signed-out screens. Uses the same design tokens as the
// dashboard, so sign-in does not look like a different product.
export default function AuthLayout({ title, sub, children, footer }) {
  return (
    <div className="auth-shell">
      <div className="auth-toggle">
        <ThemeToggle />
      </div>
      <div className="auth-card">
        <div className="auth-brand">
          <LumenIcon size={68} />
          <div>
            <LumenWordmark height={50} />
            <p className="mono-label muted">Production dashboard</p>
          </div>
        </div>
        <div>
          <h1 className="headline-md">{title}</h1>
          {sub && <p className="muted body-sm" style={{ marginTop: 8 }}>{sub}</p>}
        </div>
        {children}
      </div>
      {footer && <p className="auth-footer body-sm muted">{footer}</p>}
    </div>
  );
}
