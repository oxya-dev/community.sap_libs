#!/usr/bin/python
# -*- coding: utf-8 -*-

# Copyright: (c) 2026, Melvin Malagowski <mmalagowski@gmail.com>
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#     http://www.apache.org/licenses/LICENSE-2.0
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = r'''
---
module: sap_system_state
short_description: Start or stop a full SAP system idempotently via sapcontrol SOAP API
version_added: "1.0.0"
description:
  - Start or stop all instances of a SAP system idempotently using the sapcontrol SOAP API.
  - Connects to the sapstartsrv identified by C(sysnr) and issues C(StartSystem) or C(StopSystem).
  - Compatible with any SAP system managed by SAPControl, including SAP NetWeaver and SAP HANA.
  - Uses local Unix socket or HTTP depending on the provided parameters.
options:
  state:
    description:
      - Target state for the SAP instance.
    required: true
    choices: [ started, stopped ]
    type: str
  sysnr:
    description:
      - SAP instance number (e.g. "01").
    required: true
    type: str
  wait:
    description:
      - Whether to wait for the instance to reach the target state.
    type: bool
    default: true
  wait_timeout:
    description:
      - Timeout in seconds to wait for the target state.
    type: int
    default: 600
  poll_interval:
    description:
      - Interval in seconds between status checks.
    type: int
    default: 5
  post_startup_delay:
    description:
      - Seconds to monitor stability after all instances reach GREEN.
      - If any instance regresses during this window, the module fails.
    type: int
    default: 15
  hostname:
    description:
      - Hostname of the sapstartsrv.
    type: str
    default: localhost
  port:
    description:
      - The port number of the sapstartsrv.
      - If provided, the module will always use HTTP connection instead of local socket.
    required: false
    type: int
  username:
    description:
      - Username (if not using local socket).
    type: str
    required: false
  password:
    description:
      - Password (if not using local socket).
    type: str
    required: false
    no_log: true
requirements:
  - suds-community
notes:
    - Supports C(check_mode). In check mode, no action is performed but the
      module reports whether a change would be made based on the current state.
author:
  - Malagowski Melvin (@MelvinM-coder)
'''

EXAMPLES = r'''
- name: Start SAP instance 01 (local socket)
  community.sap_libs.sap_system_state:
    sysnr: "01"
    state: started
  become: true

- name: Stop SAP instance 01 (local socket)
  community.sap_libs.sap_system_state:
    sysnr: "01"
    state: stopped
    wait_timeout: 600
  become: true

- name: Start SAP instance 01 with authentication
  community.sap_libs.sap_system_state:
    sysnr: "01"
    state: started
    username: hdbadm
    password: secret

- name: Stop SAP instance 01 with authentication
  community.sap_libs.sap_system_state:
    sysnr: "01"
    state: stopped
    username: hdbadm
    password: secret
    wait_timeout: 600

- name: Start SAP instance 01 with custom port
  community.sap_libs.sap_system_state:
    hostname: 192.168.8.15
    sysnr: "01"
    state: started
    port: 50113
'''


RETURN = r'''
changed:
  description: true if an action was performed
  type: bool
  returned: always
msg:
  description: Result message
  type: str
  returned: always
state:
  description:
    - Final state of the local instance identified by C(sysnr) (GREEN, YELLOW, GRAY, RED).
    - Derived from the locally managed processes (C(GetProcessList)), not from the
      system-wide instance list, so it stays accurate even if other instances
      (e.g. the message server) are stopped at the same time.
  type: str
  returned: always
instances:
  description:
    - Best-effort list of all SAP system instances and their statuses, as reported by
      C(GetSystemInstanceList).
    - This is informational only. It depends on the SAP message server being reachable
      and can be stale or empty (e.g. right after the message server itself is
      stopped); it is never used to determine whether the target state was reached.
  type: list
  elements: dict
  returned: always
'''

import time

