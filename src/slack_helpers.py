import http.client
import json

from config import  get_logger, SlackAppConfig, SlackWebhookConfig
from dateutil.parser import parse as parse_date
from slack_sdk import WebClient
from typing import Any
from slack_sdk.web.slack_response import SlackResponse

logger = get_logger()



def post_message( # noqa: ANN201
        slack_config: SlackAppConfig | SlackWebhookConfig,
        message: dict,
        account_id: str | None = None,
        thread_ts: str | None = None,
) -> None | SlackResponse:

    if isinstance(slack_config, SlackAppConfig):
        if account_id and slack_config.configuration:
            channel_id = next(
                (cfg["slack_channel_id"] for cfg in slack_config.configuration if account_id in cfg["accounts"]), # noqa: E501
                slack_config.default_channel_id
            )
        else:
            channel_id = slack_config.default_channel_id
        return slack_app_post_message(
            message = message,
            channel_id = channel_id,
            slack_config = slack_config,
            thread_ts = thread_ts,
        )

    if isinstance(slack_config, SlackWebhookConfig):
        if account_id and slack_config.configuration:
            hook_url = next(
                (cfg["slack_hook_url"] for cfg in slack_config.configuration if account_id in cfg["accounts"]), # noqa: E501
                slack_config.default_hook_url
            )
        else:
            hook_url = slack_config.default_hook_url
        webhook_post_message(
            message = message,
            hook_url = hook_url,
        )


def slack_app_post_message( # noqa: ANN201
        message: dict,
        channel_id: str,
        slack_config: SlackAppConfig,
        thread_ts: str | None = None
):
    client = WebClient(token=slack_config.bot_token)
    return client.chat_postMessage(
        channel = channel_id,
        blocks = message["blocks"],
        thread_ts = thread_ts,
        text="New message from CloudTrailToSlack"
    )



# Slack web hook example
# https://hooks.slack.com/services/XXXXXXX/XXXXXXX/XXXXXXXXXX
def webhook_post_message(message: dict, hook_url: str) -> int:
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


# Format message
def event_to_slack_message(event:  dict, source_file :str , account_id_from_event: str ) ->  dict[str, Any]:
    event_name = event["eventName"]
    error_code = event.get("errorCode")
    error_message = event.get("errorMessage")
    request_parameters = event.get("requestParameters")
    response_elements = event.get("responseElements")
    additional_details = event.get("additionalEventData")
    event_time = parse_date(event["eventTime"])
    event_id = event.get("eventID", "N/A")
    actor = event.get("userIdentity", {}).get("arn", "Unknown Identity")
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
        "text": f"Account Id: {account_id_from_event}"
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


def message_for_slack_error_notification(
        error: Exception,
        s3_notification_event:  dict
) ->  dict:
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
    message = {"blocks": blocks}

    return message


def message_for_rule_evaluation_error_notification(
        error: Exception,
        object_key: str,
        rule: str
) ->  dict[str, Any]:
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
    message = {"blocks": blocks}

    return message
