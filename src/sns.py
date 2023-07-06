import json
from typing import Any

import config
from config import get_logger
from dateutil.parser import parse as parse_date

logger = get_logger()

def event_to_sns_message(event: dict, source_file: str, account_id_from_event: str | None) -> dict[str, Any]:
    event_name = event["eventName"]
    error_code = event.get("errorCode")
    error_message = event.get("errorMessage")
    request_parameters = event.get("requestParameters")
    response_elements = event.get("responseElements")
    additional_details = event.get("additionalEventData")
    event_time = parse_date(event["eventTime"])
    event_id = event.get("eventID", "N/A")
    actor = event["userIdentity"]["arn"] if "arn" in event["userIdentity"] else event["userIdentity"]
    title = f"{actor} called {event_name}"
    account_id = "N/A"
    if account_id_from_event:
        account_id = account_id_from_event

    if error_code is not None:
        title = f"{title} but failed due to {error_code}"

    message = {
        "title": title,
        "error_message": error_message,
        "request_parameters": request_parameters,
        "response_elements": response_elements,
        "additional_details": additional_details,
        "account_id": account_id,
        "event_time": str(event_time),
        "event_id": event_id,
        "actor": actor,
        "source_file": source_file,
    }

    return message


def send_message_to_sns(
    event: dict,
    source_file: str,
    account_id: str | None,
    cfg: config.Config,
    sns_client # noqa: ANN001
)-> None:
    if default_topic_arn := cfg.default_sns_topic_arn:
        logger.info("Sending message to SNS.")
        message = json.dumps(event_to_sns_message(event, source_file, account_id))

        logger.debug(f"SNS Message: {message}")
        if account_id:
            topic_arn = next(
                (item["sns_topic_arn"] for item in cfg.sns_configuration if account_id in item["accounts"]),
                default_topic_arn
            )
        else:
            topic_arn = default_topic_arn
        logger.debug(f"Topic ARN: {topic_arn}")
        return sns_client.publish(
            TopicArn = topic_arn,
            Message = message,
        )
