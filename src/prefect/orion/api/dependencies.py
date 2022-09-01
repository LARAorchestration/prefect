"""
Utilities for injecting FastAPI dependencies.
"""
import logging
from typing import AsyncGenerator

from fastapi import Body, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from prefect.orion.database.dependencies import provide_database_interface
from prefect.orion.database.interface import OrionDBInterface
from prefect.orion.utilities.server import response_scoped_dependency
from prefect.settings import PREFECT_ORION_API_DEFAULT_LIMIT


@response_scoped_dependency
async def get_raw_session(
    db: OrionDBInterface = Depends(provide_database_interface),
) -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency-injected database session that handles opening and closing the
    session, but does not perform any transaction management like commits or
    rollbacks. This means users can use this dependency for a "commit-as-you-go"
    style.

    Unless explicit transaction control is required, users should prefer the
    `get_session` dependency which automatically begins, commits, or rolls back
    a transaction.
    """
    session = await db.session()
    async with session:
        yield session


@response_scoped_dependency
async def get_session(
    raw_session: AsyncSession = Depends(get_raw_session),
) -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency-injected database session.

    The context manager will automatically handle commits, rollbacks, and
    closing the connection. It can not be used for explicit commits, however. To
    manually commit a session, use the `get_raw_session` dependency.

    A `response_scoped_dependency` is used to ensure this session is closed
    before the response is returned to a client.
    """
    async with raw_session.begin():
        yield raw_session


class EnforceMinimumAPIVersion:
    """
    FastAPI Dependency used to check compatibility between the version of the api
    and a given request.

    Looks for the header 'X-PREFECT-API-VERSION' in the request and compares it
    to the api's version. Rejects requests that are lower than the minimum version.
    """

    def __init__(self, minimum_api_version: str, logger: logging.Logger):
        self.minimum_api_version = minimum_api_version
        versions = [int(v) for v in minimum_api_version.split(".")]
        self.api_major = versions[0]
        self.api_minor = versions[1]
        self.api_patch = versions[2]
        self.logger = logger

    async def __call__(
        self,
        x_prefect_api_version: str = Header(None),
    ):
        request_version = x_prefect_api_version

        # if no version header, assume latest and continue
        if not request_version:
            return

        # parse version
        try:
            major, minor, patch = [int(v) for v in request_version.split(".")]
        except ValueError:
            await self._notify_of_invalid_value(request_version)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Invalid X-PREFECT-API-VERSION header format."
                    f"Expected header in format 'x.y.z' but received {request_version}"
                ),
            )

        if (major, minor, patch) < (self.api_major, self.api_minor, self.api_patch):
            await self._notify_of_outdated_version(request_version)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"The request specified API version {request_version} but this "
                    f"server requires version {self.minimum_api_version} or higher."
                ),
            )

    async def _notify_of_invalid_value(self, request_version: str):
        self.logger.error(
            f"Invalid X-PREFECT-API-VERSION header format: '{request_version}'"
        )

    async def _notify_of_outdated_version(self, request_version: str):
        self.logger.error(
            f"X-PREFECT-API-VERSION header specifies version '{request_version}' "
            f"but minimum allowed version is '{self.minimum_api_version}'"
        )


def LimitBody() -> Depends:
    """
    A `fastapi.Depends` factory for pulling a `limit: int` parameter from the
    request body while determing the default from the current settings.
    """

    def get_limit(
        limit: int = Body(
            None,
            description="Defaults to PREFECT_ORION_API_DEFAULT_LIMIT if not provided.",
        )
    ):
        default_limit = PREFECT_ORION_API_DEFAULT_LIMIT.value()
        limit = limit if limit is not None else default_limit
        if not limit >= 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Invalid limit: must be greater than or equal to 0.",
            )
        if limit > default_limit:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Invalid limit: must be less than or equal to {default_limit}.",
            )
        return limit

    return Depends(get_limit)
