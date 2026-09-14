import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";

// Single source of truth for light/dark across the whole app.
// The theme is written to <html data-theme> — every component reads colour
// through the CSS custom properties defined in index.css, so nothing needs
// its own theme logic. index.html applies the same rule before first paint
// so there is no flash on load.
//
// Lumen is light by default. Dark is an option the viewer turns on, and only
// that explicit choice is stored.

const STORAGE_KEY = "lumen-theme-choice";
const ThemeContext = createContext({ theme: "light", setTheme: () => {}, toggleTheme: () => {} });

function readStoredTheme() {
  try {
    return localStorage.getItem(STORAGE_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light"; // storage blocked (private window, embedded frame)
  }
}

export function ThemeProvider({ children }) {
  const [theme, setThemeState] = useState(readStoredTheme);

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
  }, [theme]);

  const setTheme = useCallback((next) => {
    setThemeState(next);
    try {
      localStorage.setItem(STORAGE_KEY, next);
    } catch {
      /* not persistable — the theme still applies for this session */
    }
  }, []);

  const toggleTheme = useCallback(() => setTheme(theme === "dark" ? "light" : "dark"), [theme, setTheme]);
  const value = useMemo(() => ({ theme, setTheme, toggleTheme }), [theme, setTheme, toggleTheme]);

  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme() {
  return useContext(ThemeContext);
}
