"""
Abstracts the management of AWS resources,
such IAM credentials, IAM roles, VPCs, VMs and EKS clusters.
"""
from eikobot.core.errors import EikoPluginError
from eikobot.core.handlers import CRUDHandler, HandlerContext
from eikobot.core.helpers import EikoBaseModel
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
def validate_image(region: str, image_id: str) -> None:
    """
    Checks if the given image is available.
    """
    image = api.get_ec2_image(region, image_id)
    if image is None:
        raise EikoPluginError(f"No such image '{image_id}' in region '{region}'.")


class EC2InstanceModel(EikoBaseModel):
    """
    Standard representation of an EC2 instance.
    """

    __eiko_resource__ = "EC2Instance"

    name: str
    region: str
    key_pair: EC2KeyPairModel
    image_id: str


class EC2InstanceHandler(CRUDHandler):
    """
    Deploys an EC2 instance and the key pair if required.
    """

    __eiko_resource__ = "EC2Instance"

    async def create(self, ctx: HandlerContext[EC2InstanceModel]) -> None:
        ctx.resource.key_pair.enforce(ctx.resource.region, ctx)
        ctx.deployed = True
