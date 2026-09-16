import { useId, useRef, useState } from "react";
import Icon from "../../shared/Icon.jsx";
import { PortraitArt } from "../../shared/Artwork.jsx";
import { PaperClip, Photo, Stamp, Tape } from "../../shared/Artifacts.jsx";
import { cn, money } from "../../lib/utils.js";

// One actor on the casting wall: a face that opens into a mini-profile with a
// filmstrip of photos, previous work and the characters played (or, for
// someone without screen credits yet, their training and background), and
// what the scout, the audition and the casting director made of them.

// a safe id and view-transition-name fragment from any candidate or role id
export const viewName = (id) => String(id).replace(/[^a-zA-Z0-9_-]/g, "-");

// The top pick is printed as an 8x10 with the name in the border; everyone
// else alternates audition Polaroids and frames cut from a contact sheet,
// each pinned up a little crooked.
const LOOKS = ["polaroid", "frame"];
const TILTS = ["-1.1deg", "0.8deg", "-0.4deg", "1.3deg", "-0.8deg", "0.5deg"];

function following(count) {
  if (count >= 1e6) return `${(count / 1e6).toFixed(1).replace(/\.0$/, "")}M`;
  if (count >= 1e3) return `${Math.round(count / 1e3)}k`;
  return String(count);
}

function standing(person, role) {
  if (person.ruledOut) return `Ruled out for ${role.name}`;
  return `${person.isPick ? "Top pick" : "Runner-up"} for ${role.name}`;
}

function Face({ person, photo, sizes }) {
  if (!photo) return <PortraitArt name={person.name} decorative />;
  return (
    <Photo
      photo={photo}
      sizes={sizes}
      decorative
      style={photo.position ? { objectPosition: photo.position } : undefined}
    />
  );
}

function Section({ title, children }) {
  return (
    <section className="profile-section">
      <h4 className="profile-section__title">{title}</h4>
      {children}
    </section>
  );
}

