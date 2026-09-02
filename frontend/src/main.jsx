import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App.jsx";
import { ThemeProvider } from "./theme/ThemeProvider.jsx";
import { AuthProvider } from "./shared/AuthContext.jsx";
import { ProjectProvider } from "./shared/ProjectContext.jsx";
import "./index.css";

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