from ansible.module_utils.basic import AnsibleModule, missing_required_lib
from ..module_utils.sapstartsrv_client import (
    HAS_SUDS_LIBRARY,
    SUDS_LIBRARY_IMPORT_ERROR,
    TransportError,
    WebFault,
    call_function,
    connection,
    recursive_dict,
)

# sapcontrol dispstatus constants
DISPSTATUS_GREEN = "SAPControl-GREEN"
DISPSTATUS_YELLOW = "SAPControl-YELLOW"
DISPSTATUS_RED = "SAPControl-RED"
DISPSTATUS_GRAY = "SAPControl-GRAY"

# SAP fault messages meaning the instance is already in the desired state
ALREADY_FAULTS = (
    "already started",
    "already stopped",
)


STATE_RANK = {
    DISPSTATUS_GRAY: 0,
    DISPSTATUS_YELLOW: 1,
    DISPSTATUS_GREEN: 2,
    DISPSTATUS_RED: 3,
}


def _get_soap_items(client, function_name):
    """Call a read-only sapcontrol function and return its <item> elements
    as a list of plain dicts, regardless of how many items were returned.

    suds does not wrap single-occurrence repeating elements into a list:
    when sapstartsrv returns exactly one <item> (which regularly happens
    for GetProcessList on instances with a single monitored process, e.g.
    an ERS), the raw SOAP result exposes a single object (sometimes even a
    bare suds Text/string) instead of a list. Blindly treating that as a
    list of items later breaks with errors such as:
        'Text' object has no attribute 'get'
    This normalizes the result upfront so callers always get a list.
    """
    result = call_function(client, function_name)
    if result is None:
        return []

    raw_items = getattr(result, 'item', None)
    if raw_items is None:
        return []
    if not isinstance(raw_items, list):
        raw_items = [raw_items]

    items = []
    for raw_item in raw_items:
        if hasattr(raw_item, '__keylist__'):
            items.append(recursive_dict(raw_item))
        elif isinstance(raw_item, dict):
            items.append(raw_item)
        # else: not a structured item (e.g. a bare Text/str value) -
        # nothing meaningful to report on, skip it rather than crash.
    return items


def get_instance_list(client):
    """Call GetSystemInstanceList and return all instances of the SAP system.

    NOTE: this is a *system-wide* view, aggregated by the connected
    sapstartsrv via the SAP message server. It is only used for
    best-effort, informational reporting: once the message server /
    ASCS instance itself is stopped (which happens as a side effect of
    a system-wide StopSystem call), other instances can no longer
    refresh this aggregated view and may keep serving a stale snapshot
    indefinitely. Readiness/regression decisions must never depend on
    this call — see get_process_list()/compute_local_state() instead.
    """
    return _get_soap_items(client, "GetSystemInstanceList")


def get_instance_list_safe(client, module=None):
    """Best-effort GetSystemInstanceList, for informational reporting only.

    Only swallows the failure modes we actually expect to see once the
    message server / another instance becomes unreachable (a SOAP fault
    from sapstartsrv, an HTTP/transport-level failure, or an OS-level
    connection error). Anything else (e.g. a programming error in
    recursive_dict()) is left to propagate so it isn't silently hidden.
    """
    try:
        return get_instance_list(client)
    except (WebFault, TransportError, OSError) as e:
        if module is not None:
            module.warn(
                "Could not refresh the system-wide instance list (informational "
                "only, does not affect readiness detection): {0}".format(e)
            )
        return []


def get_process_list(client):
    """Call GetProcessList and return the local processes of this instance.

    Unlike GetSystemInstanceList, this call only reports on the
    processes managed locally by the connected sapstartsrv and does not
    depend on the SAP message server being reachable. This makes it the
    correct source of truth for waiting on/regression-checking *this*
    instance's own state.
    """
    return _get_soap_items(client, "GetProcessList")


