import Icon from "./Icon.jsx";

// Shared empty/idle state. Every phase view shows this until the pipeline
// has produced data, so an un-run project reads as "waiting", not "broken".
export default function EmptyState({ icon = "hourglass_empty", title, children, action }) {
  return (
    <div className="empty">
      <Icon name={icon} />
      {title && <h4>{title}</h4>}
      {children && <p>{children}</p>}
      {action}
    </div>
  );
}
