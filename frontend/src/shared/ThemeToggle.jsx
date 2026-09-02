import Icon from "./Icon.jsx";
import { useTheme } from "../theme/ThemeProvider.jsx";

// Application-wide theme switch. Lives in the top navigation so it is reachable
// from every route; the choice persists in localStorage via ThemeProvider.
export default function ThemeToggle() {
  const { theme, toggleTheme } = useTheme();
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button
      type="button"
      className="btn btn--icon"
      onClick={toggleTheme}
      title={`Switch to ${next} mode`}
      aria-label={`Switch to ${next} mode`}
    >
      <Icon name={theme === "dark" ? "light_mode" : "dark_mode"} size={20} />
    </button>
  );
}
