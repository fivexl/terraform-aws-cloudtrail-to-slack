# Licensed to the Apache Software Foundation (ASF) under one
# or more contributor license agreements.  See the NOTICE file
# distributed with this work for additional information
# regarding copyright ownership.  The ASF licenses this file
# to you under the Apache License, Version 2.0 (the
# "License"); you may not use this file except in compliance
# with the License.  You may obtain a copy of the License at

#   http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing,
# software distributed under the License is distributed on an
# "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.  See the License for the
# specific language governing permissions and limitations
# under the License.
import gzip
import http.client
import json

import os
import urllib

from typing import Any, Dict, List, NamedTuple

import boto3
from config import Config, get_logger
from dateutil.parser import parse


cfg = Config()
logger = get_logger()


def lambda_handler(s3_notification_event: Dict[str, List[Any]], _) -> int:  # noqa: ANN001

    try:
        for record in s3_notification_event["Records"]:
            event_name: str = record["eventName"]
            if "Digest" not in record["s3"]["object"]["key"]:
                logger.debug({"s3_notification_event": s3_notification_event})

            if event_name.startswith("ObjectRemoved"):
                handle_removed_object_event(
                    record = record,
                    cfg = cfg,
                )
                continue

            elif event_name.startswith("ObjectCreated"):
                handle_created_object_event(
                    record = record,
                    cfg = cfg,
                )
                continue

    except Exception as e:
        post_slack_message(
            hook_url= cfg.default_hook_url,
            message= message_for_slack_error_notification(e, s3_notification_event)
        )
        logger.exception({"Failed to process event": e})
    return 200


def handle_removed_object_event(
        record: dict,
        cfg: Config,
) -> None:
    logger.info({"s3:ObjectRemoved event": record})
    hook_url = get_hook_url_for_account(record, cfg.configuration_as_json, cfg.default_hook_url)
    message = event_to_slack_message(record, record["s3"]["object"]["key"])
    post_slack_message(hook_url, message)


def handle_created_object_event(
        record: dict,
        cfg: Config,
) -> None:
    cloudtrail_log_record = get_cloudtrail_log_records(record)
    if cloudtrail_log_record:
        for cloudtrail_log_event in cloudtrail_log_record["events"]:
            hook_url = get_hook_url_for_account(
                event = cloudtrail_log_event,
                configuration = cfg.configuration_as_json,
                default_hook_url = cfg.default_hook_url
            )
            handle_event(
                event = cloudtrail_log_event,
                source_file_object_key = cloudtrail_log_record["key"],
                rules = cfg.rules,
                ignore_rules = cfg.ignore_rules,
                hook_url = hook_url
            )


# Slack web hook example
# https://hooks.slack.com/services/XXXXXXX/XXXXXXX/XXXXXXXXXX
def post_slack_message(hook_url: str, message: dict) -> int:
    logger.info({"Sending message to slack": message})
    headers = {"Content-type": "application/json"}
    connection = http.client.HTTPSConnection("hooks.slack.com")
    connection.request("POST",
                       hook_url.replace("https://hooks.slack.com", ""),
                       json.dumps(message),
                       headers)
    response = connection.getresponse()
    logger.info({"Slack response": {"status": response.status, "message": response.read().decode()}})
    return response.status


def get_cloudtrail_log_records(record: Dict) -> Dict | None:
    # Get all the files from S3 so we can process them
    s3 = boto3.client("s3")

    # In case if we get something unexpected
    if "s3" not in record:
        raise AssertionError(f"recieved record does not contain s3 section: {record}")
    bucket = record["s3"]["bucket"]["name"]
    key = urllib.parse.unquote_plus(record["s3"]["object"]["key"], encoding="utf-8") # type: ignore # noqa: PGH003, E501
    # Do not process digest files
    if "Digest" in key:
        return
    try:
        response = s3.get_object(Bucket=bucket, Key=key)
        with gzip.GzipFile(fileobj=response["Body"]) as gzipfile:
            content = gzipfile.read()
        content_as_json = json.loads(content.decode("utf8"))
        cloudtrail_log_record = {
            "key": key,
            "events": content_as_json["Records"],
        }

    except Exception as e:
        logger.exception({"Error getting object": {"key": key, "bucket": bucket, "error": e}})
        raise e
    return cloudtrail_log_record


