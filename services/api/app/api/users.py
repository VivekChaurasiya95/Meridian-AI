"""Current-user routes (API.md §6.2)."""

import datetime as dt

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from app.api.deps import CurrentUser, DbSession, RequestId
from app.envelope import ok
from app.schemas import UserUpdate

router = APIRouter(prefix="/api/v1", tags=["user"])


def _serialize(user: CurrentUser) -> dict:
    return {
        "id": str(user.id),
        "display_name": user.display_name,
        "email": user.email,
        "status": user.status,
    }


@router.get("/me")
def get_me(user: CurrentUser, request_id: RequestId) -> JSONResponse:
    return ok(_serialize(user), request_id)


@router.patch("/me")
def update_me(
    payload: UserUpdate, session: DbSession, user: CurrentUser, request_id: RequestId
) -> JSONResponse:
    user.display_name = payload.display_name
    user.updated_at = dt.datetime.now(dt.UTC)
    session.commit()
    session.refresh(user)
    return ok(_serialize(user), request_id)
