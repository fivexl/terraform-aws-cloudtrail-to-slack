import hashlib
import time

from config import Config, get_logger

logger = get_logger()


def hash_user_identity_and_event_name(event: dict,) -> str | None:

    user_identity = event.get("userIdentity")
    if not user_identity:
        logger.info({"No userIdentity in event": {"event": event}})
        return None

    type = user_identity.get("type", "N/A")
    principalId = user_identity.get("principalId", "N/A")
    arn = user_identity.get("arn", "N/A")
    accountId = user_identity.get("accountId", "N/A")

    na_count = sum(x == "N/A" for x in [type, principalId, arn, accountId])

    # If more than 3 elements are "N/A", return None, cause we can't be shure that we will get a unique hash.
    if na_count >= 3: # noqa: PLR2004
        logger.info({"Not enough information to hash": {"event": event["userIdentity"]}})
        return None
    logger.info({"Hashing user identity and event name"})
    combined = type + principalId + arn + accountId + event["eventName"]
    # Concatenate the user_identity string and event_name


    # Hash the combined string using SHA256
    result = hashlib.sha256(combined.encode())

    # Return the hexadecimal representation of the hash
    logger.debug({"Hash value": result.hexdigest()})
    return result.hexdigest()


def put_event_to_dynamodb(
    event: dict,
    thread_ts: str,
    dynamodb_client, # noqa: ANN001,
    cfg: Config
) -> dict | None:
    hash_value = hash_user_identity_and_event_name(event)
    if not hash_value:
        logger.info({"No hash value returned from hash_user_identity_and_event_name, not putting event to DynamoDB"}) # noqa: E501
        return None

    logger.debug({"Putting event to DynamoDB": {"event": event}})
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
    if int(item["ttl"]["N"]) < int(time.time()):
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
    if not hash_vaule:
        return None
    item = check_dynamodb_for_similar_events(
        hash_value = hash_vaule,
        dynamodb_client = dynamodb_client,
        cfg = cfg
        )
    if item:
        return item["thread_ts"]["S"]
    else:
        return None
