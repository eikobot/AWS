"""
Abstracts the management of AWS resources,
such IAM credentials, IAM roles, VPCs, VMs and EKS clusters.
"""
import boto3
from eikobot.core.helpers import EikoBaseModel
from eikobot.core.handlers import CRUDHandler, HandlerContext

IAM_CLIENT = boto3.client("iam")


class IAMRoleModel(EikoBaseModel):
    """
    An IAM role in AWS.
    """

    __eiko_resource__ = "IAMRole"


class IAMRoleHandler(CRUDHandler):
    """
    An IAM role in AWS.
    """

    __eiko_resource__ = "IAMRole"

    async def read(self, ctx: HandlerContext) -> None:
        pass

    async def create(self, ctx: HandlerContext) -> None:
        pass
