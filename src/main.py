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
import json
import urllib
from typing import Any, Dict, List, NamedTuple

import boto3
from config import Config, SlackAppConfig, SlackWebhookConfig, get_logger, get_slack_config
from dynamodb import get_thread_ts_from_dynamodb, put_event_to_dynamodb
from slack_helpers import (
    event_to_slack_message,
    message_for_rule_evaluation_error_notification,
    message_for_slack_error_notification,
    post_message,
)
from slack_sdk.web.slack_response import SlackResponse
from sns import send_message_to_sns

cfg = Config()
logger = get_logger()
slack_config = get_slack_config()

s3_client = boto3.client("s3")
dynamodb_client = boto3.client("dynamodb")
sns_client = boto3.client("sns")


def lambda_handler(s3_notification_event: Dict[str, List[Any]], _) -> int:  # noqa: ANN001

    try:
        for record in s3_notification_event["Records"]:
            event_name: str = record["eventName"]
            if "Digest" in record["s3"]["object"]["key"]:
                return 200

            if event_name.startswith("ObjectRemoved"):
                handle_removed_object_record(
                    record = record,
                )
                continue

            elif event_name.startswith("ObjectCreated"):
                handle_created_object_record(
                    record = record,
                    cfg = cfg,
                )
                continue

    except Exception as e:
        post_message(
            message = message_for_slack_error_notification(e, s3_notification_event),
            account_id = None,
            slack_config = slack_config,
        )
        logger.exception({"Failed to process event": e})
    return 200


def handle_removed_object_record(
        record: dict,
) -> None:
    logger.info({"s3:ObjectRemoved event": record})
    account_id = record["userIdentity"]["accountId"] if "accountId" in record["userIdentity"] else ""
    message = event_to_slack_message(
        event = record,
        source_file = record["s3"]["object"]["key"],
        account_id_from_event = account_id,
    )
    post_message(message = message, account_id = account_id, slack_config = slack_config)


def handle_created_object_record(
        record: dict,
        cfg: Config,
) -> None:
    logger.debug({"s3_notification_event": record})
    cloudtrail_log_record = get_cloudtrail_log_records(record)
    if cloudtrail_log_record:
        for cloudtrail_log_event in cloudtrail_log_record["events"]:
            handle_event(
                event = cloudtrail_log_event,
                source_file_object_key = cloudtrail_log_record["key"],
                rules = cfg.rules,
                ignore_rules = cfg.ignore_rules
            )


def get_cloudtrail_log_records(record: Dict) -> Dict | None:
    # Get all the files from S3 so we can process them

    # In case if we get something unexpected
    if "s3" not in record:
        raise AssertionError(f"recieved record does not contain s3 section: {record}")
    bucket = record["s3"]["bucket"]["name"]
    key = urllib.parse.unquote_plus(record["s3"]["object"]["key"], encoding="utf-8") # type: ignore # noqa: PGH003, E501
    # Do not process digest files
    try:
        response = s3_client.get_object(Bucket=bucket, Key=key)
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
) -> SlackResponse | None:

    result = should_message_be_processed(event, rules, ignore_rules)
    account_id = event["userIdentity"]["accountId"] if "accountId" in event["userIdentity"] else""
    if cfg.rule_evaluation_errors_to_slack:
        for error in result.errors:
            post_message(
                message = message_for_rule_evaluation_error_notification(
                error = error["error"],
                object_key = source_file_object_key,
                rule = error["rule"],
                ),
                account_id = account_id,
                slack_config = slack_config,
            )

    if not result.should_be_processed:
        return

    # log full event if it is AccessDenied
    if ("errorCode" in event and "AccessDenied" in event["errorCode"]):
        event_as_string = json.dumps(event, indent=4)
        logger.info({"errorCode": "AccessDenied", "log full event": event_as_string})

    message = event_to_slack_message(event, source_file_object_key, account_id)

    send_message_to_sns(
        event = event,
        source_file = source_file_object_key,
        account_id = account_id,
        cfg = cfg,
        sns_client = sns_client,
    )

    if isinstance(slack_config, SlackAppConfig):
        thread_ts = get_thread_ts_from_dynamodb(
            cfg = cfg,
            event = event,
            dynamodb_client=dynamodb_client,
        )
        if thread_ts is not None:
            # If we have a thread_ts, we can post the message to the thread
            logger.info({"Posting message to thread": {"thread_ts": thread_ts}})
            return post_message(
                message = message,
                account_id = account_id,
                thread_ts = thread_ts,
                slack_config = slack_config,
            )
        else:
            # If we don't have a thread_ts, we need to post the message to the channel
            logger.info({"Posting message to channel"})
            slack_response = post_message(
                message = message,
                account_id = account_id,
                slack_config = slack_config
            )
            if slack_response is not None:
                logger.info({"Saving thread_ts to DynamoDB"})
                thread_ts = slack_response.get("ts")
                if thread_ts is not None:
                    put_event_to_dynamodb(
                        cfg = cfg,
                        event = event,
                        thread_ts = thread_ts,
                        dynamodb_client=dynamodb_client,
                    )
    if isinstance(slack_config, SlackWebhookConfig):
        return post_message(
            message = message,
            account_id = account_id,
            slack_config = slack_config,
        )



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

# For local testing
if __name__ == "__main__":
    #Before running this script, set environment variables below
    #On top of this file add region to boto3 clients
    #and remove cfg = Config() slack_config = get_slack_config() from top of this file.
    import os
    os.environ["SLACK_BOT_TOKEN"] = ""
    os.environ["DEFAULT_SLACK_CHANNEL_ID"] = ""
    os.environ["SLACK_APP_CONFIGURATION"] = ""

    os.environ["DYNAMODB_TABLE_NAME"] = ""
    os.environ["DYNAMODB_TIME_TO_LIVE"] = ""

    os.environ["HOOK_URL"] = ""
    os.environ["CONFIGURATION"] = ""

    os.environ["RULE_EVALUATION_ERRORS_TO_SLACK"] = ""
    os.environ["RULES_SEPARATOR"] = ","
    os.environ["RULES"] = ""
    os.environ["IGNORE_RULES"] = ""
    os.environ["USE_DEFAULT_RULES"] = ""
    os.environ["EVENTS_TO_TRACK"] = ""
    os.environ["LOG_LEVEL"] = ""
    os.environ["DEFAULT_SNS_TOPIC_ARN"] = ""
    os.environ["SNS_CONFIGURATION"] = '[{""}]'


    cfg = Config()
    slack_config = get_slack_config()

    with open("./tests/test_events.json") as f:
        data = json.load(f)
    for event in data["test_events"]:
        handle_event(event["event"], "file_name", cfg.rules, cfg.ignore_rules)
