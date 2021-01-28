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
import json
import gzip
import os
import http
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


def lambda_handler(event, context):
    hook_url = read_env_variable_or_die('HOOK_URL')
    user_rules = os.environ.get('RULES', None)
    use_default_rules = os.environ.get('USE_DEFAULT_RULES', None)
    rules = default_rules
    if user_rules and not use_default_rules:
        rules = json.loads(user_rules)
    elif user_rules and not use_default_rules:
        rules += json.loads(user_rules)
    print(f'Going to use the following rules:\n{rules}')
    compressed_payload = base64.b64decode(event['awslogs']['data'])
    uncompressed_payload = gzip.decompress(compressed_payload)
    payload = json.loads(uncompressed_payload)

    log_events = payload['logEvents']
    for log_event in log_events:
        handle_event(json.loads(log_event['message']), rules, hook_url)

    return 200


# Filter out events
def should_message_be_processed(event, rules):
    flat_event = flatten_json(event)
    user = event['userIdentity']
    event_name = event['eventName']
    for rule in rules:
        try:
            if eval(rule, {}, {'event': flat_event}) is True:
                print(f'Event "{event_name}"" matched rule:\n{rule}')
                return True
        except KeyError as error:
            print(f'Event that failed with KeyError: {flat_event}')
            raise error
    print(f'did not match any rules: event {event_name} called by {user}')
    return False


# Handle events
def handle_event(event, rules, hook_url):
    if should_message_be_processed(event, rules) is not True:
        return
    # log full event if it is AccessDenied
    if ('errorCode' in event and 'AccessDenied' in event['errorCode']):
        event_as_string = json.dumps(event, indent=4)
        print(f'errorCode == AccessDenied; log full event: {event_as_string}')
    message = event_to_slack_message(event)
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
def event_to_slack_message(event):

    event_name = event['eventName']
    error_code = event['errorCode'] if 'errorCode' in event else None
    error_message = event['errorMessage'] if 'errorMessage' in event else None
    request_parameters = event['requestParameters'] if 'requestParameters' in event else None
    response_elements = event['responseElements'] if 'responseElements' in event else None
    additional_details = event['additionalEventData'] if 'additionalEventData' in event else None
    event_time = datetime.strptime(event['eventTime'], '%Y-%m-%dT%H:%M:%SZ')
    event_id = event['eventID']
    actor = event['userIdentity']['arn'] if 'arn' in event['userIdentity'] else event['userIdentity']
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
                    'text': ':unacceptable: *Login without MFA!* :unacceptable:'
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
        'text': f'Time: {event_time} UTC Id: {event_id}'
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
        handle_event(event, default_rules, hook_url)
