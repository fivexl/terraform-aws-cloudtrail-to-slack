import hashlib
import time
from datetime import datetime

from config import Config, get_logger

logger = get_logger()


def hash_user_identity_and_event_name(event: dict,) -> str:

    user_identity = event["userIdentity"]
    type = user_identity["type"]
    principalId = user_identity["principalId"]
    arn = user_identity["arn"]
    accountId = user_identity["accountId"]

    combined = type + principalId + arn + accountId + event["eventName"]
    # Concatenate the user_identity string and event_name


    # Hash the combined string using SHA256
    result = hashlib.sha256(combined.encode())

    # Return the hexadecimal representation of the hash
    return result.hexdigest()


def put_event_to_dynamodb(
    event: dict,
    thread_ts: str,
    dynamodb_client, # noqa: ANN001,
    cfg: Config
) -> dict:
    logger.debug({"Putting event to DynamoDB": {"event": event}})
    hash_value = hash_user_identity_and_event_name(event)
    logger.debug({"Hash value": hash_value})
    expire_at = int(time.time()) + cfg.dynamodb_time_to_live

    return dynamodb_client.put_item(
        TableName = cfg.dynamodb_table_name,
        Item={
            "principal_structure_and_action_hash": {"S": hash_value},
            "thread_ts": {"S": thread_ts},
            "ttl": {"N": str(expire_at)},
        }
    )

def check_dynamodb_for_similar_events(
        hash_value: str,
        dynamodb_client, # noqa: ANN001
        cfg: Config
) -> dict | None:
    response = dynamodb_client.get_item(
        TableName = cfg.dynamodb_table_name,
        Key={
            "principal_structure_and_action_hash": {"S": hash_value}
        }
    )
    item = response.get("Item", None)
    if not item:
        logger.info({"No similar event found in DynamoDB"})
        return None
    if int(item["ttl"]["N"]) > int(time.time()):
        # If the item has expired, we treat it as if it doesn't exist
        logger.info({"Found similar event in DynamoDB, but it has expired"})
        return None
    logger.info({"Found similar event in DynamoDB": {"object": item}})
    return item


def get_thread_ts_from_dynamodb(
        cfg: Config,
        event: dict,
        dynamodb_client # noqa: ANN001
) -> str | None:
    hash_vaule = hash_user_identity_and_event_name(event)
    item = check_dynamodb_for_similar_events(
        hash_value = hash_vaule,
        dynamodb_client = dynamodb_client,
        cfg = cfg
        )
    if item:
        return item["thread_ts"]["S"]
    else:
        return None
