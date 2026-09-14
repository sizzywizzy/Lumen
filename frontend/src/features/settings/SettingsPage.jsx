import Panel from "../../shared/Panel.jsx";
import PageHeader from "../../shared/PageHeader.jsx";
import Icon from "../../shared/Icon.jsx";
import EmptyState from "../../shared/EmptyState.jsx";
import DirectorControls from "../production/DirectorControls.jsx";
import { useProject } from "../../shared/ProjectContext.jsx";
import { useAuth } from "../../shared/AuthContext.jsx";
import { useTheme } from "../../theme/ThemeProvider.jsx";
import { cn, money, shortDate, statusLabel } from "../../lib/utils.js";

const THEMES = [
  { key: "dark", label: "Dark", icon: "dark_mode", hint: "Warm charcoal with golden highlights. Easy on the eyes at night." },
  { key: "light", label: "Light", icon: "light_mode", hint: "Warm paper with amber accents. Easy to read by day." },
];

// Where casting stands for the production as a whole.
const CASTING_WORDS = { SOURCING: "Looking for actors", SCREENING: "Reviewing actors", LOCKED: "Cast chosen" };

// Settings route: the same director constraints the schedule agent reads, plus
// the application-wide appearance choice and the live project summary.
export default function SettingsPage() {
  const { state, projectId, intake } = useProject();
  const { activeProduction } = useAuth();
  const { theme, setTheme } = useTheme();
  const castingStatus = state?.casting_status;

  return (
    <>
      <PageHeader
        title="Settings"
        sub="How Lumen looks, the rules for the shooting schedule, and a summary of this production."
        size="lg"
      />

      <Panel className="panel--pad">
        <h3 className="panel-title mono-label" style={{ marginBottom: 16 }}>
          <Icon name="palette" />
          Appearance
        </h3>
        <div className="matrix">
          {THEMES.map((t) => (
            <button
              key={t.key}
              type="button"
              className={cn("month-tile", theme === t.key && "selected")}
              onClick={() => setTheme(t.key)}
              aria-pressed={theme === t.key}
            >
              <span className="row row--tight" style={{ marginBottom: 6 }}>
                <Icon name={t.icon} size={20} />
                <strong>{t.label}</strong>
              </span>
              <small>{t.hint}</small>
            </button>
          ))}
        </div>
        <p className="muted body-sm" style={{ marginTop: 12 }}>
          The choice is stored in this browser and applies to every screen. With no saved choice, Lumen follows your
          operating system.
        </p>
      </Panel>

      <Panel className="panel--pad">
        <h3 className="panel-title mono-label" style={{ marginBottom: 16 }}>
          <Icon name="tune" />
          Schedule rules
        </h3>
        {state ? (
          <DirectorControls />
        ) : (
          <EmptyState icon="settings" title="Nothing to set yet">
            Drop a script first. Once it has been read, you can adjust the schedule rules here.
          </EmptyState>
        )}
      </Panel>

      <Panel className="panel--pad">
        <h3 className="panel-title mono-label" style={{ marginBottom: 16 }}>
          <Icon name="info" />
          This production
        </h3>
        <dl className="mono-data" style={{ display: "grid", gap: 10, margin: 0 }}>
          <div className="between">
            <span className="muted">Production</span>
            <span>{activeProduction?.name || state?.script_context?.title || projectId}</span>
          </div>
          <div className="between">
            <span className="muted">Casting</span>
            <span>{castingStatus ? CASTING_WORDS[castingStatus] || statusLabel(castingStatus) : "—"}</span>
          </div>
          <div className="between">
            <span className="muted">Budget</span>
            <span>{state?.budget_state?.cap ? money(state.budget_state.cap) : "—"}</span>
          </div>
          <div className="between">
            <span className="muted">Scenes scheduled</span>
            <span>{state?.schedule?.stripboard?.length ?? 0}</span>
          </div>
          <div className="between">
            <span className="muted">Agent messages</span>
            <span>{state?.event_log?.length ?? 0}</span>
          </div>
          {intake?.fileName && (
            <div className="between">
              <span className="muted">Script</span>
              <span>{intake.fileName}</span>
            </div>
          )}
          {intake?.start && (
            <div className="between">
              <span className="muted">Shooting dates</span>
              <span>
                {shortDate(intake.start)} to {shortDate(intake.wrap)}
              </span>
            </div>
          )}
        </dl>
        {intake?.notes && (
          <>
            <p className="mono-label muted" style={{ marginTop: 16, marginBottom: 6 }}>
              Director's notes
            </p>
            <p className="body-sm">{intake.notes}</p>
          </>
        )}
      </Panel>
    </>
  );
}
