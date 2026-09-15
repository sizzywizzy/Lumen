import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import { ThemeProvider } from "./theme/ThemeProvider.jsx";
import { AuthProvider } from "./shared/AuthContext.jsx";
import { ProjectProvider } from "./shared/ProjectContext.jsx";
import { installPressEffects } from "./lib/pressEffects.js";
import "./index.css";
import "./site.css";
import "./tactile.css";

// Click ripples and press feedback for every control, app-wide.
installPressEffects();

// AuthProvider sits above ProjectProvider: the active production comes from the
// signed-in member's memberships, so pipeline state can only ever load for a
// project the account actually belongs to.
ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <ThemeProvider>
      <BrowserRouter>
        <AuthProvider>
          <ProjectProvider>
            <App />
          </ProjectProvider>
        </AuthProvider>
      </BrowserRouter>
    </ThemeProvider>
  </React.StrictMode>
);
