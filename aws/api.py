"""
Abstracted boto3 functionality to make it easier to use.
"""
import datetime
import os
from typing import TYPE_CHECKING

import boto3
from eikobot.core import logger
from pydantic import BaseModel

if TYPE_CHECKING:
    from mypy_boto3_ec2 import EC2Client
    from mypy_boto3_ec2.type_defs import TagTypeDef


AWS_ACCESS_KEY = os.environ.get("AWS_ACCESS_KEY")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")


class BotoCache:
    """
    Allows for easy creation and automatic caching of Boto resources.
    """

    _ec2_clients: dict[str, "EC2Client"] = {}
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

    client = BotoCache.get_ec2_client(region)
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
    client = BotoCache.get_ec2_client(region)
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
    client = BotoCache.get_ec2_client(region)
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
    client = BotoCache.get_ec2_client(region)
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
            f"AWS: Failed to retrieve image '{image_name}' in region '{region}'. "
            f"[{e}]"
        )
        return None


def get_ec2_instance_types(region: str) -> list[str]:
    """
    Lists all available instance type
    """
    prev = BotoCache.ec2_instance_types.get(region)
    if prev is not None:
        return prev

    client = BotoCache.get_ec2_client(region)
    instance_types: list[str] = []
    response = client.describe_instance_types()
    while "NextToken" in response:
        for instance_type in response["InstanceTypes"]:
            instance_types.append(instance_type["InstanceType"])

        response = client.describe_instance_types(NextToken=response["NextToken"])

    BotoCache.ec2_instance_types[region] = instance_types
    return instance_types
