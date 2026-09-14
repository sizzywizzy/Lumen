import { Navigate, Route, Routes } from "react-router-dom";
import AppLayout from "./shared/AppLayout.jsx";
import RequireAuth from "./shared/RequireAuth.jsx";
import HomePage from "./features/site/HomePage.jsx";
import LoginPage from "./features/auth/LoginPage.jsx";
import RegisterPage from "./features/auth/RegisterPage.jsx";
import JoinPage from "./features/auth/JoinPage.jsx";
import NewScriptPage from "./features/intake/NewScriptPage.jsx";
import OverviewPage from "./features/results/OverviewPage.jsx";
import SchedulePage from "./features/results/SchedulePage.jsx";
import CastPage from "./features/results/CastPage.jsx";
import AudiencePage from "./features/results/AudiencePage.jsx";
import TeamPage from "./features/team/TeamPage.jsx";
import SettingsPage from "./features/settings/SettingsPage.jsx";
// Earlier tools: still reachable by address, but no longer in the menu.
import IntakePage from "./features/intake/IntakePage.jsx";
import CastingView from "./features/casting/CastingView.jsx";
import ProdView from "./features/production/ProdView.jsx";
import LaunchView from "./features/launch/LaunchView.jsx";
import LogsPage from "./features/logs/LogsPage.jsx";
import AdvisorsPage from "./features/advisors/AdvisorsPage.jsx";

// Route table.
//
// Public: the homepage, sign-in, production sign-up and invite redemption.
// Everything else sits behind RequireAuth and inside AppLayout; the backend
// independently checks membership on every request, so the guard below is
// convenience rather than the security boundary.
export default function App() {
  return (
    <Routes>
      <Route path="/" element={<HomePage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/join/:token" element={<JoinPage />} />
      <Route path="/join" element={<JoinPage />} />

      <Route element={<RequireAuth />}>
        <Route element={<AppLayout />}>
          <Route path="overview" element={<OverviewPage />} />
          <Route path="schedule" element={<SchedulePage />} />
          <Route path="cast" element={<CastPage />} />
          <Route path="audience" element={<AudiencePage />} />
          <Route path="new" element={<NewScriptPage />} />
          <Route path="team" element={<TeamPage />} />
          <Route path="settings" element={<SettingsPage />} />

          <Route path="intake" element={<IntakePage />} />
          <Route path="casting" element={<CastingView />} />
          <Route path="production" element={<ProdView />} />
          <Route path="marketing" element={<LaunchView />} />
          <Route path="advisors" element={<AdvisorsPage />} />
          <Route path="logs" element={<LogsPage />} />
          <Route path="*" element={<Navigate to="/overview" replace />} />
        </Route>
      </Route>
    </Routes>
  );
}
