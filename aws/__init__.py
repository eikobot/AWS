"""
Abstracts the management of AWS resources,
such IAM credentials, IAM roles, VPCs, VMs and EKS clusters.
"""
import asyncio

import asyncssh
from eikobot.core.errors import EikoDeployError, EikoPluginError
from eikobot.core.handlers import CRUDHandler, Handler, HandlerContext
from eikobot.core.helpers import EikoBaseModel
from eikobot.core.lib.std import HostModel
from eikobot.core.plugin import eiko_plugin

from . import api


class IAMRoleModel(EikoBaseModel):
    """
    An IAM role in AWS.
    """

    __eiko_resource__ = "IAMRole"

    name: str
    permissions: list[str]


class IAMRoleHandler(CRUDHandler):
    """
    An IAM role in AWS.
    """

    __eiko_resource__ = "IAMRole"

    async def read(self, ctx: HandlerContext[IAMRoleModel]) -> None:
        pass

    async def create(self, ctx: HandlerContext[IAMRoleModel]) -> None:
        pass


class EC2KeyPairModel(EikoBaseModel):
    """
    Represents a keypair used for ssh in EC2 instances.
    While officially these are region bound,
    this model can be used to deploy to different regions as needed.
    """

    __eiko_resource__ = "EC2KeyPair"

    name: str
    public_key: str

    # We only check once per region
    _regions: list[str] = []

    def enforce(self, region: str, ctx: HandlerContext, dry_run: bool = False) -> None:
        """
        Makes sure the key pair exists in the given region,
        and updates the public key or tags if needed.
        """
        if region in self._regions:
            return

        keys = api.get_key_pairs(region)
        prev_key = keys.get(self.name)
        if prev_key is None:
            ctx.debug("Creating EC2KeyPair.")
            api.import_key_pair(
                self.name,
                self.public_key.encode("utf-8"),
                region,
                dry_run,
                tags={"eikobot-managed": "yes"},
            )

        # split to remove OpenSSH annotations
        elif prev_key.public_key.split()[1] != self.public_key.split()[1]:
            ctx.debug("Updating EC2KeyPair.")
            api.delete_key_pair(region, prev_key.key_pair_id)
            api.import_key_pair(
                self.name,
                self.public_key.encode("utf-8"),
                region,
                dry_run,
                tags={"eikobot-managed": "yes"},
            )

        self._regions.append(region)


@eiko_plugin()
def validate_image(region: str, image_name: str) -> str:
    """
    Checks if the given image is available.
    """
    image = api.get_ec2_image(region, image_name)
    if image is None:
        raise EikoPluginError(f"No such image '{image_name}' in region '{region}'.")

    return image_name


@eiko_plugin()
def validate_instance_type(region: str, instance_type: str) -> str:
    """
    Checks if the given instance type is available.
    """
    instance_types = api.get_ec2_instance_types(region)
    if instance_type not in instance_types:
        raise EikoPluginError(
            f"Instance type '{instance_type}' is not available in region '{region}'."
        )

    return instance_type


@eiko_plugin()
def get_default_username(
    image_name: str, instance_name: str, username: str = ""
) -> str:
    """
    Checks if the given image is available.
    """
    if username != "":
        return username

    if "amazon" in image_name:
        return "ec2-user"

    if "debian" in image_name:
        return "admin"

    if "ubuntu" in image_name:
        return "ubuntu"

    raise EikoPluginError(
        f"No default username available for image '{image_name}'. "
        f"Please add a username to the EC2Instance '{instance_name}'."
    )


class EC2InstanceModel(EikoBaseModel):
    """
    Standard representation of an EC2 instance.
    """

    __eiko_resource__ = "EC2Instance"

    name: str
    region: str
    key_pair: EC2KeyPairModel
    image_name: str
    instance_type: str
    _test_ssh: bool = False


class EC2InstanceHandler(CRUDHandler):
    """
    Deploys an EC2 instance and the key pair if required.
    """

    __eiko_resource__ = "EC2Instance"

    async def create(self, ctx: HandlerContext[EC2InstanceModel]) -> None:
        image = api.get_ec2_image(ctx.resource.region, ctx.resource.image_name)
        if image is None:
            raise EikoDeployError(
                f"Couldn't find image '{ctx.resource.image_name}' in region '{ctx.resource.region}'."
            )
        instance_id = api.create_ec2_instance(
            ctx.resource.name,
            ctx.resource.region,
            ctx.resource.key_pair.name,
            image.image_id,
            ctx.resource.instance_type,
            ctx.task_id,
        )
        await api.wait_for_instance(ctx.resource.region, instance_id, ctx)

        instance = api.get_ec2_instance(ctx.resource.region, instance_id)
        ctx.promises["public_ip"].set(instance.public_ip_address, ctx)

        ctx.deployed = True

    async def read(self, ctx: HandlerContext[EC2InstanceModel]) -> None:
        ctx.resource.key_pair.enforce(ctx.resource.region, ctx)
        instance_id = api.get_instance_id(ctx.resource.region, ctx.task_id)
        if instance_id is None:
            return

        instance = api.get_ec2_instance(ctx.resource.region, instance_id)
        ctx.promises["public_ip"].set(instance.public_ip_address, ctx)
        await self._wait_for_ssh(instance.public_ip_address, ctx)

        ctx.deployed = True

    async def _wait_for_ssh(
        self, host: str, ctx: HandlerContext[EC2InstanceModel]
    ) -> None:
        if ctx.resource._test_ssh:  # pylint: disable=protected-access
            for i in range(6):
                ctx.debug("Waiting for EC2 instance to come online.")
                if await self._ready_to_connect(host):
                    break
                if i == 6:
                    raise EikoDeployError("Failed to ssh to host.")

    async def _ready_to_connect(self, host: str) -> bool:
        try:
            async with asyncssh.connect(host) as connection:
                await connection.run("echo eikobot", timeout=10)
        except asyncssh.HostKeyNotVerifiable:
            return True
        except asyncssh.TimeoutError:
            return False
        except asyncssh.PermissionDenied:
            return True

        return False


class EC2InstanceHostModel(EikoBaseModel):
    """
    Standard representation of an EC2 instance.
    """

    __eiko_resource__ = "EC2InstanceHost"

    _instance: EC2InstanceModel
    host: HostModel
