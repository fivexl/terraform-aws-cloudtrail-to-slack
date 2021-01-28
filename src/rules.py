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

# Notify if someone logged in without MFA
default_rules.append('"eventName" in event and event["eventName"] == "ConsoleLogin" and event["additionalEventData.MFAUsed"] != "Yes"')
# Notify if someone is trying to do something they not supposed to be doing
default_rules.append('"errorCode" in event and event["errorCode"] == "UnauthorizedOperation"')
# Notify about all actions done by root
default_rules.append('"userIdentity.type" in event and event["userIdentity.type"] == "Root"')
# Notify only for non read (Starts from Get/Describe/Head/List etc) and
# non data events (like PutObject, GetObject, DeleteObject, Inovoke)
# as well as kms Decrypt
default_rules.append('"eventName" in event and not event["eventName"].startswith(("Get", "Describe", "List", "Head", "DeleteObject", "PutObject", "Invoke", "Decrypt"')
