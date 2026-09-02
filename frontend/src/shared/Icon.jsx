import { cn } from "../lib/utils.js";

// Material Symbols Outlined — the icon set the Stitch designs are drawn with.
// Loaded as a font in index.html, so there is no icon dependency to install.
export default function Icon({ name, size, filled = false, className, style, ...rest }) {
  return (
    <span
      className={cn("material-symbols-outlined", filled && "filled", className)}
      style={size ? { fontSize: size, ...style } : style}
      aria-hidden="true"
      {...rest}
    >
      {name}
    </span>
  );
}
