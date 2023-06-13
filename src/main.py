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
from datetime import datetime
from typing import Any, Dict, List, Union

import boto3
from errors import ParsingEventError
from rules import default_rules


# Slack web hook example
# https://hooks.slack.com/services/XXXXXXX/XXXXXXX/XXXXXXXXXX
def post_slack_message(hook_url: str, message: dict) -> int:
    print(f"Sending message: {json.dumps(message)}")
    headers = {"Content-type": "application/json"}
    connection = http.client.HTTPSConnection("hooks.slack.com")
    connection.request("POST",
                       hook_url.replace("https://hooks.slack.com", ""),
                       json.dumps(message),
                       headers)
    response = connection.getresponse()
    print("Response: {}, message: {}".format(response.status, response.read().decode()))
    return response.status


def read_env_variable_or_die(env_var_name: str) -> str:
    value = os.environ.get(env_var_name)
    if value is None:
        message = f"Required env variable {env_var_name} is not defined."
        raise EnvironmentError(message)
    return value


def get_cloudtrail_log_records(event: Dict[str, List[Any]]) -> List[Dict[str, Any]]:
    # Get all the files from S3 so we can process them
    records = []

    s3 = boto3.client("s3")
    for record in event["Records"]:
        # In case if we get something unexpected
        if "s3" not in record:
            raise AssertionError(f"recieved record does not contain s3 section: {record}")
        bucket = record["s3"]["bucket"]["name"]
        key = urllib.parse.unquote_plus(record["s3"]["object"]["key"], encoding="utf-8")
        # Do not process digest files
        if "Digest" in key:
            continue
        try:
            response = s3.get_object(Bucket=bucket, Key=key)
            with gzip.GzipFile(fileobj=response["Body"]) as gzipfile:
                content = gzipfile.read()
            content_as_json = json.loads(content.decode("utf8"))
            records.append(
                {
                    "key": key,
                    "events": content_as_json["Records"],
                    "eventName": record["eventName"]
                }
            )
        except Exception as e:
            print(e)
            print(f"Error getting object {key} from bucket {bucket}")
            raise e
    return records


def get_account_id_from_event(event: dict) -> str:
    return event["userIdentity"]["accountId"] if "accountId" in event["userIdentity"] else ""


def get_hook_url_for_account(
        event: dict,
        configuration: List[Dict[str, Union[List[str], str]]],
        default_hook_url: str
) -> str:
    accoun_id = get_account_id_from_event(event)
    hook_url = [cfg["slack_hook_url"] for cfg in configuration if accoun_id in cfg["accounts"]]
    if len(hook_url) > 0:
        return hook_url[0]
    return default_hook_url


def lambda_handler(event: Dict[str, List[Any]], __) -> int: # type: ignore # noqa: ANN001, PGH003
    default_hook_url = read_env_variable_or_die("HOOK_URL")
    rules_separator = os.environ.get("RULES_SEPARATOR", ",")
    user_rules = parse_rules_from_string(os.environ.get("RULES", ""), rules_separator)
    ignore_rules = parse_rules_from_string(os.environ.get("IGNORE_RULES", ""), rules_separator)
    use_default_rules = os.environ.get("USE_DEFAULT_RULES")
    events_to_track = os.environ.get("EVENTS_TO_TRACK")
    configuration = os.environ.get("CONFIGURATION")
    configuration_as_json = json.loads(configuration) if configuration else []
    rules = []
    if use_default_rules:
        rules += default_rules
    if user_rules:
        rules += user_rules
    if events_to_track:
        events_list = events_to_track.replace(" ", "").split(",")
        rules.append(f'"eventName" in event and event["eventName"] in {json.dumps(events_list)}')
    if not rules:
        raise Exception("Have no rules to apply! Check configuration - add some, or enable default.")
    print(f"Match rules:\n{rules}\nIgnore rules:\n{ignore_rules}")

    records = get_cloudtrail_log_records(event)
    for record in records:
        if "s3:ObjectRemoved" in record["eventName"]:
            # TODO: Handle deletion
            continue
        for log_event in record["events"]:
            hook_url = get_hook_url_for_account(log_event, configuration_as_json, default_hook_url)
            handle_event(log_event, record["key"], rules, ignore_rules, hook_url)

    return 200


# Filter out events
def should_message_be_processed(event: Dict, rules: List[str], ignore_rules: List[str]) -> bool:
    flat_event = flatten_json(event)
    user = event["userIdentity"]
    event_name = event["eventName"]
    for rule in ignore_rules:
        try:
            if eval(rule, {}, {"event": flat_event}) is True: # noqa: PGH001
                print("Event matched ignore rule and will not be processed.\n"
                      f"Rule: {rule}\nEvent: {flat_event}")
                return False  # do not process event
        except ParsingEventError as e:
            print(f"Event parsing failed: {e}.\n"
                  f"Rule: {rule}\nEvent: {event}\nFlat event: {flat_event}")
            continue
    for rule in rules:
        try:
            if eval(rule, {}, {"event": flat_event}) is True: # noqa: PGH001
                print(f"Event matched rule and will be processed.\nRule:{rule}\nEvent: {flat_event}")
                return True  # do send notification about event
        except ParsingEventError as e:
            print(f"Event parsing failed: {e}.\n"
                  f"Rule: {rule}\nEvent: {event}\nFlat event: {flat_event}")
            continue
    print(f"did not match any rules: event {event_name} called by {user}")
    return False


# Handle events
def handle_event(
    event: dict,
    source_file, # noqa: ANN001 TODO: type
    rules: List[str],
    ignore_rules: List[str],
    hook_url: str
) -> None:
    if should_message_be_processed(event, rules, ignore_rules) is not True:
        return
    # log full event if it is AccessDenied
    if ("errorCode" in event and "AccessDenied" in event["errorCode"]):
        event_as_string = json.dumps(event, indent=4)
        print(f"errorCode == AccessDenied; log full event: {event_as_string}")
    message = event_to_slack_message(event, source_file)
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


# Parse rules from string
def parse_rules_from_string(rules_as_string: str, rules_separator: str) -> List[str]:
    rules_as_list = rules_as_string.split(rules_separator)
    # make sure there are no empty strings in the list
    return [x for x in rules_as_list if x]


# Format message
def event_to_slack_message(event: Dict, source_file) -> Dict[str, Any]: # noqa: ANN001
    event_name = event["eventName"]
    error_code = event.get("errorCode")
    error_message = event.get("errorMessage")
    request_parameters = event.get("requestParameters")
    response_elements = event.get("responseElements")
    additional_details = event.get("additionalEventData")
    event_time = datetime.strptime(event["eventTime"], "%Y-%m-%dT%H:%M:%SZ")
    event_id = event["eventID"]
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


# For local testing
if __name__ == "__main__":
    hook_url = read_env_variable_or_die("HOOK_URL")
    ignore_rules = ["'userIdentity.accountId' in event and event['userIdentity.accountId'] == 'YYYYYYYYYYY'"]
    with open("./test/events.json") as f:
        data = json.load(f)
    for event in data:
        handle_event(event, "file_name", default_rules, ignore_rules, hook_url)
