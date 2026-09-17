import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import Icon from "../../shared/Icon.jsx";
import { PencilNote } from "../../shared/Artifacts.jsx";
import { signOffs } from "../../lib/production.js";
import { Card } from "./parts.jsx";

// The human sign-off queue: everything the agents stopped to ask a person
// about (GlobalState.human_escalations), each with a link to where it gets
// decided. Nothing shows once the queue is empty.
export default function SignOffQueue({ state, className }) {
  const items = signOffs(state);
  const { hash } = useLocation();

  // The Agents menu links here as /overview#sign-off.
  useEffect(() => {
    if (hash === "#sign-off") document.getElementById("sign-off")?.scrollIntoView({ behavior: "smooth", block: "center" });
  }, [hash]);

  if (!items.length) return null;
  return (
    <Card
      className={className}
      title="Waiting for your sign-off"
      action={<span className="chip chip--ink">{items.length} open</span>}
    >
      <PencilNote className="signoff-note">the agents stopped here for a person</PencilNote>
      <ul className="signoff-list" id="sign-off">
        {items.map((item) => (
          <li className="signoff-row" key={item.key}>
            <span className="round-icon">
              <Icon name={item.icon} />
            </span>
            <div className="signoff-main">
              <span className="signoff-kicker">{item.kicker}</span>
              <strong className="signoff-title">{item.title}</strong>
              {item.reason && <p className="signoff-reason">{item.reason}</p>}
            </div>
            <Link to={item.to} className="btn btn--ghost signoff-action">
              {item.action}
              <Icon name="arrow_forward" size={16} />
            </Link>
          </li>
        ))}
      </ul>
    </Card>
  );
}
