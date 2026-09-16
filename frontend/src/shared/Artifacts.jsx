import { useId, useState } from "react";
import { cn } from "../lib/utils.js";

// The small physical things the site lays over its cards: a photo that falls
// back gracefully, a Polaroid, a paper clip, camera tape, a rubber stamp, a
// coffee ring and a pencil note. Styles live in tactile.css. Pieces that only
// decorate are hidden from assistive technology; a stamp or a note that says
// something can opt back in.

// A photograph ({ src, srcSet, width, height, alt }). If the image never loads
// the frame keeps a toned placeholder and the description stays available to
// screen readers, instead of a broken-image icon. `decorative` drops the alt
// text for repeats of a picture that is already described elsewhere.
export function Photo({ photo, sizes, decorative = false, loading = "lazy", className, style }) {
  const [failed, setFailed] = useState(false);
  if (failed || !photo?.src) {
    return decorative || !photo?.alt ? (
      <span className={cn("photo", "photo--missing", className)} style={style} aria-hidden="true" />
    ) : (
      <span className={cn("photo", "photo--missing", className)} style={style} role="img" aria-label={photo.alt} />
    );
  }
  return (
    <img
      className={cn("photo", className)}
      style={style}
      src={photo.src}
      srcSet={photo.srcSet}
      sizes={sizes}
      width={photo.width}
      height={photo.height}
      alt={decorative ? "" : photo.alt}
      loading={loading}
      decoding="async"
      onError={() => setFailed(true)}
    />
  );
}

// The casting Polaroid: a square window, the thick bottom margin and a name
// in marker.
export function Polaroid({ photo, caption, className, children }) {
  return (
    <span className={cn("polaroid", className)} aria-hidden="true">
      <span className="polaroid__window">
        <Photo photo={photo} sizes="140px" loading="eager" decorative />
      </span>
      {caption && <span className="polaroid__caption">{caption}</span>}
      {children}
    </span>
  );
}

// A steel paper clip, drawn upright with its long loop at the back.
export function PaperClip({ className }) {
  const steel = `clip-steel-${useId().replace(/:/g, "")}`;
  return (
    <svg className={cn("paper-clip", className)} viewBox="0 0 20 60" aria-hidden="true" focusable="false">
      <defs>
        <linearGradient id={steel} x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor="#6f747a" />
          <stop offset="0.45" stopColor="#f4f5f6" />
          <stop offset="0.7" stopColor="#a9aeb3" />
          <stop offset="1" stopColor="#d9dcdf" />
        </linearGradient>
      </defs>
      <path
        d="M6 18V44a4 4 0 0 0 8 0V10a6 6 0 0 0-12 0V48a8 8 0 0 0 16 0V16"
        fill="none"
        stroke={`url(#${steel})`}
        strokeWidth="2.2"
        strokeLinecap="round"
      />
    </svg>
  );
}

// A torn strip of camera tape, the kind a camera assistant labels in marker.
// The torn ends are a clip-path on the inner strip, so the outer span can
// still cast a shadow.
export function Tape({ label, className }) {
  return (
    <span className={cn("tape", className)} aria-hidden="true">
      <span className="tape__strip" />
      {label && <span className="tape__label">{label}</span>}
    </span>
  );
}

// An inked rubber stamp ("Top pick", "Ruled out"). tone: "gold" or "red".
export function Stamp({ children, tone = "gold", decorative = true, className }) {
  return (
    <span className={cn("stamp", `stamp--${tone}`, className)} aria-hidden={decorative || undefined}>
      {children}
    </span>
  );
}

export function CoffeeRing({ className }) {
  return <span className={cn("coffee-ring", className)} aria-hidden="true" />;
}

// Handwriting in the margin. Decorative by default; pass decorative={false}
// when the note carries something a reader should hear.
export function PencilNote({ children, decorative = true, className }) {
  return (
    <span className={cn("pencil-note", className)} aria-hidden={decorative || undefined}>
      {children}
    </span>
  );
}

// A ticket stub: the main face, then a torn-off counterfoil down the side.
// The notches at the perforation are a mask in tactile.css, so whatever holds
// a ticket casts its shadow with a filter instead of a box-shadow.
export function Ticket({ stub, children, className }) {
  return (
    <div className={cn("ticket", className)}>
      <div className="ticket__main">{children}</div>
      {stub && (
        <div className="ticket__stub">
          <span>{stub}</span>
        </div>
      )}
    </div>
  );
}
