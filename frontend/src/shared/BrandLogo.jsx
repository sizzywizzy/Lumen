import { Link } from "react-router-dom";
import LumenIcon from "./CameraArt.jsx";
import LumenLogo from "./LumenLogo.jsx";

// The full Lumen logo wherever it fits. On screens too narrow for it, the CSS
// in site.css swaps in the square icon instead.
export default function BrandLogo({ to = "/", height = 42, label = "Lumen home" }) {
  return (
    <Link to={to} className="brand" aria-label={label}>
      <span className="brand-full">
        <LumenLogo height={height} />
      </span>
      <span className="brand-small">
        <LumenIcon size={Math.round(height * 0.9)} />
      </span>
    </Link>
  );
}
