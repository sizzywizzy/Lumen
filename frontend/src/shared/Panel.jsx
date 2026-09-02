import Icon from "./Icon.jsx";
import { cn } from "../lib/utils.js";

// Stitch "bento" surface: raised card, 1px outline-variant border, 8px radius.
// `sunken` uses surface-container-low, the tone the production-intel bento uses.
export default function Panel({ children, className, sunken = false, pad = false, clip = false, ...rest }) {
  return (
    <section
      className={cn("panel", sunken && "panel--sunken", pad && "panel--pad", clip && "panel--clip", className)}
      {...rest}
    >
      {children}
    </section>
  );
}

// Header strip used on framed panels (stripboard, leaderboard, terminal).
export function PanelHead({ title, icon, children, className }) {
  return (
    <header className={cn("panel-head", className)}>
      <h3 className="panel-title mono-label">
        {icon && <Icon name={icon} />}
        {title}
      </h3>
      {children && <div className="row row--tight">{children}</div>}
    </header>
  );
}

export function PanelFoot({ children, className }) {
  return <footer className={cn("panel-foot mono-label", className)}>{children}</footer>;
}

// Section title inside a padded panel, matching the production-intel bento.
export function PanelTitle({ title, icon, children }) {
  return (
    <div className="between" style={{ marginBottom: 24 }}>
      <h3 className="panel-title mono-label">
        {icon && <Icon name={icon} />}
        {title}
      </h3>
      {children}
    </div>
  );
}
