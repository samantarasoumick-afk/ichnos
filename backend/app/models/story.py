import uuid

from datetime import datetime

from sqlalchemy import Column
from sqlalchemy import DateTime
from sqlalchemy import ForeignKey
from sqlalchemy import Integer
from sqlalchemy import JSON
from sqlalchemy import String
from sqlalchemy import Text

from app.db.database import Base


class Story(Base):
    """
    A user-authored guided tour, the "stitch your own story" companion
    to the two hand-written scenarios in frontend/src/lib/tourScenarios.ts.
    Shares the exact same shape (title/problem/solution_summary + an
    ordered sequence of steps) so the frontend's existing
    TourContext/TourStepper playback machinery can run a Story exactly
    like it runs a built-in TourScenario, once converted to that shape -
    see TourContext.tsx's dynamic-scenario handling.

    Deliberately org-scoped rather than global: "shareable across orgs"
    means a story is *portable* (its steps resolve datasets by
    schema_name/table_name at play-time, same as the built-in
    scenarios - see StoryStep below), not that one physical row is
    visible to every organization. Anyone can export/re-author a story
    in another org; each org's copy is still its own row.
    """

    __tablename__ = "stories"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    organization_id = Column(
        String(36),
        ForeignKey("organizations.id"),
        nullable=False
    )

    title = Column(String, nullable=False)

    # Mirrors TourScenario.problem/solutionSummary - optional narrative
    # bookends around the step-by-step walkthrough. Nullable because a
    # quickly-recorded internal story may skip straight to steps.
    problem = Column(Text, nullable=True)
    solution_summary = Column(Text, nullable=True)

    created_by_user_id = Column(
        String(36),
        ForeignKey("users.id"),
        nullable=True
    )
    created_by_email = Column(String, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )


class StoryStep(Base):
    """
    One step of a Story - mirrors TourStep/TourStepTarget in
    tourScenarios.ts field-for-field:
      - path            -> TourStepTarget.path
      - dataset_schema_name/dataset_table_name -> TourStepTarget.dataset
      - tab             -> TourStepTarget.tab
      - query_params    -> TourStepTarget.query (stored as JSON since
                            it's an arbitrary string->string map, e.g.
                            {"q": "customer"} for a prefilled search or
                            Ask'Fe' question)

    dataset_schema_name/dataset_table_name (not a raw dataset_id FK) is
    the deliberate choice that makes a story portable across orgs: the
    same resolve-by-name lookup TourContext already does for the two
    built-in scenarios (GET /api/datasets, matched by schema+name) works
    unchanged here, and gracefully reports "couldn't find this step's
    dataset" if the org playing it back doesn't have a same-named
    dataset - no separate provisioning path needed for custom stories.
    """

    __tablename__ = "story_steps"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4())
    )

    story_id = Column(
        String(36),
        ForeignKey("stories.id"),
        nullable=False
    )

    order_index = Column(Integer, nullable=False)

    title = Column(String, nullable=False)
    narrative = Column(Text, nullable=False)

    path = Column(String, nullable=False)

    dataset_schema_name = Column(String, nullable=True)
    dataset_table_name = Column(String, nullable=True)

    tab = Column(String, nullable=True)
    query_params = Column(JSON, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow)
