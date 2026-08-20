"""Demo runner — kicks a project through all six phases with mock data.

    python backend/run_demo.py --project PROJ_NEON_NIGHTS --mode indie
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from core.orchestrator.graph import Orchestrator
from core.orchestrator.state import GlobalState
from services import supabase_client


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full CineNode pipeline.")
    parser.add_argument("--project", default="PROJ_NEON_NIGHTS")
    parser.add_argument("--mode", choices=["indie", "enterprise"], default="indie")
    parser.add_argument("--verbose", action="store_true", help="print every A2A envelope")
    args = parser.parse_args()

    state = GlobalState(project_id=args.project, mode=args.mode)
    orchestrator = Orchestrator()

    print(f"🎬 CineNode — {args.project} ({args.mode} mode)\n")
    for node in orchestrator.nodes:
        before = len(state.event_log)
        state = orchestrator.run(state, start=node.key, end=node.key)
        new_events = state.event_log[before:]
        print(f"[{node.key.upper()}] {node.title} — {len(new_events)} A2A messages")
        for envelope in new_events:
            if args.verbose:
                print(f"    {envelope}")
            else:
                arrow = "↩" if envelope.get("in_reply_to") else "→"
                print(f"    {envelope['sender']} {arrow} {envelope['recipient']}: {envelope['intent']}")
        if node.fail_fast and node.fail_fast(state):
            print(f"    ⛔ fail-fast halt: {node.fail_fast(state)}")
            break

    supabase_client.save_state(state)

    print("\n=== FINAL STATE ===")
    print(f"Casting: {state.casting_status} | locked: "
          f"{[c.name for c in state.candidates if c.status == 'LOCKED']}")
    print(f"Disqualified: {[(c.name, c.disqualify_reason) for c in state.candidates if c.status == 'DISQUALIFIED']}")
    print(f"Stripboard: {len(state.schedule.stripboard)} scenes over "
          f"{len({e.date for e in state.schedule.stripboard})} days | daily burn ${state.budget_state.daily_burn:,.0f}")
    print(f"Compliance: {state.compliance_state}")
    print(f"Tomatometer: {state.audience_report.tomatometer}% | audience {state.audience_report.audience_score} "
          f"| weakest scene {state.audience_report.weakest_scene_id}")
    print(f"Assets: {[(a.asset_id, a.status) for a in state.marketing_assets]}")
    print(f"Human escalations: {len(state.human_escalations)}")
    for esc in state.human_escalations:
        print(f"    • {esc.queue_item}: {esc.reason}")
    print(f"\nEvent log: {len(state.event_log)} A2A messages — state saved for {state.project_id}.")


if __name__ == "__main__":
    main()
