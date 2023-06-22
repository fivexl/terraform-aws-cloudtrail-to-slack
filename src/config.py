from typing import List, Dict
import os
import json
from rules import default_rules
import logging
from datetime import datetime


class Config:
    def __init__(self): # noqa: ANN101 ANN204
        self.default_hook_url: str = self.read_env_variable_or_die("HOOK_URL")
        self.rules_separator: str = os.environ.get("RULES_SEPARATOR", ",")
        self.user_rules: List[str] = self.parse_rules_from_string(os.environ.get("RULES"), self.rules_separator) # noqa: E501
        self.ignore_rules: List[str] = self.parse_rules_from_string(os.environ.get("IGNORE_RULES"), self.rules_separator) # noqa: E501
        self.use_default_rules: bool = os.environ.get("USE_DEFAULT_RULES") # type: ignore # noqa: PGH003
        self.events_to_track: str | None = os.environ.get("EVENTS_TO_TRACK")
        self.configuration: str | None = os.environ.get("CONFIGURATION")
        self.configuration_as_json: List[Dict]  = json.loads(self.configuration) if self.configuration else []
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
    def read_env_variable_or_die(var_name: str) -> str:
        var_value = os.environ.get(var_name)
        if var_value is None:
            raise Exception(f"Environment variable {var_name} is not set")
        return var_value

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
    root_logger.handlers = []
    root_logger.setLevel(log_level)

    logger = logging.getLogger(name)
    handler = logging.StreamHandler()
    formatter = JsonFormatter()
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(log_level)

    return logger