def get_account_id_from_event(event: dict) -> str:
    return event["userIdentity"]["accountId"] if "accountId" in event["userIdentity"] else ""


def get_hook_url_for_account(
        event: dict,
        configuration: List[Dict],
        default_hook_url: str
) -> str:
    accoun_id = get_account_id_from_event(event)
    hook_url = [cfg["slack_hook_url"] for cfg in configuration if accoun_id in cfg["accounts"]]
    if len(hook_url) > 0:
        return hook_url[0]
    return default_hook_url


class ProcessingResult(NamedTuple):
    should_be_processed: bool
    errors: List[Dict[str, Any]]


def should_message_be_processed(
    event: Dict[str, Any],
    rules: List[str],
    ignore_rules: List[str],
) -> ProcessingResult:
    flat_event = flatten_json(event)
    user = event["userIdentity"]
    event_name = event["eventName"]
    logger.debug({"Rules:": rules, "ignore_rules": ignore_rules})
    logger.debug({"Flattened event": flat_event})

    errors = []
    for ignore_rule in ignore_rules:
        try:
            if eval(ignore_rule, {}, {"event": flat_event}) is True: # noqa: PGH001
                logger.info({"Event matched ignore rule and will not be processed": {"ignore_rule": ignore_rule, "flat_event": flat_event}}) # noqa: E501
                return ProcessingResult(False, errors)
        except Exception as e:
            logger.exception({"Event parsing failed": {"error": e, "ignore_rule": ignore_rule, "flat_event": flat_event}}) # noqa: E501
            errors.append({"error": e, "rule": ignore_rule})

    for rule in rules:
        try:
            if eval(rule, {}, {"event": flat_event}) is True: # noqa: PGH001
                logger.info({"Event matched rule and will be processed": {"rule": rule, "flat_event": flat_event}}) # noqa: E501
                return ProcessingResult(True, errors)
        except Exception as e:
            logger.exception({"Event parsing failed": {"error": e, "rule": rule, "flat_event": flat_event}})
            errors.append({"error": e, "rule": rule})

    logger.info({"Event did not match any rules and will not be processed": {"event": event_name, "user": user}}) # noqa: E501
    return ProcessingResult(False, errors)


def handle_event(
    event: Dict[str, Any],
    source_file_object_key: str,
    rules: List[str],
    ignore_rules: List[str],
    hook_url: str
) -> None:

    result = should_message_be_processed(event, rules, ignore_rules)

    if cfg.rule_evaluation_errors_to_slack:
        for error in result.errors:
            post_slack_message(
                hook_url = get_hook_url_for_account(event, cfg.configuration_as_json, cfg.default_hook_url),
                message = message_for_rule_evaluation_error_notification(
                error = error["error"],
                object_key = source_file_object_key,
                rule = error["rule"],
                )
            )

    if not result.should_be_processed:
        return

    # log full event if it is AccessDenied
    if ("errorCode" in event and "AccessDenied" in event["errorCode"]):
        event_as_string = json.dumps(event, indent=4)
        logger.info({"errorCode": "AccessDenied", "log full event": event_as_string})
    message = event_to_slack_message(event, source_file_object_key)
    response = post_slack_message(hook_url, message)
    if response != 200: # noqa: PLR2004 TODO
        raise Exception("Failed to send message to Slack!")


# Flatten json
def flatten_json(y: dict) -> dict:
    out = {}

    def flatten(x, name=""): # noqa: ANN001, ANN202
        if type(x) is dict:
            for a in x:
                flatten(x[a], name + a + ".")
        elif type(x) is list:
            i = 0
            for a in x:
                flatten(a, name + str(i) + ".")
                i += 1
        else:
            out[name[:-1]] = x

    flatten(y)
    return out