export default function ActorCard({ person, role, index, open, onToggle }) {
  const { profile } = person;
  const look = person.isPick ? "print" : LOOKS[index % LOOKS.length];
  const faceRef = useRef(null);
  const uid = viewName(useId());
  const profileId = `actor-profile${uid}`;
  const nameId = `actor-name${uid}`;
  const [shown, setShown] = useState(0);
  const [previous, setPrevious] = useState(null);

  const photos = profile.photos;
  const current = open ? photos[shown] || profile.headshot : profile.headshot;
  const background = [...profile.experience, ...profile.training];

  function show(i) {
    if (i < 0 || i === shown) return;
    setPrevious(photos[shown]);
    setShown(i);
  }
  function toggle() {
    setShown(0);
    setPrevious(null);
    onToggle(person.id);
  }
  function close() {
    toggle();
    faceRef.current?.focus({ preventScroll: true });
  }

  return (
    <li
      className={cn(
        "actor-card",
        `actor-card--${look}`,
        person.isPick && "is-pick",
        person.ruledOut && "is-out",
        open && "is-open"
      )}
      style={{ "--tilt": TILTS[index % TILTS.length], viewTransitionName: `actor-${viewName(person.id)}` }}
      onKeyDown={(event) => {
        if (open && event.key === "Escape") close();
      }}
    >
      <button
        ref={faceRef}
        type="button"
        className="actor-card__face"
        aria-expanded={open}
        aria-controls={open ? profileId : undefined}
        onClick={toggle}
      >
        <span className="actor-card__print">
          <span
            className="actor-card__photo"
            style={previous ? { backgroundImage: `url("${previous.src}")` } : undefined}
          >
            <Face
              key={current?.src || "portrait"}
              person={person}
              photo={current}
              sizes={open ? "(max-width: 720px) 80vw, 320px" : "(max-width: 720px) 45vw, 240px"}
            />
          </span>
          {look === "print" && (
            <span className="actor-card__printed-name" aria-hidden="true">
              {person.name}
            </span>
          )}
          {look === "polaroid" && (
            <span className="actor-card__scrawl" aria-hidden="true">
              {person.name.split(" ")[0]}
            </span>
          )}
          {person.isPick && <Stamp className="actor-card__stamp">Top pick</Stamp>}
          {person.ruledOut && (
            <Stamp tone="red" className="actor-card__stamp">
              Ruled out
            </Stamp>
          )}
          {open && <PaperClip className="actor-card__clip" />}
        </span>
        <span className="actor-card__caption">
          <span className="actor-card__name">{person.name}</span>
          <span className="actor-card__line">
            {person.ruledOut ? "Ruled out" : person.isPick ? "Top pick" : "Runner-up"} · {money(person.fee)}
            {!person.ruledOut && ` · fit ${person.fit}`}
          </span>
          <span className="actor-card__cue" aria-hidden="true">
            Meet {person.name.split(" ")[0]}
            <Icon name="arrow_forward" size={16} />
          </span>
        </span>
      </button>

      {open && photos.length > 1 && (
        <div className="profile-strip" role="group" aria-label={`Photos of ${person.name}`}>
          {photos.map((photo, i) => (
            <button
              key={photo.src}
              type="button"
              className={cn("profile-strip__frame", i === shown && "is-shown")}
              aria-pressed={i === shown}
              aria-label={photo.caption ? `Show ${photo.caption}` : `Show photo ${i + 1} of ${photos.length}`}
              onClick={() => show(i)}
            >
              <Photo photo={photo} sizes="84px" decorative style={photo.position ? { objectPosition: photo.position } : undefined} />
            </button>
          ))}
        </div>
      )}

      {open && (
        <div className="actor-profile" id={profileId} role="region" aria-labelledby={nameId}>
          <div className="actor-profile__head">
            <p className="actor-profile__kicker">{standing(person, role)}</p>
            <h3 className="actor-profile__name" id={nameId}>
              {person.name}
            </h3>
            {(person.place || profile.agency) && (
              <p className="actor-profile__where">
                {[person.place, profile.agency && `Represented by ${profile.agency}`].filter(Boolean).join(" · ")}
              </p>
            )}
            <button
              type="button"
              className="btn btn--icon actor-profile__close"
              aria-label={`Close ${person.name}'s profile`}
              onClick={close}
            >
              <Icon name="close" />
            </button>
          </div>

          {photos[shown]?.caption && (
            <p className="actor-profile__showing" aria-live="polite">
              <Icon name="photo_camera" size={16} />
              {photos[shown].caption}
            </p>
          )}

          <dl className="actor-profile__facts">
            <div>
              <dt>{person.ruledOut ? "Asking fee" : "Fee"}</dt>
              <dd>{money(person.fee)}</dd>
            </div>
            {!person.ruledOut && (
              <div>
                <dt>Fit</dt>
                <dd>
                  {person.fit}
                  <small> of 100</small>
                </dd>
              </div>
            )}
            {profile.followers > 0 && (
              <div>
                <dt>Following</dt>
                <dd>{following(profile.followers)}</dd>
              </div>
            )}
          </dl>

          {person.ruledOut && person.reason && (
            <p className="actor-profile__ruled">
              <Icon name="block" size={18} />
              {person.reason}
            </p>
          )}

          <div className="actor-profile__columns">
            <div>
              {profile.credits.length > 0 && (
                <Section title="Previous work">
                  <ol className="credit-list">
                    {profile.credits.map((credit) => {
                      const still = credit.image ? photos.findIndex((photo) => photo.src === credit.image.src) : -1;
                      return (
                        <li className="credit" key={`${credit.title}-${credit.year}`}>
                          {still >= 0 ? (
                            <button
                              type="button"
                              className={cn("credit__frame", still === shown && "is-shown")}
                              aria-label={`Show the still from ${credit.title}`}
                              onClick={() => show(still)}
                            >
                              <Photo photo={credit.image} sizes="72px" decorative />
                            </button>
                          ) : (
                            <span className="credit__frame credit__frame--empty" aria-hidden="true">
                              <Icon name="movie" size={16} />
                            </span>
                          )}
                          <span className="credit__text">
                            {(credit.kind || credit.year) && (
                              <span className="credit__meta">{[credit.kind, credit.year].filter(Boolean).join(" · ")}</span>
                            )}
                            <span className="credit__title">{credit.title}</span>
                            {credit.role && <span className="credit__role">as {credit.role}</span>}
                          </span>
                        </li>
                      );
                    })}
                  </ol>
                </Section>
              )}

              {background.length > 0 && (
                <Section title={profile.credits.length ? "Training and background" : "No screen credits yet · Background"}>
                  <ul className="background-list">
                    {background.map((line, i) => (
                      <li key={`${i}-${line}`}>{line}</li>
                    ))}
                  </ul>
                </Section>
              )}

              {!profile.credits.length && !background.length && (
                <p className="actor-profile__empty">No credits, training or background on file yet.</p>
              )}
            </div>

            <div>
              {profile.match && (
                <Section title="Why Lumen suggested them">
                  <blockquote className="actor-profile__quote">{profile.match}</blockquote>
                </Section>
              )}
              {profile.review && profile.review !== profile.match && (
                <Section title="From the audition">
                  <p className="actor-profile__text">{profile.review}</p>
                </Section>
              )}
              {profile.press && (
                <Section title="In the press">
                  <p className="actor-profile__text">{profile.press}</p>
                </Section>
              )}
              {profile.note && (
                <p className="sticky-note">
                  <Tape className="sticky-note__tape" />
                  <span className="visually-hidden">Casting note: </span>
                  {profile.note}
                </p>
              )}
              {profile.reel && (
                <a className="card-link actor-profile__reel" href={profile.reel} target="_blank" rel="noreferrer noopener">
                  Watch the showreel
                  <Icon name="arrow_outward" size={16} />
                </a>
              )}
            </div>
          </div>
        </div>
      )}
    </li>
  );
}
