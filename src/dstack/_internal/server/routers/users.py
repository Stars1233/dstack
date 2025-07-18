from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from dstack._internal.core.errors import ResourceNotExistsError
from dstack._internal.core.models.users import User, UserWithCreds
from dstack._internal.server.db import get_session
from dstack._internal.server.models import UserModel
from dstack._internal.server.schemas.users import (
    CreateUserRequest,
    DeleteUsersRequest,
    GetUserRequest,
    RefreshTokenRequest,
    UpdateUserRequest,
)
from dstack._internal.server.security.permissions import Authenticated, GlobalAdmin
from dstack._internal.server.services import users
from dstack._internal.server.utils.routers import (
    CustomORJSONResponse,
    get_base_api_additional_responses,
)

router = APIRouter(
    prefix="/api/users",
    tags=["users"],
    responses=get_base_api_additional_responses(),
)


@router.post("/list", response_model=List[User])
async def list_users(
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
):
    return CustomORJSONResponse(await users.list_users_for_user(session=session, user=user))


@router.post("/get_my_user", response_model=User)
async def get_my_user(
    user: UserModel = Depends(Authenticated()),
):
    return CustomORJSONResponse(users.user_model_to_user(user))


@router.post("/get_user", response_model=UserWithCreds)
async def get_user(
    body: GetUserRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
):
    res = await users.get_user_with_creds_by_name(
        session=session, current_user=user, username=body.username
    )
    if res is None:
        raise ResourceNotExistsError()
    return CustomORJSONResponse(res)


@router.post("/create", response_model=User)
async def create_user(
    body: CreateUserRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(GlobalAdmin()),
):
    res = await users.create_user(
        session=session,
        username=body.username,
        global_role=body.global_role,
        email=body.email,
        active=body.active,
    )
    return CustomORJSONResponse(users.user_model_to_user(res))


@router.post("/update", response_model=User)
async def update_user(
    body: UpdateUserRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(GlobalAdmin()),
):
    res = await users.update_user(
        session=session,
        username=body.username,
        global_role=body.global_role,
        email=body.email,
        active=body.active,
    )
    if res is None:
        raise ResourceNotExistsError()
    return CustomORJSONResponse(users.user_model_to_user(res))


@router.post("/refresh_token", response_model=UserWithCreds)
async def refresh_token(
    body: RefreshTokenRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(Authenticated()),
):
    res = await users.refresh_user_token(session=session, user=user, username=body.username)
    if res is None:
        raise ResourceNotExistsError()
    return CustomORJSONResponse(users.user_model_to_user_with_creds(res))


@router.post("/delete")
async def delete_users(
    body: DeleteUsersRequest,
    session: AsyncSession = Depends(get_session),
    user: UserModel = Depends(GlobalAdmin()),
):
    await users.delete_users(
        session=session,
        user=user,
        usernames=body.users,
    )