def compute_overall_state(instances):
    """
    Derive the overall instance state from GetSystemInstanceList output.
    """
    if not instances:
        return DISPSTATUS_GRAY

    statuses = set(p.get("dispstatus", DISPSTATUS_GRAY) for p in instances)

    if DISPSTATUS_RED in statuses:
        return DISPSTATUS_RED
    if DISPSTATUS_YELLOW in statuses:
        return DISPSTATUS_YELLOW
    if statuses == {DISPSTATUS_GREEN}:
        return DISPSTATUS_GREEN
    if statuses == {DISPSTATUS_GRAY}:
        return DISPSTATUS_GRAY
    return DISPSTATUS_YELLOW


def compute_local_state(processes):
    """
    Derive this instance's own state from GetProcessList output.

    Same ranking rules as compute_overall_state(), but applied to the
    locally managed processes only, so it stays accurate regardless of
    the reachability of the SAP message server / other instances.
    """
    return compute_overall_state(processes)


def wait_for_green(client, timeout, poll_interval, post_startup_delay, module=None):
    """
    Wait for this instance's local processes to reach GREEN, then monitor
    stability.

    Readiness/regression is decided from GetProcessList (local, does not
    depend on the message server). GetSystemInstanceList is only fetched
    best-effort for informational reporting.
    """
    previous_statuses = {}  # process name -> most recent dispstatus seen

    # wait until all local processes are GREEN
    deadline = time.time() + timeout
    while time.time() < deadline:
        processes = get_process_list(client)
        state = compute_local_state(processes)
        instances = get_instance_list_safe(client, module=module)

        # Regression detection
        for proc in processes:
            process_key = proc.get('name')
            current_status = proc.get('dispstatus', DISPSTATUS_GRAY)
            previous_status = previous_statuses.get(process_key, DISPSTATUS_GRAY)
            if STATE_RANK.get(current_status, 0) > STATE_RANK.get(previous_status, 0):
                previous_statuses[process_key] = current_status
            elif STATE_RANK.get(current_status, 0) < STATE_RANK.get(previous_status, 0):
                return state, instances, {
                    'instance': proc,
                    'from_state': previous_status,
                    'to_state': current_status,
                }

        if state == DISPSTATUS_RED:
            return state, instances, None

        if state == DISPSTATUS_GREEN:
            break   # All local processes GREEN — enter stability window

        time.sleep(poll_interval)
    else:
        # Timeout reached without all local processes turning GREEN
        return None, [], None

    # stability window — confirm GREEN holds for post_startup_delay seconds
    stability_deadline = time.time() + post_startup_delay
    while time.time() < stability_deadline:
        processes = get_process_list(client)
        state = compute_local_state(processes)

        if state != DISPSTATUS_GREEN:
            return state, get_instance_list_safe(client, module=module), None

        time.sleep(poll_interval)

    return (
        compute_local_state(get_process_list(client)),
        get_instance_list_safe(client, module=module),
        None,
    )


