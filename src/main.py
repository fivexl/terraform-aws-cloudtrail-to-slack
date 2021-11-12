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

import json
import gzip
import sys
import os
import http.client
import boto3
import urllib
from datetime import datetime

from rules import default_rules


# Slack web hook example
# https://hooks.slack.com/services/XXXXXXX/XXXXXXX/XXXXXXXXXX
def post_slack_message(hook_url, message):
    print(f'Sending message: {json.dumps(message)}')
    headers = {'Content-type': 'application/json'}
    connection = http.client.HTTPSConnection('hooks.slack.com')
    connection.request('POST',
                       hook_url.replace('https://hooks.slack.com', ''),
                       json.dumps(message),
                       headers)
    response = connection.getresponse()
    print('Response: {}, message: {}'.format(response.status, response.read().decode()))
    return response.status


def read_env_variable_or_die(env_var_name):
    value = os.environ.get(env_var_name, '')
    if value == '':
        message = f'Required env variable {env_var_name} is not defined or set to empty string'
        raise EnvironmentError(message)
    return value


def get_cloudtrail_log_records(event):
    # Get all the files from S3 so we can process them
    records = []

    s3 = boto3.client('s3')
    for record in event['Records']:
        # In case if we get something unexpected
        if 's3' not in record:
            raise AssertionError(f'recieved record does not contain s3 section: {record}')
        bucket = record['s3']['bucket']['name']
        key = urllib.parse.unquote_plus(record['s3']['object']['key'], encoding='utf-8')
        # Do not process digest files
        if 'Digest' in key:
            continue
        try:
            response = s3.get_object(Bucket=bucket, Key=key)
            with gzip.GzipFile(fileobj=response["Body"]) as gzipfile:
                content = gzipfile.read()
            content_as_json = json.loads(content.decode('utf8'))
            records.append(
                {
                    'key': key,
                    'events': content_as_json['Records'],
                    'eventName': record['eventName']
                }
            )
        except Exception as e:
            print(e)
            print(f'Error getting object {key} from bucket {bucket}')
            raise e
    return records


def get_account_id_from_event(event):
    return event['userIdentity']['accountId'] if 'accountId' in event['userIdentity'] else ''


def get_hook_url_for_account(event, configuration, default_hook_url):
    accoun_id = get_account_id_from_event(event)
    hook_url = [cfg['slack_hook_url'] for cfg in configuration if accoun_id in cfg['accounts']]
    if len(hook_url) > 0:
        return hook_url[0]
    return default_hook_url


def lambda_handler(event, context):

    default_hook_url = read_env_variable_or_die('HOOK_URL')
    user_rules = os.environ.get('RULES', None)
    ignore_rules = os.environ.get('IGNORE_RULES', "").split(",")
    use_default_rules = os.environ.get('USE_DEFAULT_RULES', None)
    events_to_track = os.environ.get('EVENTS_TO_TRACK', None)
    configuration = os.environ.get('CONFIGURATION', None)
    configuration_as_json = json.loads(configuration) if configuration else []
    rules = []
    if use_default_rules:
        rules += default_rules
    if user_rules:
        rules_list = user_rules.split(",")
        rules += rules_list
    if events_to_track:
        events_list = events_to_track.replace(" ", "").split(",")
        rules.append(f'"eventName" in event and event["eventName"] in {json.dumps(events_list)}')
    if not rules:
        raise Exception('Have no rules to apply!!! '
                        + 'Check configuration - add some rules or enable default rules')
    print(f'Going to use the following rules to match events:\n{rules}\nand those two ignore:\n{ignore_rules}')

    records = get_cloudtrail_log_records(event)
    for record in records:
        if 's3:ObjectRemoved' in record['eventName']:
            # TODO: Handle deletion
            continue
        for log_event in record['events']:
            hook_url = get_hook_url_for_account(log_event, configuration_as_json, default_hook_url)
            handle_event(log_event, record['key'], rules, ignore_rules, hook_url)

    return 200


# Filter out events
def should_message_be_processed(event, rules, ignore_rules):
    flat_event = flatten_json(event)
    user = event['userIdentity']
    event_name = event['eventName']
    try:
        for rule in ignore_rules:
            if eval(rule, {}, {'event': flat_event}) is True:
                print(f'Event "{flat_event}"" matched ignore rule:\n{rule}')
                return False # do not process event
        for rule in rules:
            if eval(rule, {}, {'event': flat_event}) is True:
                print(f'Event "{flat_event}"" matched rule:\n{rule}')
                return True # do send notification about event
    except Exception:
        print(f'Event parsing failed: {sys.exc_info()[0]}. '
            + 'Rule: {rule}\nEvent:\n {event}\nFlat event:\n {flat_event}')
        raise
    print(f'did not match any rules: event {event_name} called by {user}')
    return False


# Handle events
def handle_event(event, source_file, rules, ignore_rules, hook_url):
    if should_message_be_processed(event, rules, ignore_rules) is not True:
        return
    # log full event if it is AccessDenied
    if ('errorCode' in event and 'AccessDenied' in event['errorCode']):
        event_as_string = json.dumps(event, indent=4)
        print(f'errorCode == AccessDenied; log full event: {event_as_string}')
    message = event_to_slack_message(event, source_file)
    response = post_slack_message(hook_url, message)
    if response != 200:
        raise Exception('Failed to send message to Slack!')


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
    hook_url = read_env_variable_or_die('HOOK_URL')
    with open('./test/events.json') as f:
        data = json.load(f)
    for event in data:
        handle_event(event, 'file_name', default_rules, hook_url)
