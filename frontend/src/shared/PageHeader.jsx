// Page title block: headline + sub-line on the left, actions on the right,
// separated from the content by the Stitch hairline rule.
export default function PageHeader({ title, sub, meta, actions, size = "xl" }) {
  return (
    <header className="page-header">
      <div>
        <h2 className={size === "lg" ? "headline-lg" : "headline-xl"}>{title}</h2>
        {sub && <p className="sub body-md">{sub}</p>}
        {meta && <p className="mono-data muted" style={{ marginTop: 8 }}>{meta}</p>}
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </header>
  );
}
