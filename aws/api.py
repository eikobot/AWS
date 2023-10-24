"""
Abstracted boto3 functionality to make it easier to use.
While this code could be used by others to easily create things
it is very much oriented at being an abstraction that mostly
serves the eikobot aws module.
"""
import asyncio
import datetime
import os
from typing import TYPE_CHECKING

import boto3
from eikobot.core import logger
from eikobot.core.handlers import HandlerContext
from pydantic import BaseModel

if TYPE_CHECKING:
    from mypy_boto3_ec2 import EC2Client, EC2ServiceResource
    from mypy_boto3_ec2.service_resource import Instance, SecurityGroup
    from mypy_boto3_ec2.type_defs import TagTypeDef


AWS_ACCESS_KEY = os.environ.get("AWS_ACCESS_KEY")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")


class AWSCache:
    """
    Allows for easy creation and automatic caching of Boto resources.
    """

    _ec2_clients: dict[str, "EC2Client"] = {}
    _ec2_instance_mappings: dict[str, dict[str, str]] = {}
    _ec2_resources: dict[str, "EC2ServiceResource"] = {}
    ec2_instance_types: dict[str, list[str]] = {}

    @classmethod
    def get_ec2_client(cls, region: str) -> "EC2Client":
        """
        Retrieves a cached client or creates and caches it.
        """
        client = cls._ec2_clients.get(region)
        if client is None:
            if AWS_ACCESS_KEY is not None:
                if AWS_SECRET_ACCESS_KEY is None:
                    raise ValueError(
                        "If 'AWS_ACCESS_KEY' is set, 'AWS_SECRET_ACCESS_KEY' also needs to be set."
                    )
                client = boto3.client(
                    "ec2",
                    region_name=region,
                    aws_access_key_id=AWS_ACCESS_KEY,
                    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                )
            else:
                client = boto3.client("ec2", region_name=region)
            cls._ec2_clients[region] = client

        return client

    @classmethod
    def get_ec2_resource(cls, region: str) -> "EC2ServiceResource":
        """
        Retrieves a cached client or creates and caches it.
        """
        resource = cls._ec2_resources.get(region)
        if resource is None:
            if AWS_ACCESS_KEY is not None:
                if AWS_SECRET_ACCESS_KEY is None:
                    raise ValueError(
                        "If 'AWS_ACCESS_KEY' is set, 'AWS_SECRET_ACCESS_KEY' also needs to be set."
                    )
                resource = boto3.resource(
                    "ec2",
                    region_name=region,
                    aws_access_key_id=AWS_ACCESS_KEY,
                    aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
                )
            else:
                resource = boto3.resource("ec2", region_name=region)
            cls._ec2_resources[region] = resource

        return resource

    @classmethod
    def get_ec2_instance_id(cls, region: str, name: str) -> str | None:
        """
        Gets an id by name.
        """
        region_cache = cls._ec2_instance_mappings.get(region)
        if region_cache is not None:
            return region_cache.get(name)

        cls._ec2_instance_mappings[region] = {}
        return None

    @classmethod
    def add_ec2_instance_id(cls, region: str, name: str, instance_id: str) -> None:
        """
        Add an id.
        """
        region_cache = cls._ec2_instance_mappings.get(region)
        if region_cache is None:
            region_cache = {}
            cls._ec2_instance_mappings[region] = region_cache

        region_cache[name] = instance_id


def import_key_pair(
    key_name: str,
    public_key: bytes,
    region: str,
    dry_run: bool = False,
    tags: dict[str, str] | None = None,
) -> None:
    """
    Import a key pair to a specific region.
    """
    _tags: list["TagTypeDef"] = []
    if tags is not None:
        for key, value in tags.items():
            _tags.append({"Key": key, "Value": value})

    client = AWSCache.get_ec2_client(region)
    client.import_key_pair(
        DryRun=dry_run,
        KeyName=key_name,
        PublicKeyMaterial=public_key,
        TagSpecifications=[
            {
                "ResourceType": "key-pair",
                "Tags": _tags,
            }
        ],
    )


class EC2KeyPair(BaseModel):
    """
    Result of querying the AWS api for key pairs
    """

    key_pair_id: str
    fingerprint: str
    name: str
    type: str
    public_key: str
    create_time: datetime.datetime


def get_key_pairs(region: str) -> dict[str, EC2KeyPair]:
    """
    Returns all ssh keys in a given region.
    """
    logger.debug("[AWS] Getting EC2 key pairs.")
    client = AWSCache.get_ec2_client(region)
    raw_key_pairs = client.describe_key_pairs(IncludePublicKey=True)["KeyPairs"]
    keys: dict[str, EC2KeyPair] = {}
    for raw_pair in raw_key_pairs:
        keys[raw_pair["KeyName"]] = EC2KeyPair(
            key_pair_id=raw_pair["KeyPairId"],
            fingerprint=raw_pair["KeyFingerprint"],
            name=raw_pair["KeyName"],
            type=raw_pair["KeyType"],
            public_key=raw_pair["PublicKey"],
            create_time=raw_pair["CreateTime"],
        )

    return keys


