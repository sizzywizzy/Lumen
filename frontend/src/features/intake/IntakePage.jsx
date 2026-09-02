import { useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../../lib/api.js";
import { useProject } from "../../shared/ProjectContext.jsx";
import Panel from "../../shared/Panel.jsx";
import PageHeader from "../../shared/PageHeader.jsx";
import Icon from "../../shared/Icon.jsx";
import { cn } from "../../lib/utils.js";

// Phase 0 — intake. Drop the script, set budget + shooting window + notes, then
// "Start agent orchestration" seeds the project (POST /api/pipeline/init) and
// hands off to the casting board. Same behaviour as the original cover page;
// the layout is the Stitch "New Production Intake" screen.
export default function IntakePage() {
  const navigate = useNavigate();
  const { startProject, projectId, canEdit } = useProject();

  const [file, setFile] = useState(null);
  const fileName = file?.name || null;
  const [dragging, setDragging] = useState(false);
  const [budget, setBudget] = useState("250000");
  const [start, setStart] = useState("2026-09-01");
  const [wrap, setWrap] = useState("2026-09-26");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const fileInput = useRef(null);

  const budgetNum = Number(budget || 0);
  const budgetFmt = budgetNum ? budgetNum.toLocaleString("en-US") : "";

  const windowLine = useMemo(() => {
    const ms = Date.parse(wrap) - Date.parse(start);
    const days = Number.isFinite(ms) ? Math.round(ms / 86400000) : NaN;
    if (!Number.isFinite(days) || days <= 0) return "Pick a start and a wrap date";
    const weeks = Math.max(1, Math.round(days / 7));
    return `${days} days · about ${weeks} weeks on set`;
  }, [start, wrap]);

  function onDrop(e) {
    e.preventDefault();
    setDragging(false);
    const f = e.dataTransfer?.files?.[0];
    if (f) setFile(f);
  }

  function onPick(e) {
    const f = e.target.files?.[0];
    if (f) setFile(f);
  }

  // Plain formats are read as text in the browser; anything else (.pdf, .fdx)
  // goes up as base64 and the backend extracts it.
  const PLAIN = /\.(txt|fountain|md|markdown|text)$/i;

  function readAsBase64(f) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error("Could not read the file."));
      reader.onload = () => resolve(String(reader.result).split(",")[1] || "");
      reader.readAsDataURL(f);
    });
  }

  async function startPreProduction() {
    if (!fileName || busy || !canEdit) return;
    setBusy(true);
    setError("");
    // Seed this production's state with the budget so the studio reflects it
    // before the first run. The project id comes from the signed-in member's
    // active production — it is never chosen by the client.
    try {
      await api.initPipeline(projectId, budgetNum || undefined);
    } catch (e) {
      setBusy(false);
      setError(String(e.message || e));
      return;
    }

    // Then upload the screenplay itself, so every later phase reads the real
    // script instead of just its filename.
    let scriptInfo = null;
    try {
      const payload = PLAIN.test(file.name)
        ? { filename: file.name, text: await file.text() }
        : { filename: file.name, content_base64: await readAsBase64(file) };
      scriptInfo = await api.uploadScript(projectId, payload);
    } catch (e) {
      setBusy(false);
      setError(`Script uploaded but could not be read: ${e.message || e}`);
      return;
    }

    setBusy(false);
    startProject(projectId, {
      budget: budgetNum || undefined, start, wrap, notes,
      fileName, script: scriptInfo,
    });
    navigate("/casting");
  }

  return (
    <div className="page-inner page-inner--narrow stack--md">
      <PageHeader
        title="New Production Intake"
        sub="Initialize agent orchestration pipeline via technical script analysis."
        meta={
          <>
            Target project: <span className="text-primary">{projectId}</span>
          </>
        }
      />

      <div className="grid">
        {/* Script dropzone — span 8 */}
        <Panel className="span-8 panel--pad relative" style={{ overflow: "hidden" }}>
          <div className="tint-wash" />
          <h3 className="panel-title mono-label" style={{ marginBottom: 24, position: "relative" }}>
            <Icon name="upload_file" />
            Technical Script Analysis
          </h3>

          <input
            ref={fileInput}
            type="file"
            accept=".pdf,.fountain,.fdx,.txt"
            onChange={onPick}
            style={{ display: "none" }}
          />
          <div
            className={cn("dropzone", dragging && "dragging", fileName && "filled")}
            role="button"
            tabIndex={0}
            onClick={() => fileInput.current?.click()}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                fileInput.current?.click();
              }
            }}
            onDragOver={(e) => {
              e.preventDefault();
              if (!dragging) setDragging(true);
            }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
          >
            {fileName ? (
              <>
                <Icon name="task_alt" className="cloud" />
                <p className="body-lg filename" style={{ fontWeight: 500 }}>
                  {fileName}
                </p>
                <p className="mono-data muted">
                  {(file?.size / 1024).toFixed(0)} KB · read on start and shared with the production
                </p>
                <button
                  type="button"
                  className="btn btn--ghost"
                  style={{ marginTop: 12 }}
                  onClick={(e) => {
                    e.stopPropagation();
                    setFile(null);
                    if (fileInput.current) fileInput.current.value = "";
                  }}
                >
                  Remove
                </button>
              </>
            ) : (
              <>
                <Icon name="cloud_upload" className="cloud" />
                <p className="body-lg">Drag and drop screenplay file</p>
                <p className="mono-data muted">Supported formats: .fdx, .pdf, .fountain, .txt</p>
                <span className="btn btn--ghost" style={{ marginTop: 12 }}>
                  Browse Files
                </span>
              </>
            )}
          </div>
        </Panel>

        {/* Parameters — span 4 */}
        <div className="span-4 stack">
          <Panel className="panel--pad">
            <label className="mono-label muted" htmlFor="intake-budget" style={{ display: "block", marginBottom: 8 }}>
              Initial Budget Estimate
            </label>
            <div className="input-group">
              {/* the backend contract is budget_usd, so the currency is fixed rather than a dead control */}
              <span className="mono-data muted" style={{ padding: "0 12px" }}>
                USD
              </span>
              <span className="divider" />
              <input
                id="intake-budget"
                className="input"
                inputMode="numeric"
                placeholder="0"
                value={budgetFmt}
                onChange={(e) => setBudget(e.target.value.replace(/[^0-9]/g, ""))}
              />
            </div>
            <p className="mono-data muted" style={{ marginTop: 10 }}>
              Sets casting caps, venue picks and territory reach.
            </p>
          </Panel>

          <Panel className="panel--pad">
            <span className="mono-label muted" style={{ display: "block", marginBottom: 8 }}>
              Production Window
            </span>
            <div className="input-group" style={{ padding: 2 }}>
              <input
                className="input"
                type="date"
                value={start}
                aria-label="First shoot day"
                onChange={(e) => setStart(e.target.value)}
              />
              <span className="sep">–</span>
              <input
                className="input"
                type="date"
                value={wrap}
                aria-label="Wrap day"
                onChange={(e) => setWrap(e.target.value)}
              />
            </div>
            <p className="mono-data muted" style={{ marginTop: 10 }}>
              {windowLine}
            </p>
          </Panel>
        </div>

        {/* Notes + action — span 12 */}
        <div className="span-12 stack">
          <Panel className="panel--pad">
            <label className="mono-label muted" htmlFor="intake-notes" style={{ display: "block", marginBottom: 8 }}>
              Director's Notes / Special Requirements
            </label>
            <textarea
              id="intake-notes"
              className="textarea"
              rows={4}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Enter key details regarding casting preferences, specific location needs, or complex VFX sequences…"
            />
          </Panel>

          {error && (
            <div className="banner" data-tone="warn" role="status">
              <Icon name="warning" />
              <span>{error}</span>
            </div>
          )}

          <div className="form-actions">
            <button
              type="button"
              className="btn btn--primary btn--lg"
              onClick={startPreProduction}
              disabled={!fileName || busy || !canEdit}
              title={
                !canEdit
                  ? "Your role on this production is read-only"
                  : fileName
                  ? undefined
                  : "Attach a screenplay first"
              }
            >
              <Icon
                name={busy ? "progress_activity" : "play_circle"}
                size={20}
                className={busy ? "spin" : undefined}
              />
              <span>{busy ? "Reading script…" : "Start Agent Orchestration"}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
