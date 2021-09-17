import datetime
from typing import List
from uuid import UUID

import pendulum
import sqlalchemy as sa
from fastapi import Body, Depends, HTTPException, Path, Response, status

from prefect.orion import models, schemas
from prefect.orion.api import dependencies, run_history
from prefect.orion.orchestration.rules import OrchestrationResult
from prefect.orion.utilities.server import OrionRouter
from prefect.utilities.logging import get_logger

logger = get_logger("orion.api")

router = OrionRouter(prefix="/flow_runs", tags=["Flow Runs"])


@router.post("/")
async def create_flow_run(
    flow_run: schemas.actions.FlowRunCreate,
    session: sa.orm.Session = Depends(dependencies.get_session),
    response: Response = None,
) -> schemas.core.FlowRun:
    """
    Create a flow run. If a flow run with the same flow_id and
    idempotency key already exists, the existing flow run will be returned.

    If no state is provided, the flow run will be created in a PENDING state.
    """
    if not flow_run.state:
        flow_run.state = schemas.states.Pending()

    now = pendulum.now("UTC")
    model = await models.flow_runs.create_flow_run(session=session, flow_run=flow_run)
    if model.created >= now:
        response.status_code = status.HTTP_201_CREATED
    return model


@router.patch("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def update_flow_run(
    flow_run: schemas.actions.FlowRunUpdate,
    flow_run_id: UUID = Path(..., description="The flow run id", alias="id"),
    session: sa.orm.Session = Depends(dependencies.get_session),
):
    """
    Updates a flow run
    """
    result = await models.flow_runs.update_flow_run(
        session=session, flow_run=flow_run, flow_run_id=flow_run_id
    )
    if not result:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Flow run not found")


# must be defined before `GET /:id`
@router.get("/count")
async def count_flow_runs(
    flows: schemas.filters.FlowFilter = None,
    flow_runs: schemas.filters.FlowRunFilter = None,
    task_runs: schemas.filters.TaskRunFilter = None,
    session: sa.orm.Session = Depends(dependencies.get_session),
) -> int:
    """
    Query for flow runs
    """
    return await models.flow_runs.count_flow_runs(
        session=session,
        flow_filter=flows,
        flow_run_filter=flow_runs,
        task_run_filter=task_runs,
    )


# insert other routes here so they are defined ahead of `GET /:id`
@router.get("/history")
async def flow_run_history(
    history_start: datetime.datetime = Body(
        ..., description="The history's start time."
    ),
    history_end: datetime.datetime = Body(..., description="The history's end time."),
    history_interval: datetime.timedelta = Body(
        ...,
        description="The size of each history interval, in seconds.",
        alias="history_interval_seconds",
    ),
    flows: schemas.filters.FlowFilter = None,
    flow_runs: schemas.filters.FlowRunFilter = None,
    task_runs: schemas.filters.TaskRunFilter = None,
    session: sa.orm.Session = Depends(dependencies.get_session),
) -> List[schemas.responses.HistoryResponse]:
    return await run_history.run_history(
        session=session,
        run_type="flow_run",
        history_start=history_start,
        history_end=history_end,
        history_interval=history_interval,
        flows=flows,
        flow_runs=flow_runs,
        task_runs=task_runs,
    )


@router.get("/{id}")
async def read_flow_run(
    flow_run_id: UUID = Path(..., description="The flow run id", alias="id"),
    session: sa.orm.Session = Depends(dependencies.get_session),
) -> schemas.core.FlowRun:
    """
    Get a flow run by id
    """
    flow_run = await models.flow_runs.read_flow_run(
        session=session, flow_run_id=flow_run_id
    )
    if not flow_run:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="Flow run not found")
    return flow_run


@router.get("/")
async def read_flow_runs(
    sort: schemas.sorting.FlowRunSort = Body(schemas.sorting.FlowRunSort.ID_DESC),
    pagination: schemas.filters.Pagination = Depends(),
    flows: schemas.filters.FlowFilter = None,
    flow_runs: schemas.filters.FlowRunFilter = None,
    task_runs: schemas.filters.TaskRunFilter = None,
    session: sa.orm.Session = Depends(dependencies.get_session),
) -> List[schemas.core.FlowRun]:
    """
    Query for flow runs
    """
    return await models.flow_runs.read_flow_runs(
        session=session,
        flow_filter=flows,
        flow_run_filter=flow_runs,
        task_run_filter=task_runs,
        offset=pagination.offset,
        limit=pagination.limit,
        sort=sort,
    )


@router.delete("/{id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_flow_run(
    flow_run_id: UUID = Path(..., description="The flow run id", alias="id"),
    session: sa.orm.Session = Depends(dependencies.get_session),
):
    """
    Delete a flow run by id
    """
    result = await models.flow_runs.delete_flow_run(
        session=session, flow_run_id=flow_run_id
    )
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Flow run not found"

@router.post("/{id}/set_state")
async def set_flow_run_state(
    flow_run_id: UUID = Path(..., description="The flow run id", alias="id"),
    state: schemas.actions.StateCreate = Body(..., description="The intended state."),
    session: sa.orm.Session = Depends(dependencies.get_session),
    response: Response = None,
) -> OrchestrationResult:
    """Set a flow run state, invoking any orchestration rules."""

    # create the state
    orchestration_result = await models.flow_run_states.orchestrate_flow_run_state(
        session=session,
        flow_run_id=flow_run_id,
        # convert to a full State object
        state=schemas.states.State.parse_obj(state),
    )

    # set the 201 because a new state was created
    if orchestration_result.status == schemas.responses.SetStateStatus.WAIT:
        response.status_code = status.HTTP_200_OK
    elif orchestration_result.status == schemas.responses.SetStateStatus.ABORT:
        response.status_code = status.HTTP_200_OK
    else:
        response.status_code = status.HTTP_201_CREATED

    return orchestration_result