# Format message
def event_to_slack_message(event: Dict, source_file) -> Dict[str, Any]: # noqa: ANN001
    event_name = event["eventName"]
    error_code = event.get("errorCode")
    error_message = event.get("errorMessage")
    request_parameters = event.get("requestParameters")
    response_elements = event.get("responseElements")
    additional_details = event.get("additionalEventData")
    event_time = parse(event["eventTime"])
    event_id = event.get("eventID", "N/A")
    actor = event["userIdentity"]["arn"] if "arn" in event["userIdentity"] else event["userIdentity"]
    account_id = get_account_id_from_event(event)
    title = f"*{actor}* called *{event_name}*"
    if error_code is not None:
        title = f":warning: {title} but failed due to ```{error_code}``` :warning:"
    blocks = []
    contexts = []

    blocks.append(
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": title
            }
        }
    )

    if error_message is not None:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Error message:* ```{error_message}```"
                }
            }
        )

    if event_name == "ConsoleLogin" and event["additionalEventData"]["MFAUsed"] != "Yes":
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": ":warning: *Login without MFA!* :warning:"
                }
            }
        )

    if request_parameters is not None:
        contexts.append({
            "type": "mrkdwn",
            "text": f"*requestParameters:* ```{json.dumps(request_parameters, indent=4)}```"
        })

    if response_elements is not None:
        contexts.append({
            "type": "mrkdwn",
            "text": f"*responseElements:* ```{json.dumps(response_elements, indent=4)}```"
        })

    if additional_details is not None:
        contexts.append({
            "type": "mrkdwn",
            "text": f"*additionalEventData:* ```{json.dumps(additional_details, indent=4)}```"
        })

    contexts.append({
        "type": "mrkdwn",
        "text": f"Time: {event_time} UTC"
    })

    contexts.append({
        "type": "mrkdwn",
        "text": f"Id: {event_id}"
    })

    contexts.append({
        "type": "mrkdwn",
        "text": f"Account Id: {account_id}"
    })

    contexts.append({
        "type": "mrkdwn",
        "text": f"Event location in s3:\n{source_file}"
    })

    blocks.append({
        "type": "context",
        "elements": contexts
    })

    blocks.append({"type": "divider"})

    message = {"blocks": blocks}

    return message


def message_for_slack_error_notification(error: Exception, s3_notification_event: Dict) -> Dict[str, Any]:
    object_keys = [record["s3"]["object"]["key"] for record in s3_notification_event["Records"]]
    if len(object_keys) == 1:
        object_key = object_keys[0]
    else:
        object_key = "\n ".join(object_keys)

    title = ":warning: *Failed to process event:*  :warning:"
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": title
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Error:*"
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"```{error}```"
                }
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Object(s):*"
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"{object_key}"
                }
            ]
        }
    ]
    message = {"attachments": [{"color": "#FF0000", "blocks": blocks}]}

    return message


def message_for_rule_evaluation_error_notification(
        error: Exception,
        object_key: str,
        rule: str
) -> Dict[str, Any]:
    title = ":warning: *Failed to evaluate rule:*  :warning:"
    blocks = [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": title
            }
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"*Rule:* \n```{rule}```"
                }
            ]
        },

        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"*Error:* \n```{error}```"
                }
            ]
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"*Object:* \n{object_key}"
                }
            ]
        }
    ]
    message = {"attachments": [{"color": "#FF0000", "blocks": blocks}]}

    return message


# For local testing
if __name__ == "__main__":
    from rules import default_rules
    hook_url = os.environ.get("HOOK_URL")
    if hook_url is None:
        raise Exception("HOOK_URL is not set!")
    ignore_rules = ["'userIdentity.accountId' in event and event['userIdentity.accountId'] == 'YYYYYYYYYYY'"]
    with open("./tests/test_events.json") as f:
        data = json.load(f)
    for event in data:
        handle_event(event, "file_name", default_rules, ignore_rules, hook_url)
