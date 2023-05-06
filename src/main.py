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

import base64
import gzip
import http.client
import json
import os
import sys
import boto3
import urllib3
from datetime import datetime

from rules import default_rules


sns = boto3.client('sns')
http_client = urllib3.PoolManager()

### Define function to retrieve values from extension local HTTP server cachce
def retrieve_extension_value(url):
    port = os.environ['PARAMETERS_SECRETS_EXTENSION_HTTP_PORT']
    url = ('http://localhost:' + port + url)
    headers = { "X-Aws-Parameters-Secrets-Token": os.environ.get('AWS_SESSION_TOKEN') }
    response = http_client.request("GET", url, headers=headers)
    response = json.loads(response.data)
    return response

# Slack web hook example
# https://hooks.slack.com/services/XXXXXXX/XXXXXXX/XXXXXXXXXX
def post_slack_message(hook_url, message):
    # print(f'Sending message: {json.dumps(message)}')
    headers = {'Content-type': 'application/json'}
    connection = http.client.HTTPSConnection('hooks.slack.com')
    connection.request('POST',
                       hook_url.replace('https://hooks.slack.com', ''),
                       json.dumps(message),
                       headers)
    response = connection.getresponse()
    # print('Response: {}, message: {}'.format(response.status, response.read().decode()))
    return response.status

def publish_sns(sns_topic, event):
    attributes = {}
    for key, value in event.items():
        if isinstance(value, str):
            attributes[key] = {'DataType': 'String', 'StringValue': str(value)}
    print(attributes)
    try:
        return sns.publish(
            TargetArn=sns_topic,
            Message=json.dumps(event),
            MessageAttributes=attributes
        )['ResponseMetadata']['HTTPStatusCode']
    except Exception as e:
        print(f"Topic {sns_topic}: {e}")
        if "NotFound" in str(e) or "AuthorizationError" in str(e):
            return 200
        return 500

def get_cloudtrail_log_records(event):
    # Get all the files from S3 so we can process them
    records = []
    cw_data = event['awslogs']['data']
    compressed_payload = base64.b64decode(cw_data)
    uncompressed_payload = gzip.decompress(compressed_payload)
    payload = json.loads(uncompressed_payload)

    log_events = payload['logEvents']
    for log_event in log_events:
        records.append(
            {
                'key': payload['logGroup'],
                'accountId': payload['owner'],
                'event': json.loads(log_event['message']),
            }
        )
    return records


def get_account_id_from_event(event):
    return event.get("recipientAccountId", "-no-recipientAccountId-")


def get_hook_url_for_account(event, configuration, default_hook_url):
    account_id = get_account_id_from_event(event)
    hook_url = [cfg['slack_hook_url'] for cfg in configuration if account_id in cfg['accounts']]
    if len(hook_url) > 0:
        return hook_url[0]
    return default_hook_url


def get_sns_topic_for_account(event, sns_pattern, placeholder):
    account_id = get_account_id_from_event(event)
    return sns_pattern.replace(placeholder, account_id)

def lambda_handler(event, context):

    config_ssm_parameter_name = os.environ.get('CONFIG_SSM_PARAMETER_NAME', 'None')
    default_hook_url = os.environ.get('HOOK_URL', None)
    rules_separator = os.environ.get('RULES_SEPARATOR', ',')
    user_rules = parse_rules_from_string(os.environ.get('RULES', ''), rules_separator)
    ignore_rules = parse_rules_from_string(os.environ.get('IGNORE_RULES', ''), rules_separator)
    use_default_rules = os.environ.get('USE_DEFAULT_RULES', None)
    events_to_track = os.environ.get('EVENTS_TO_TRACK', None)
    configuration = retrieve_extension_value(('/systemsmanager/parameters/get/?name=' + config_ssm_parameter_name))['Parameter']['Value']
    sns_pattern = os.environ.get('SNS_PATTERN', '')
    placeholder = os.environ.get('SNS_PATTERN_PLACEHOLDER', '')
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
        raise Exception('Have no rules to apply!!! '
                        + 'Check configuration - add some rules or enable default rules')
    # print(f'Match rules:\n{rules}\nIgnore rules:\n{ignore_rules}')

    records = get_cloudtrail_log_records(event)
    for record in records:
        hook_url = get_hook_url_for_account(record['event'], configuration_as_json, default_hook_url)
        sns_topic = get_sns_topic_for_account(record['event'], sns_pattern, placeholder)
        handle_event(record['event'], record['key'], rules, ignore_rules, hook_url, sns_topic)

    return 200


# Filter out events
def should_message_be_processed(event, rules, ignore_rules):
    flat_event = flatten_json(event)
    flat_event = {k: v for k, v in flat_event.items() if v is not None}
    try:
        for rule in ignore_rules:
            if eval(rule, {}, {'event': flat_event}) is True:
                print('Event matched ignore rule and will not be processed. ' +
                      f'Rule: {rule} Event: {flat_event}')
                return False  # do not process event
        for rule in rules:
            if eval(rule, {}, {'event': flat_event}) is True:
                # print(f'Event matched rule and will be processed.\nRule:{rule}\nEvent: {flat_event}')
                return True  # do send notification about event
    except Exception:
        print(f'Event parsing failed: {sys.exc_info()[0]}. '
              + f'Rule: {rule} Event: {event} Flat event: {flat_event}')
        raise
    # print(f'did not match any rules: event {event_name} called by {user}')
    return False


