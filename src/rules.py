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

# Rules in rules list will be applied to the CloudTrail event one by one and if any matches
# then event will be processed and published to Slack
default_rules = list()

# Notify if someone logged in without MFA but skip notification for SSO logins
default_rules.append('event["eventName"] == "ConsoleLogin" ' +
                     'and event.get("additionalEventData.MFAUsed", "") != "Yes" ' +
                     'and "assumed-role/AWSReservedSSO" not in event.get("userIdentity.arn", "")')
# Notify if someone is trying to do something they not supposed to be doing but do not notify
# about not logged in actions since there are a lot of scans for open buckets that generate noise
default_rules.append('event.get("errorCode", "") == "UnauthorizedOperation"')
default_rules.append('event.get("errorCode", "") == "AccessDenied" ' +
                     'and (event.get("userIdentity.accountId", "") != "ANONYMOUS_PRINCIPAL")')
# Notify about all non-read actions done by root
default_rules.append('event.get("userIdentity.type", "") == "Root" ' +
                     'and not event["eventName"].startswith(("Get", "List", "Describe", "Head"))')
default_rules.append('event["eventName"] == "AttachUserPolicy" and "AdministratorAccess" in event.get("requestParameters.policyArn", "")')
