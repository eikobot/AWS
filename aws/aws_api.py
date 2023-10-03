"""
Contains wrappers around the AWS api.
Allowing the use of async calls to it.
"""
import asyncio
import json
from datetime import datetime

from eikobot.core.errors import EikoError
from pydantic import BaseModel


class AWSCredential(BaseModel):
    """
    A set of credentials retrieved using the AWS API.
    """

    access_key_id: str
    secret_access_key: str
    session_token: str
    expiration: datetime

    def __repr__(self) -> str:
        _repr = f"AWSCredential(access_key_id: {self.access_key_id}, "
        _repr += f"secret_access_key: ****, session_token: ****, expiration: {self.expiration})"
        return _repr


async def _get_credentials() -> AWSCredential:
    process = (
        await asyncio.subprocess.create_subprocess_shell(  # pylint: disable=no-member
            "aws sts get-session-token",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        raise EikoError(
            f"Failed to get aws token: \n{stdout.decode('utf-8')}\n{stderr.decode('utf-8')}"
        )

    credentials = json.loads(stdout)["Credentials"]
    return AWSCredential(
        access_key_id=credentials["AccessKeyId"],
        secret_access_key=credentials["SecretAccessKey"],
        session_token=credentials["SessionToken"],
        expiration=credentials["Expiration"],
    )
