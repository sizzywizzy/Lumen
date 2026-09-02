import Panel from "../../shared/Panel.jsx";
import PageHeader from "../../shared/PageHeader.jsx";
import Icon from "../../shared/Icon.jsx";
import EmptyState from "../../shared/EmptyState.jsx";
import DirectorControls from "../production/DirectorControls.jsx";
import { useProject } from "../../shared/ProjectContext.jsx";
import { useTheme } from "../../theme/ThemeProvider.jsx";
import { cn, money } from "../../lib/utils.js";

const THEMES = [
  { key: "dark", label: "Cinematic Command", icon: "dark_mode", hint: "Wine and plum on charcoal — the on-set default." },
  { key: "light", label: "Alexandria", icon: "light_mode", hint: "Editorial serif on paper — for reviews and print-outs." },
];

// Settings route: the same director constraints the schedule agent reads, plus
// the application-wide appearance choice and the live project summary.
export default function SettingsPage() {
  const { state, projectId, intake } = useProject();
  const { theme, setTheme } = useTheme();

  return (
    <>
      <PageHeader
        title="Settings"
        sub="Director constraints, appearance and the current project snapshot."
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
          The choice is stored in this browser and applies to every screen. With no saved choice, CineNode follows your
          operating system.
        </p>
      </Panel>

      <Panel className="panel--pad">
        <h3 className="panel-title mono-label" style={{ marginBottom: 16 }}>
          <Icon name="tune" />
          Director controls
        </h3>
        {state ? (
          <DirectorControls />
        ) : (
          <EmptyState icon="settings" title="No project state yet">
            Seed a project from Script Intake, then the schedule constraints become editable here.
          </EmptyState>
        )}
      </Panel>

      <Panel className="panel--pad">
        <h3 className="panel-title mono-label" style={{ marginBottom: 16 }}>
          <Icon name="info" />
          Project snapshot
        </h3>
        <dl className="mono-data" style={{ display: "grid", gap: 10, margin: 0 }}>
          <div className="between">
            <span className="muted">Project id</span>
            <span>{projectId}</span>
          </div>
          <div className="between">
            <span className="muted">Casting status</span>
            <span>{state?.casting_status || "—"}</span>
          </div>
          <div className="between">
            <span className="muted">Budget cap</span>
            <span>{state?.budget_state?.cap ? money(state.budget_state.cap) : "—"}</span>
          </div>
          <div className="between">
            <span className="muted">Scenes scheduled</span>
            <span>{state?.schedule?.stripboard?.length ?? 0}</span>
          </div>
          <div className="between">
            <span className="muted">A2A envelopes</span>
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
              <span className="muted">Production window</span>
              <span>
                {intake.start} → {intake.wrap}
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
