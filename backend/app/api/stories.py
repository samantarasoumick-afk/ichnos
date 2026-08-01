from fastapi import APIRouter
from fastapi import Depends
from fastapi import HTTPException

from sqlalchemy.orm import Session

from app.db.session import get_db

from app.models.story import Story
from app.models.story import StoryStep
from app.models.user import User

from app.schemas.story import StoryCreate
from app.schemas.story import StoryResponse
from app.schemas.story import StorySummary

from app.auth.dependencies import get_current_user
from app.auth.dependencies import require_role
from app.services.audit_service import log_audit_event


router = APIRouter(
    prefix="/api/stories",
    tags=["stories"]
)


def _step_count(db: Session, story_id: str) -> int:

    return (
        db.query(StoryStep)
        .filter(StoryStep.story_id == story_id)
        .count()
    )


def _to_summary(db: Session, story: Story) -> StorySummary:

    return StorySummary(
        id=story.id,
        title=story.title,
        problem=story.problem,
        solution_summary=story.solution_summary,
        step_count=_step_count(db, story.id),
        created_by_email=story.created_by_email,
        created_at=story.created_at,
    )


def _to_response(db: Session, story: Story) -> StoryResponse:

    steps = (
        db.query(StoryStep)
        .filter(StoryStep.story_id == story.id)
        .order_by(StoryStep.order_index)
        .all()
    )

    return StoryResponse(
        id=story.id,
        title=story.title,
        problem=story.problem,
        solution_summary=story.solution_summary,
        created_by_email=story.created_by_email,
        created_at=story.created_at,
        updated_at=story.updated_at,
        steps=steps,
    )


def _get_story_or_404(story_id: str, db: Session, current_user: User) -> Story:

    story = (
        db.query(Story)
        .filter(
            Story.id == story_id,
            Story.organization_id == current_user.organization_id
        )
        .first()
    )

    if not story:
        raise HTTPException(status_code=404, detail="Story not found")

    return story


@router.get(
    "",
    response_model=list[StorySummary]
)
@router.get(
    "/",
    response_model=list[StorySummary]
)
def list_stories(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Every user-authored story in the org, newest first - merged into
    TourContext's `scenarios` list alongside the two built-in
    TOUR_SCENARIOS on the frontend, so a picked-up story plays back
    through the exact same stepper.
    """

    stories = (
        db.query(Story)
        .filter(Story.organization_id == current_user.organization_id)
        .order_by(Story.created_at.desc())
        .all()
    )

    return [_to_summary(db, story) for story in stories]


@router.get(
    "/{story_id}",
    response_model=StoryResponse
)
def get_story(
    story_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    story = _get_story_or_404(story_id, db, current_user)
    return _to_response(db, story)


@router.post(
    "",
    response_model=StoryResponse
)
@router.post(
    "/",
    response_model=StoryResponse
)
def create_story(
    payload: StoryCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):
    """
    Saves a story recorded by stepping through the actual product (see
    the frontend's story-recorder flow) - steps arrive already in
    playback order, so order_index is just each step's position in
    the list rather than something the client has to track separately.

    Requires at least one step: a story with nothing to walk through
    isn't a story, and would render as a picker card that goes nowhere.
    """

    if not payload.steps:
        raise HTTPException(status_code=400, detail="A story needs at least one step.")

    story = Story(
        title=payload.title,
        problem=payload.problem,
        solution_summary=payload.solution_summary,
        organization_id=current_user.organization_id,
        created_by_user_id=current_user.id,
        created_by_email=current_user.email,
    )

    db.add(story)
    db.flush()

    for index, step in enumerate(payload.steps):
        db.add(StoryStep(
            story_id=story.id,
            order_index=index,
            title=step.title,
            narrative=step.narrative,
            path=step.path,
            dataset_schema_name=step.dataset.schema_name if step.dataset else None,
            dataset_table_name=step.dataset.table_name if step.dataset else None,
            tab=step.tab,
            query_params=step.query,
        ))

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="story.create",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="story",
        resource_id=story.id,
        details=f"Created story '{story.title}' with {len(payload.steps)} step(s)",
    )

    db.commit()
    db.refresh(story)

    return _to_response(db, story)


@router.delete("/{story_id}")
def delete_story(
    story_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("admin", "steward"))
):

    story = _get_story_or_404(story_id, db, current_user)

    db.query(StoryStep).filter(StoryStep.story_id == story.id).delete(synchronize_session=False)
    db.delete(story)

    log_audit_event(
        db,
        organization_id=current_user.organization_id,
        action="story.delete",
        actor_user_id=current_user.id,
        actor_email=current_user.email,
        resource_type="story",
        resource_id=story_id,
        details=f"Deleted story '{story.title}'",
    )

    db.commit()

    return {"message": "Story deleted"}
