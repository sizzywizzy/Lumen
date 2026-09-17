import { useCallback, useEffect, useRef, useState } from "react";
import Icon from "../../shared/Icon.jsx";
import { PosterCard } from "../../shared/Artwork.jsx";
import { api } from "../../lib/api.js";

const POLL_MS = 2500;

// Where the poster on screen came from, in words.
function provenanceNote(poster, painting) {
  if (painting && !poster) return "Lumen is making a poster from your script. It takes a few seconds.";
  if (painting) return "Making a new poster in a different style. This one stays up until it's ready.";
  if (!poster) return "There's no poster for this production yet.";
  if (poster.written_by) {
    return "Lumen drew this in a style picked at random, with a tagline and colours Gemini chose from your script.";
  }
  if (poster.fallback_reason === "no_api_key") {
    return "Lumen drew this offline, with a tagline and colours for the genre. With a Gemini API key, they come from your script.";
  }
  if (poster.fallback_reason === "pr_blocked") {
    return "PR review turned down the drafted taglines, so this poster uses a safe line for the genre.";
  }
  return "Gemini didn't answer, so this poster uses a tagline and colours for the genre. Try another in a minute.";
}

// The production's poster. Polls while one is being made and loads each
// poster's image once, through the signed-in request, since the image route is
// for members only. A producer's production planned before posters existed
// gets one the first time they open the Overview.
function usePoster(projectId, autoPaint) {
  const [info, setInfo] = useState(null); // { status, error, poster }
  const [image, setImage] = useState(null); // object URL of the poster on screen
  const [round, setRound] = useState(0); // bumped by each request for a new poster, restarting the poll
  const [requestError, setRequestError] = useState("");
  const autoPainted = useRef(false);
  const urlRef = useRef(null);

  const repaint = useCallback(async () => {
    setRequestError("");
    try {
      setInfo(await api.newPoster(projectId));
    } catch (err) {
      setRequestError(String(err.message || err));
    } finally {
      setRound((n) => n + 1);
    }
  }, [projectId]);

  useEffect(() => {
    setInfo(null);
    setImage(null);
    autoPainted.current = false;
  }, [projectId]);

  useEffect(() => {
    if (!projectId) return undefined;
    let cancelled = false;
    let timer;
    async function check() {
      try {
        const next = await api.getPoster(projectId);
        if (cancelled) return;
        setInfo(next);
        if (next.status === "painting") timer = setTimeout(check, POLL_MS);
      } catch {
        /* poster route unreachable: the title card stays */
      }
    }
    check();
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [projectId, round]);

  useEffect(() => {
    if (autoPaint && info?.status === "none" && !autoPainted.current) {
      autoPainted.current = true;
      repaint();
    }
  }, [autoPaint, info, repaint]);

  const posterId = info?.poster?.poster_id;
  useEffect(() => {
    if (!projectId || !posterId) return undefined;
    let cancelled = false;
    api
      .getPosterImage(projectId, posterId)
      .then((blob) => {
        if (cancelled) return;
        if (urlRef.current) URL.revokeObjectURL(urlRef.current);
        urlRef.current = URL.createObjectURL(blob);
        setImage(urlRef.current);
      })
      .catch(() => {
        /* the image didn't load: the title card stands in */
      });
    return () => {
      cancelled = true;
    };
  }, [projectId, posterId]);

  useEffect(() => () => urlRef.current && URL.revokeObjectURL(urlRef.current), []);

  return {
    poster: info?.poster || null,
    image: info?.poster ? image : null,
    painting: info?.status === "painting",
    error: requestError || (info?.status === "failed" ? `That poster didn't come through. ${info.error || ""}`.trim() : ""),
    repaint,
  };
}

// The poster beside the production's title. It opens full size with the
// tagline, the style it was drawn in and where its tagline came from, and
// producers can ask for another take from there.
export default function ProductionPoster({ projectId, title, genre, canEdit }) {
  const { poster, image, painting, error, repaint } = usePoster(projectId, canEdit);
  const dialogRef = useRef(null);
  const close = () => dialogRef.current?.close();

  return (
    <>
      <button
        type="button"
        className="poster-button"
        onClick={() => dialogRef.current?.showModal()}
        aria-haspopup="dialog"
        aria-label={painting ? `${title} poster, in progress` : `Open the ${title} poster`}
      >
        <PosterCard title={title} genre={genre} image={image} busy={painting} description={poster?.alt_text} />
      </button>

      <dialog
        ref={dialogRef}
        className="poster-viewer"
        aria-labelledby="poster-viewer-title"
        onClick={(e) => e.target === dialogRef.current && close()} // the backdrop; content sits in the body
      >
        <div className="poster-viewer__body">
          <PosterCard
            size="xl"
            title={title}
            genre={genre}
            image={image}
            tagline={poster?.tagline}
            busy={painting}
            description={poster?.alt_text}
          />
          <div className="poster-viewer__side">
            <div className="poster-viewer__head">
              <span className="kicker">The poster</span>
              <button type="button" className="btn btn--icon" onClick={close} aria-label="Close">
                <Icon name="close" />
              </button>
            </div>
            <h2 id="poster-viewer-title">{title}</h2>
            {poster?.tagline && <p className="poster-viewer__tagline">“{poster.tagline}”</p>}
            {poster && (
              <div className="row row--tight">
                {poster.style?.label && (
                  <span className="chip">
                    <Icon name="palette" />
                    {poster.style.label}
                  </span>
                )}
                <span className="chip">
                  <Icon name="draw" />
                  Drawn by Lumen
                </span>
              </div>
            )}
            <p className="poster-viewer__note">{provenanceNote(poster, painting)}</p>
            {error && (
              <div className="banner" data-tone="bad" role="alert">
                <Icon name="error" />
                <span>{error}</span>
              </div>
            )}
            {canEdit && (
              <div className="poster-viewer__actions">
                <button type="button" className="btn btn--primary btn--lg btn--block" onClick={repaint} disabled={painting}>
                  <Icon name={painting ? "progress_activity" : "shuffle"} className={painting ? "spin" : undefined} />
                  {painting ? "Making…" : poster ? "Try another style" : "Make a poster"}
                </button>
                <small className="field-hint">
                  Each new poster takes a different style at random and replaces this one once it's ready.
                </small>
              </div>
            )}
          </div>
        </div>
      </dialog>
    </>
  );
}