# Handle events
def handle_event(event, source_file, rules, ignore_rules, hook_url, sns_topic):
    if should_message_be_processed(event, rules, ignore_rules) is not True:
        return
    # log full event if it is AccessDenied
    if ('errorCode' in event and 'AccessDenied' in event['errorCode']):
        event_as_string = json.dumps(event)
        print(f'errorCode == AccessDenied; log full event: {event_as_string}')
    sns_response = publish_sns(sns_topic, event)
    if sns_response != 200:
        raise Exception('Failed to send message to SNS!')

    if hook_url:
        message = event_to_slack_message(event, source_file)
        slack_response = post_slack_message(hook_url, message)
        if slack_response != 200:
            raise Exception('Failed to send message to Slack!')
    else:
        print(f"No hook url found for account {get_account_id_from_event(event)}")


# Flatten json
def flatten_json(y):
    out = {}

    def flatten(x, name=''):
        if type(x) is dict:
            for a in x:
                flatten(x[a], name + a + '.')
        elif type(x) is list:
            i = 0
            for a in x:
                flatten(a, name + str(i) + '.')
                i += 1
        else:
            out[name[:-1]] = x

    flatten(y)
    return out


# Parse rules from string
def parse_rules_from_string(rules_as_string, rules_separator):
    rules_as_list = rules_as_string.split(rules_separator)
    # make sure there are no empty strings in the list
    return [x for x in rules_as_list if x]


# Format message
def event_to_slack_message(event, source_file):

    event_name = event['eventName']
    error_code = event['errorCode'] if 'errorCode' in event else None
    error_message = event['errorMessage'] if 'errorMessage' in event else None
    request_parameters = event['requestParameters'] if 'requestParameters' in event else None
    response_elements = event['responseElements'] if 'responseElements' in event else None
    additional_details = event['additionalEventData'] if 'additionalEventData' in event else None
    event_time = datetime.strptime(event['eventTime'], '%Y-%m-%dT%H:%M:%SZ')
    event_id = event['eventID']
    region = event.get("awsRegion", "-no-region-")
    actor = event['userIdentity']['arn'] if 'arn' in event['userIdentity'] else event['userIdentity']
    account_id = get_account_id_from_event(event)
    title = f'*{actor}* called *{event_name}*'
    if error_code is not None:
        title = f':warning: {title} but failed due to ```{error_code}``` :warning:'
    blocks = list()
    contexts = list()

    blocks.append(
        {
            'type': 'section',
            'text': {
                'type': 'mrkdwn',
                'text': title
            }
        }
    )

    if error_message is not None:
        blocks.append(
            {
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': f'*Error message:* ```{error_message}```'
                }
            }
        )

    if event_name == 'ConsoleLogin' and event['additionalEventData']['MFAUsed'] != 'Yes':
        blocks.append(
            {
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': ':warning: *Login without MFA!* :warning:'
                }
            }
        )

    if request_parameters is not None:
        contexts.append({
            'type': 'mrkdwn',
            'text': f'*requestParameters:* ```{json.dumps(request_parameters, indent=4)}```'
        })

    if response_elements is not None:
        contexts.append({
            'type': 'mrkdwn',
            'text': f'*responseElements:* ```{json.dumps(response_elements, indent=4)}```'
        })

    if additional_details is not None:
        contexts.append({
            'type': 'mrkdwn',
            'text': f'*additionalEventData:* ```{json.dumps(additional_details, indent=4)}```'
        })

    contexts.append({
        'type': 'mrkdwn',
        'text': f'Time: {event_time} UTC'
    })

    contexts.append({
        'type': 'mrkdwn',
        'text': f'Id: {event_id}'
    })

    contexts.append({
        'type': 'mrkdwn',
        'text': f'Account Id: {account_id}'
    })

    contexts.append({
        'type': 'mrkdwn',
        'text': f'awsRegion: {region}'
    })

    contexts.append({
        'type': 'mrkdwn',
        'text': f'Event location in s3:\n{source_file}'
    })

    blocks.append({
        'type': 'context',
        'elements': contexts
    })

    blocks.append({'type': 'divider'})

    message = {'blocks': blocks}

    return message


# For local testing
if __name__ == '__main__':
    os.environ["SNS_PATTERN_PLACEHOLDER"] = "ACCOUNT_ID"
    os.environ["SNS_PATTERN"] = "arn:aws:sns:eu-west-1:ACCOUNT_ID:cloudtrail-notifications"
    os.environ["USE_DEFAULT_RULES"] = "true"
    ignore_rules = ["'userIdentity.accountId' in event and event['userIdentity.accountId'] == 'YYYYYYYYYYY'"]
    with open('./test/events.json') as f:
        json_string = json.dumps({
            "messageType": "DATA_MESSAGE",
            "owner": "942041421337",
            "logGroup": "aws-controltower/CloudTrailLogs",
            "logStream": "942041421337_CloudTrail_eu-west-1_3",
            "subscriptionFilters": [ "foo-bar"],
            "logEvents": [{
                "id": "36735300154870502596213160384635787696492633805025443840",
                "timestamp": 1647267830193,
                "message": json.dumps(json.load(f))
            }]}
        )
        compressed_payload = gzip.compress(bytes(json_string, 'utf-8'))
        encoded_payload = base64.b64encode(compressed_payload)
        data = {
            "awslogs": {
                "data": encoded_payload
            }
        }
    lambda_handler(data, {})
