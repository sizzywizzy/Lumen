"""API endpoints for Phases V & VI (launch). Mounted under /api/launch.

  POST /api/launch/run/{project_id}           Phase V + VI on the stored state (background)
  GET  /api/launch/poster/{project_id}        the production's poster and whether one is painting
  POST /api/launch/poster/{project_id}        paint a new poster in another style (producer/owner)
  GET  /api/launch/poster/{project_id}/image  the poster image itself
"""
import base64

from fastapi import APIRouter, Depends, HTTPException, Response

from core.auth.deps import require_member, require_producer
from core.auth.models import Membership
from domains.launch import posters
from domains.pipeline import jobs
from services import poster_store, supabase_client

router = APIRouter(prefix="/api/launch", tags=["launch"])

# The page asks for the image as ?v=<poster_id>, so a cached copy is never stale.
# The offline sketch is SVG: the response allows no scripts and no sniffing,
# though the sketch holds neither text nor script.
_IMAGE_HEADERS = {
    "Cache-Control": "private, max-age=86400",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'",
    "X-Content-Type-Options": "nosniff",
}
_IMAGE_TYPES = ("image/png", "image/jpeg", "image/webp", "image/svg+xml")


def _launch_summary(state) -> dict:
    return {
        "audience_report": state.audience_report.model_dump(),
        "marketing_assets": [a.model_dump() for a in state.marketing_assets],
    }


@router.post("/run/{project_id}", status_code=202)
def run_launch(project_id: str, membership: Membership = Depends(require_producer)):
    """Run Phase V (audience sim) + Phase VI (marketing) on the stored state, in
    the background. Poll /api/pipeline/status for progress."""
    if supabase_client.load_state(project_id) is None:
        raise HTTPException(404, f"No state for {project_id}. POST /api/pipeline/init first.")
    try:
        return jobs.start(project_id, "launch", started_by=membership.user_id, summary=_launch_summary)
    except jobs.PipelineBusy:
        raise HTTPException(409, "Lumen is already working on this production. Wait for that run to finish.") from None


@router.get("/poster/{project_id}")
def get_poster(project_id: str, _member=Depends(require_member)):
    """The production's poster, and whether a new one is painting."""
    return posters.status(project_id)


@router.post("/poster/{project_id}", status_code=202)
def new_poster(project_id: str, membership: Membership = Depends(require_producer)):
    """Paint a new poster in a different random style; poll GET for progress."""
    if supabase_client.load_state(project_id) is None:
        raise HTTPException(404, f"No state for {project_id}. Drop in a script first.")
    try:
        posters.start(project_id, membership.user_id)
    except posters.PosterBusy:
        raise HTTPException(409, "A poster is already being painted for this production.") from None
    return posters.status(project_id)


@router.get("/poster/{project_id}/image")
def poster_image(project_id: str, _member=Depends(require_member)):
    record = poster_store.get(project_id, with_image=True)
    if not record or record.get("image_mime") not in _IMAGE_TYPES:
        raise HTTPException(404, "This production has no poster yet.")
    return Response(base64.b64decode(record["image_base64"]), media_type=record["image_mime"], headers=_IMAGE_HEADERS)