def wait_for_gray(client, timeout, poll_interval, module=None):
    """
    Wait until this instance's local processes all reach GRAY.

    Readiness is decided from GetProcessList (local, does not depend on
    the message server). GetSystemInstanceList is only fetched
    best-effort for informational reporting.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        processes = get_process_list(client)
        state = compute_local_state(processes)

        if state == DISPSTATUS_GRAY:
            return state, get_instance_list_safe(client, module=module)

        time.sleep(poll_interval)
    return None, []


def main():
    module = AnsibleModule(
        argument_spec=dict(
            state=dict(type='str', required=True, choices=['started', 'stopped']),
            sysnr=dict(type='str', required=True),
            port=dict(type='int', required=False),
            hostname=dict(type='str', default='localhost'),
            username=dict(type='str', required=False),
            password=dict(type='str', no_log=True, required=False),
            wait=dict(type='bool', default=True),
            wait_timeout=dict(type='int', default=600),
            poll_interval=dict(type='int', default=5),
            post_startup_delay=dict(type='int', default=15),
        ),
        supports_check_mode=True,
    )

    if not HAS_SUDS_LIBRARY:
        module.fail_json(
            msg=missing_required_lib('suds'),
            exception=SUDS_LIBRARY_IMPORT_ERROR)

    params = module.params
    desired_state = params['state']
    sysnr = params['sysnr']
    port = params['port']
    hostname = params['hostname']
    username = params['username']
    password = params['password']
    wait = params['wait']
    wait_timeout = params['wait_timeout']
    poll_interval = params['poll_interval']
    post_startup_delay = params['post_startup_delay']

    # Use local Unix socket when: hostname=localhost, no credentials, no explicit port
    is_socket = (
        hostname == 'localhost'
        and username is None
        and password is None
        and port is None
    )

    # Resolve default HTTP port from sysnr when not using local socket
    if port is None and not is_socket:
        port = "5{0}13".format(str(sysnr).zfill(2))

    try:
        client = connection("sapcontrol", hostname, port, username, password,
                            sysnr=sysnr, is_socket=is_socket)
        processes = get_process_list(client)
    except Exception as e:
        module.fail_json(msg="Failed to get process list: {0}".format(str(e)))

    current_state = compute_local_state(processes)
    instances = get_instance_list_safe(client, module=module)

    result = dict(
        changed=False,
        msg='',
        state=current_state,
        instances=instances,
    )

    # Idempotency
    if desired_state == 'started' and current_state == DISPSTATUS_GREEN:
        result['msg'] = "SAP instance {0} is already GREEN (started).".format(sysnr)
        module.exit_json(**result)

    if desired_state == 'stopped' and current_state == DISPSTATUS_GRAY:
        result['msg'] = "SAP instance {0} is already GRAY (stopped).".format(sysnr)
        module.exit_json(**result)

    # Check mode
    if module.check_mode:
        target_state = DISPSTATUS_GREEN if desired_state == 'started' else DISPSTATUS_GRAY
        result['changed'] = True
        action_verb = 'start' if desired_state == 'started' else 'stop'
        result['msg'] = "Would {0} SAP instance {1} (current state: {2}).".format(
            action_verb, sysnr, current_state
        )
        result['diff'] = dict(
            before="state: {0}\n".format(current_state),
            after="state: {0}\n".format(target_state),
        )
        module.exit_json(**result)

    # Execute start or stop action on the full system via the connected instance
    action_skipped = False
    try:
        if desired_state == 'started':
            call_function(client, "StartSystem", dict(waittimeout=wait_timeout, options=0))
        else:  # stopped
            call_function(client, "StopSystem", dict(waittimeout=wait_timeout, softtimeout=0))
    except Exception as e:
        err_lower = str(e).lower()
        if any(fault in err_lower for fault in ALREADY_FAULTS):
            action_skipped = True
        else:
            result['msg'] = "Failed to execute '{0}': {1}".format(desired_state, str(e))
            module.fail_json(**result)

    result['changed'] = not action_skipped

    if wait:
        if desired_state == 'started':
            final_state, final_instances, regression = wait_for_green(
                client, wait_timeout, poll_interval, post_startup_delay, module=module
            )
            if regression is not None:
                result['state'] = final_state
                result['instances'] = final_instances
                result['msg'] = (
                    "Regression detected on SAP instance {0} process {1}: {2} -> {3}."
                    .format(
                        sysnr,
                        regression['instance'].get('name'),
                        regression['from_state'],
                        regression['to_state'],
                    )
                )
                module.fail_json(**result)
        else:
            final_state, final_instances = wait_for_gray(
                client, wait_timeout, poll_interval, module=module
            )

        if final_state is None:
            result['msg'] = (
                "Timeout ({0}s) waiting for SAP instance {1} to reach '{2}'."
                .format(wait_timeout, sysnr, desired_state)
            )
            module.fail_json(**result)

        result['state'] = final_state
        result['instances'] = final_instances

        if final_state == DISPSTATUS_RED:
            result['msg'] = (
                "SAP instance {0} reached RED state after '{1}' action."
                .format(sysnr, desired_state)
            )
            module.fail_json(**result)

    result['msg'] = "SAP instance {0} successfully {1}.".format(sysnr, desired_state)
    module.exit_json(**result)


if __name__ == '__main__':
    main()
