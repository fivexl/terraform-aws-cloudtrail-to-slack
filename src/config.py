from typing import List, Dict, Union
import os
import json
from rules import default_rules
import logging
from datetime import datetime
from dataclasses import dataclass


@dataclass
class SlackWebhookConfig:
    default_hook_url: str
    configuration: List[Dict]


@dataclass
class SlackAppConfig:
    bot_token: str
    default_channel_id: str
    configuration: List[Dict]

def get_slack_config() -> Union[SlackWebhookConfig, SlackAppConfig]:

    if bot_token := os.environ.get("SLACK_BOT_TOKEN"):

        default_channel_id: str | None = os.environ.get("DEFAULT_SLACK_CHANNEL_ID")
        if not default_channel_id:
            raise Exception("Environment variable DEFAULT_SLACK_CHANNEL_ID must be set.")

        raw_configuration: str | None = os.environ.get("SLACK_APP_CONFIGURATION")
        configuration: List[Dict] = json.loads(raw_configuration) if raw_configuration else []

        return SlackAppConfig(
            bot_token = bot_token,
            default_channel_id = default_channel_id,
            configuration = configuration,
        )

    elif hook_url := os.environ.get("HOOK_URL"):

        raw_configuration: str | None = os.environ.get("CONFIGURATION")
        configuration: List[Dict]  = json.loads(raw_configuration) if raw_configuration else []

        return SlackWebhookConfig(
            default_hook_url = hook_url,
            configuration = configuration,
        )

    else:
        raise Exception("Environment variable HOOK_URL or SLACK_BOT_TOKEN must be set.")


class Config:
    def __init__(self): # noqa: ANN101 ANN204

        self.rule_evaluation_errors_to_slack: bool = os.environ.get("RULE_EVALUATION_ERRORS_TO_SLACK") # type: ignore # noqa: PGH003, E501
        self.rules_separator: str = os.environ.get("RULES_SEPARATOR", ",")
        self.user_rules: List[str] = self.parse_rules_from_string(os.environ.get("RULES"), self.rules_separator) # noqa: E501
        self.ignore_rules: List[str] = self.parse_rules_from_string(os.environ.get("IGNORE_RULES"), self.rules_separator) # noqa: E501
        self.use_default_rules: bool = os.environ.get("USE_DEFAULT_RULES", True) # type: ignore # noqa: PGH003
        self.events_to_track: str | None = os.environ.get("EVENTS_TO_TRACK")

        self.dynamodb_table_name: str | None = os.environ.get("DYNAMODB_TABLE_NAME")
        self.dynamodb_time_to_live: int = int(os.environ.get("DYNAMODB_TIME_TO_LIVE", 900))

        self.rules = []
        if self.use_default_rules:
            self.rules += default_rules
        if self.user_rules:
            self.rules += self.user_rules
        if self.events_to_track:
            events_list = self.events_to_track.replace(" ", "").split(",")
            self.rules.append(f'"eventName" in event and event["eventName"] in {json.dumps(events_list)}')
        if not self.rules:
            raise Exception("Have no rules to apply! Check configuration - add some, or enable default.")

    @staticmethod
    def parse_rules_from_string(rules_as_string: str | None, rules_separator: str) -> List[str]:
        if not rules_as_string:
            return []
        rules_as_list = rules_as_string.split(rules_separator)
        # make sure there are no empty strings in the list
        return [x for x in rules_as_list if x]



class JsonFormatter(logging.Formatter):
    def format(self, record): # noqa: ANN001, ANN201, ANN101
        log_entry = {
            "level": record.levelname,
            "timestamp": datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S.%f"),
        }

        if isinstance(record.msg, dict):
            log_entry.update(record.msg)

        return json.dumps(log_entry)

def get_logger(name: str ="main") -> logging.Logger:
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    log_level = logging.getLevelName(log_level)

    root_logger = logging.getLogger()
    if root_logger.handlers:
        root_logger.handlers = [] # Remove the default lambda logger
    root_logger.setLevel(log_level)

    logger = logging.getLogger(name)
    if not logger.handlers:  # Check if the logger already has handlers
        handler = logging.StreamHandler()
        formatter = JsonFormatter()
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(log_level)

    return logger