def delete_key_pair(region: str, key_pair_id: str) -> None:
    client = AWSCache.get_ec2_client(region)
    client.delete_key_pair(KeyPairId=key_pair_id)


class EC2Image(BaseModel):
    """
    Object representation of an EC2 AMI image
    """

    image_id: str
    architecture: str
    imageType: str
    platform: str | None
    state: str


def get_ec2_image(region: str, image_name: str) -> EC2Image | None:
    """
    Gets all images that are available to the user in the given region.
    """
    logger.debug(f"[AWS] Looking up image '{image_name}' in region '{region}'.")
    client = AWSCache.get_ec2_client(region)
    try:
        image = client.describe_images(
            Filters=[
                {
                    "Name": "name",
                    "Values": [image_name],
                }
            ]
        )["Images"][0]
        return EC2Image(
            image_id=image["ImageId"],
            architecture=image["Architecture"],
            imageType=image["ImageType"],
            platform=image.get("Platform"),
            state=image["State"],
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
        logger.warning(
            f"[AWS] Failed to retrieve image '{image_name}' in region '{region}'. "
            f"[{e}]"
        )
        return None


def get_ec2_instance_types(region: str) -> list[str]:
    """
    Lists all available instance type
    """
    prev = AWSCache.ec2_instance_types.get(region)
    if prev is not None:
        return prev

    logger.debug(f"[AWS] Looking up available instance types in region '{region}'.")
    client = AWSCache.get_ec2_client(region)
    instance_types: list[str] = []
    response = client.describe_instance_types()
    while "NextToken" in response:
        for instance_type in response["InstanceTypes"]:
            instance_types.append(instance_type["InstanceType"])

        response = client.describe_instance_types(NextToken=response["NextToken"])

    AWSCache.ec2_instance_types[region] = instance_types
    return instance_types


def get_instance_id(region: str, task_id: str) -> str | None:
    """
    Looks up the id, given the instance name and region.
    """
    cached_id = AWSCache.get_ec2_instance_id(region, task_id)
    if cached_id is not None:
        return cached_id

    resource = AWSCache.get_ec2_resource(region)
    instances = list(
        resource.instances.filter(
            Filters=[{"Name": "tag:EikobotID", "Values": [task_id]}]
        )
    )

    if not instances:
        return None

    if len(instances) == 1:
        return instances[0].id

    raise ValueError(
        "Somehow multiple machines were given the same Eikobot id. "
        "Unable to resolve."
    )


def get_ec2_instance(region: str, instance_id: str) -> "Instance":
    ec2 = AWSCache.get_ec2_resource(region)
    return ec2.Instance(instance_id)


def create_ec2_instance(
    name: str,
    region: str,
    key_pair: str,
    image_id: str,
    instance_type: str,
    task_id: str,
    tags: dict[str, str] | None = None,
) -> str:
    """
    Creates a running instance on EC2.
    """
    logger.debug(f"[AWS] Creating instance '{name}', with EikobotID '{task_id}'.")
    _tags: list["TagTypeDef"] = []
    _tags.append({"Key": "Name", "Value": name})
    _tags.append({"Key": "EikobotID", "Value": task_id})

    if tags is not None:
        for key, value in tags.items():
            _tags.append({"Key": key, "Value": value})

    client = AWSCache.get_ec2_client(region)
    return client.run_instances(
        ImageId=image_id,
        MinCount=1,
        MaxCount=1,
        InstanceType=instance_type,  # type: ignore
        KeyName=key_pair,
        TagSpecifications=[
            {
                "ResourceType": "instance",
                "Tags": _tags,
            }
        ],
    )["Instances"][0]["InstanceId"]


async def wait_for_instance(region: str, instance_id: str, ctx: HandlerContext) -> None:
    """
    asynchronously blocks until the EC2 machine is in a running state.
    """
    ec2 = AWSCache.get_ec2_resource(region)
    while True:
        instance = list(ec2.instances.filter(InstanceIds=[instance_id]))[0]
        if instance.state["Name"] == "running":
            break
        ctx.debug("Waiting for EC2 instance to come online.")
        await asyncio.sleep(10)


def create_security_group(
    region: str, name: str, description: str, vpc_id: str
) -> "SecurityGroup":
    """
    Creates a security group for a given VPC.
    """
    ec2 = AWSCache.get_ec2_resource(region)
    return ec2.create_security_group(
        GroupName=name, Description=description, VpcId=vpc_id
    )
