import { useCallback, useState } from "react";
import { flushSync } from "react-dom";
import { castByRole } from "../../lib/production.js";
import ActorCard, { viewName } from "./ActorCard.jsx";

// The cast as a casting wall. Each role is pinned up with everyone who read
// for it: the top pick's 8x10, runners-up as audition Polaroids and contact
// sheet frames, the ruled-out stamped and faded. Clicking a face opens that
// actor's mini-profile in place (ActorCard.jsx), so the page feels like
// meeting the people behind the film rather than scanning a table.

const prefersMotion = () => !window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Opening a profile reflows the wall, so the change runs inside a view
// transition where the browser has one: the cards glide and resize into their
// new places instead of jumping. Anywhere else it simply happens.
function withTransition(update) {
  if (typeof document.startViewTransition !== "function" || !prefersMotion()) {
    update();
    return;
  }
  document.startViewTransition(() => flushSync(update));
}

function tally(role) {
  const running = (role.pick ? 1 : 0) + role.runnersUp.length;
  return [`${running} in the running`, role.ruledOut.length && `${role.ruledOut.length} ruled out`].filter(Boolean).join(" · ");
}

export default function CastBoard({ state }) {
  const roles = castByRole(state);
  const [openId, setOpenId] = useState(null);
  const toggle = useCallback((id) => withTransition(() => setOpenId((current) => (current === id ? null : id))), []);

  return (
    <div className="cast-wall">
      {roles.map((role) => {
        const people = [role.pick, ...role.runnersUp, ...role.ruledOut].filter(Boolean);
        const titleId = `cast-role-${viewName(role.roleId)}`;
        return (
          <section
            key={role.roleId}
            className="cast-role"
            aria-labelledby={titleId}
            style={{ viewTransitionName: `role-${viewName(role.roleId)}` }}
          >
            <header className="cast-role__head">
              <p className="cast-role__type">{role.type || "Role"}</p>
              <h2 className="cast-role__name" id={titleId}>
                {role.name}
              </h2>
              {role.description && <p className="cast-role__desc">{role.description}</p>}
              {people.length > 0 && <p className="cast-role__tally">{tally(role)}</p>}
            </header>

            {people.length ? (
              <ul className="cast-role__grid">
                {people.map((person, index) => (
                  <ActorCard
                    key={person.id}
                    person={person}
                    role={role}
                    index={index}
                    open={openId === person.id}
                    onToggle={toggle}
                  />
                ))}
              </ul>
            ) : (
              <p className="cast-role__empty">No actors have been suggested for this role yet.</p>
            )}
          </section>
        );
      })}
    </div>
  );
}
