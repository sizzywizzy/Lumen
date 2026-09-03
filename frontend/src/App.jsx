import { Navigate, Route, Routes } from "react-router-dom";
import AppShell from "./shared/AppShell.jsx";
import RequireAuth from "./shared/RequireAuth.jsx";
import LoginPage from "./features/auth/LoginPage.jsx";
import RegisterPage from "./features/auth/RegisterPage.jsx";
import JoinPage from "./features/auth/JoinPage.jsx";
import IntakePage from "./features/intake/IntakePage.jsx";
import CastingView from "./features/casting/CastingView.jsx";
import ProdView from "./features/production/ProdView.jsx";
import LaunchView from "./features/launch/LaunchView.jsx";
import LogsPage from "./features/logs/LogsPage.jsx";
import TeamPage from "./features/team/TeamPage.jsx";
import SettingsPage from "./features/settings/SettingsPage.jsx";
import AdvisorsPage from "./features/advisors/AdvisorsPage.jsx";

// Route table. Every entry in shared/navigation.js resolves here, so no nav
// item points at a screen that does not exist.
//
// Public: sign-in, production sign-up, and invite redemption.
// Everything else sits behind RequireAuth and inside AppShell; the backend
// independently checks membership on every request, so the guard below is
// convenience rather than the security boundary.
export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/join/:token" element={<JoinPage />} />
      <Route path="/join" element={<JoinPage />} />

      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<IntakePage />} />
          <Route path="casting" element={<CastingView />} />
          <Route path="schedule" element={<ProdView />} />
          <Route path="marketing" element={<LaunchView />} />
          <Route path="advisors" element={<AdvisorsPage />} />
          <Route path="logs" element={<LogsPage />} />
          <Route path="team" element={<TeamPage />} />
          <Route path="settings" element={<SettingsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Route>
      </Route>
    </Routes>
  );
}
