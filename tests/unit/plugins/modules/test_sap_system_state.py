#!/usr/bin/env python

# Copyright (c) 2022-2026 The Project Contributors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# For a detailed list of copyright holders and contribution history,
# please refer to the CONTRIBUTORS.md file in the project root.

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import sys
from unittest.mock import patch, MagicMock
from ansible_collections.community.sap_libs.tests.unit.plugins.modules.utils import (
    AnsibleExitJson, ModuleTestCase, set_module_args,
)

sys.modules['suds.client'] = MagicMock()
sys.modules['suds.sudsobject'] = MagicMock()
sys.modules['suds'] = MagicMock()

from ansible_collections.community.sap_libs.plugins.modules import sap_system_state


def make_item(name, dispstatus):
    return {"name": name, "dispstatus": dispstatus}


def make_instance(hostname, instance_nr, dispstatus):
    return {"hostname": hostname, "instanceNr": instance_nr, "dispstatus": dispstatus}


class FakeSudsComplexItem(object):
    """Minimal stand-in for a suds complex-type object (exposes __keylist__,
    like a real <item> element returned by GetProcessList/GetSystemInstanceList).
    """

    def __init__(self, **fields):
        self.__keylist__ = list(fields.keys())
        for key, value in fields.items():
            setattr(self, key, value)


class FakeSudsResult(object):
    """Minimal stand-in for a suds top-level SOAP response object."""

    def __init__(self, item=None):
        if item is not None:
            self.item = item


def fake_recursive_dict(suds_object):
    """Lightweight stand-in for module_utils.recursive_dict(), sufficient
    for flat FakeSudsComplexItem fixtures used in these tests.
    """
    return {key: getattr(suds_object, key) for key in suds_object.__keylist__}


class TestComputeLocalState(ModuleTestCase):

    def test_empty_processes_is_gray(self):
        self.assertEqual(
            sap_system_state.compute_local_state([]), sap_system_state.DISPSTATUS_GRAY
        )

    def test_all_green(self):
        processes = [make_item("msg_server", sap_system_state.DISPSTATUS_GREEN),
                     make_item("disp+work", sap_system_state.DISPSTATUS_GREEN)]
        self.assertEqual(
            sap_system_state.compute_local_state(processes), sap_system_state.DISPSTATUS_GREEN
        )

    def test_all_gray(self):
        processes = [make_item("msg_server", sap_system_state.DISPSTATUS_GRAY),
                     make_item("disp+work", sap_system_state.DISPSTATUS_GRAY)]
        self.assertEqual(
            sap_system_state.compute_local_state(processes), sap_system_state.DISPSTATUS_GRAY
        )

    def test_mixed_is_yellow(self):
        processes = [make_item("msg_server", sap_system_state.DISPSTATUS_GRAY),
                     make_item("disp+work", sap_system_state.DISPSTATUS_GREEN)]
        self.assertEqual(
            sap_system_state.compute_local_state(processes), sap_system_state.DISPSTATUS_YELLOW
        )

    def test_any_red_wins(self):
        processes = [make_item("msg_server", sap_system_state.DISPSTATUS_RED),
                     make_item("disp+work", sap_system_state.DISPSTATUS_GREEN)]
        self.assertEqual(
            sap_system_state.compute_local_state(processes), sap_system_state.DISPSTATUS_RED
        )


class TestGetSoapItems(ModuleTestCase):
    """
    Regression tests for the reported bug: 'Text' object has no attribute
    'get'. suds does not wrap single-occurrence repeating elements into a
    list, so when sapstartsrv returns exactly one <item> (which regularly
    happens for GetProcessList on instances with a single monitored
    process, e.g. an ERS), the raw SOAP result exposes a single object (or
    even a bare Text/string) instead of a list. _get_soap_items() must
    normalize this so callers always get a list of dicts.
    """

    def test_multiple_items_returns_list_of_dicts(self):
        client = MagicMock()
        raw_result = FakeSudsResult(item=[
            FakeSudsComplexItem(name="msg_server", dispstatus="SAPControl-GREEN"),
            FakeSudsComplexItem(name="enserver", dispstatus="SAPControl-GREEN"),
        ])
        with patch.object(sap_system_state, 'call_function', return_value=raw_result), \
                patch.object(sap_system_state, 'recursive_dict', side_effect=fake_recursive_dict):
            result = sap_system_state.get_process_list(client)
        self.assertEqual(result, [
            make_item("msg_server", "SAPControl-GREEN"),
            make_item("enserver", "SAPControl-GREEN"),
        ])

    def test_single_item_not_wrapped_by_suds_still_returns_a_list(self):
        client = MagicMock()
        # suds returns a single object here, NOT a one-element list.
        raw_result = FakeSudsResult(item=FakeSudsComplexItem(
            name="enrepserver", dispstatus="SAPControl-GRAY"
        ))
        with patch.object(sap_system_state, 'call_function', return_value=raw_result), \
                patch.object(sap_system_state, 'recursive_dict', side_effect=fake_recursive_dict):
            result = sap_system_state.get_process_list(client)
        self.assertEqual(result, [make_item("enrepserver", "SAPControl-GRAY")])

    def test_bare_text_item_is_skipped_instead_of_crashing(self):
        client = MagicMock()
        # Simulates a bare suds Text/str value instead of a structured item.
        raw_result = FakeSudsResult(item="OK")
        with patch.object(sap_system_state, 'call_function', return_value=raw_result):
            result = sap_system_state.get_process_list(client)
        self.assertEqual(result, [])

    def test_no_item_attribute_returns_empty_list(self):
        client = MagicMock()
        raw_result = FakeSudsResult()  # no 'item' attribute at all
        with patch.object(sap_system_state, 'call_function', return_value=raw_result):
            result = sap_system_state.get_process_list(client)
        self.assertEqual(result, [])

    def test_none_result_returns_empty_list(self):
        client = MagicMock()
        with patch.object(sap_system_state, 'call_function', return_value=None):
            result = sap_system_state.get_process_list(client)
        self.assertEqual(result, [])

    def test_get_instance_list_uses_get_system_instance_list_function(self):
        client = MagicMock()
        with patch.object(sap_system_state, 'call_function', return_value=FakeSudsResult()) as mock_call:
            sap_system_state.get_instance_list(client)
        mock_call.assert_called_once_with(client, "GetSystemInstanceList")

    def test_get_process_list_uses_get_process_list_function(self):
        client = MagicMock()
        with patch.object(sap_system_state, 'call_function', return_value=FakeSudsResult()) as mock_call:
            sap_system_state.get_process_list(client)
        mock_call.assert_called_once_with(client, "GetProcessList")


class TestWaitForGraySingleProcessRegression(ModuleTestCase):

    def test_wait_for_gray_handles_single_process_not_wrapped_in_list(self):
        """
        End-to-end regression test for the reported bug: an instance with
        only one monitored process (e.g. an ERS running only
        enrepserver) must not crash wait_for_gray() when suds returns
        that single <item> unwrapped.
        """
        client = MagicMock()
        raw_result = FakeSudsResult(item=FakeSudsComplexItem(
            name="enrepserver", dispstatus="SAPControl-GRAY"
        ))
        with patch.object(sap_system_state, 'call_function', return_value=raw_result), \
                patch.object(sap_system_state, 'recursive_dict', side_effect=fake_recursive_dict), \
                patch.object(sap_system_state, 'get_instance_list_safe', return_value=[]):
            state, instances = sap_system_state.wait_for_gray(client, timeout=10, poll_interval=0)
        self.assertEqual(state, sap_system_state.DISPSTATUS_GRAY)


class TestGetInstanceListSafe(ModuleTestCase):

    def test_swallows_web_fault(self):
        client = MagicMock()
        with patch.object(sap_system_state, 'call_function',
                          side_effect=sap_system_state.WebFault("ASCS unreachable", None)):
            result = sap_system_state.get_instance_list_safe(client)
        self.assertEqual(result, [])

    def test_swallows_transport_error(self):
        client = MagicMock()
        with patch.object(sap_system_state, 'call_function',
                          side_effect=sap_system_state.TransportError("connection refused", 111)):
            result = sap_system_state.get_instance_list_safe(client)
        self.assertEqual(result, [])

    def test_swallows_os_error(self):
        client = MagicMock()
        with patch.object(sap_system_state, 'call_function', side_effect=OSError("connection refused")):
            result = sap_system_state.get_instance_list_safe(client)
        self.assertEqual(result, [])

    def test_warns_via_module_when_provided(self):
        client = MagicMock()
        module = MagicMock()
        with patch.object(sap_system_state, 'call_function', side_effect=OSError("connection refused")):
            sap_system_state.get_instance_list_safe(client, module=module)
        module.warn.assert_called_once()

    def test_does_not_swallow_unexpected_exceptions(self):
        """
        Only the specific, expected failure modes (SOAP fault, transport
        error, OS-level connection error) are swallowed. Anything else
        (e.g. a programming error) must propagate instead of being hidden.
        """
        client = MagicMock()
        with patch.object(sap_system_state, 'call_function', side_effect=ValueError("unexpected bug")):
            with self.assertRaises(ValueError):
                sap_system_state.get_instance_list_safe(client)


class TestWaitForGray(ModuleTestCase):

    def test_completes_using_local_state_even_if_system_wide_view_is_stale(self):
        """
        Regression test for the reported bug: GetSystemInstanceList can stay
        frozen at GREEN (e.g. once the message server is stopped) while the
        local instance has actually reached GRAY. wait_for_gray() must rely
        on GetProcessList (local) and complete regardless.
        """
        client = MagicMock()
        process_sequence = [
            [make_item("disp+work", sap_system_state.DISPSTATUS_GREEN)],
            [make_item("disp+work", sap_system_state.DISPSTATUS_GRAY)],
        ]
        stale_instances = [make_instance("host1", "00", sap_system_state.DISPSTATUS_GREEN)]

        with patch.object(sap_system_state, 'get_process_list', side_effect=process_sequence), \
                patch.object(sap_system_state, 'get_instance_list_safe', return_value=stale_instances):
            state, instances = sap_system_state.wait_for_gray(client, timeout=10, poll_interval=0)

        self.assertEqual(state, sap_system_state.DISPSTATUS_GRAY)
        # informational only, still reflects the (stale) system-wide view
        self.assertEqual(instances, stale_instances)

    def test_times_out_when_local_state_never_reaches_gray(self):
        client = MagicMock()
        with patch.object(sap_system_state, 'get_process_list',
                          return_value=[make_item("disp+work", sap_system_state.DISPSTATUS_GREEN)]), \
                patch('time.time', side_effect=[0, 1, 2, 100]):
            state, instances = sap_system_state.wait_for_gray(client, timeout=10, poll_interval=0)
        self.assertIsNone(state)
        self.assertEqual(instances, [])


class TestWaitForGreen(ModuleTestCase):

    def test_regression_detected_from_local_process_list(self):
        client = MagicMock()
        process_sequence = [
            [make_item("disp+work", sap_system_state.DISPSTATUS_YELLOW)],
            [make_item("disp+work", sap_system_state.DISPSTATUS_GRAY)],  # regression: yellow -> gray
        ]
        with patch.object(sap_system_state, 'get_process_list', side_effect=process_sequence), \
                patch.object(sap_system_state, 'get_instance_list_safe', return_value=[]):
            state, instances, regression = sap_system_state.wait_for_green(
                client, timeout=10, poll_interval=0, post_startup_delay=5
            )
        self.assertIsNotNone(regression)
        self.assertEqual(regression['instance'].get('name'), 'disp+work')
        self.assertEqual(regression['from_state'], sap_system_state.DISPSTATUS_YELLOW)
        self.assertEqual(regression['to_state'], sap_system_state.DISPSTATUS_GRAY)

    def test_completes_after_stability_window(self):
        client = MagicMock()
        with patch.object(sap_system_state, 'get_process_list',
                          return_value=[make_item("disp+work", sap_system_state.DISPSTATUS_GREEN)]), \
                patch.object(sap_system_state, 'get_instance_list_safe', return_value=[]), \
                patch('time.time', side_effect=[0, 0, 1, 100]):
            state, instances, regression = sap_system_state.wait_for_green(
                client, timeout=10, poll_interval=0, post_startup_delay=5
            )
        self.assertIsNone(regression)
        self.assertEqual(state, sap_system_state.DISPSTATUS_GREEN)


class TestMainIdempotency(ModuleTestCase):

    def setUp(self):
        super(TestMainIdempotency, self).setUp()
        self.patcher_suds = patch.object(sap_system_state, 'HAS_SUDS_LIBRARY', True)
        self.patcher_suds.start()
        self.addCleanup(self.patcher_suds.stop)

    def test_stop_is_idempotent_based_on_local_state(self):
        """
        Even if GetSystemInstanceList would report a stale GREEN system-wide
        view, the module must not attempt to stop again if the local
        instance is already GRAY.
        """
        with patch.object(sap_system_state, 'connection', return_value=MagicMock()), \
                patch.object(sap_system_state, 'get_process_list',
                             return_value=[make_item("disp+work", sap_system_state.DISPSTATUS_GRAY)]), \
                patch.object(sap_system_state, 'get_instance_list_safe',
                             return_value=[make_instance("host1", "00", sap_system_state.DISPSTATUS_GREEN)]), \
                patch.object(sap_system_state, 'call_function') as mock_call:
            with set_module_args({
                "sysnr": "00",
                "state": "stopped",
                "hostname": "localhost",
            }):
                with self.assertRaises(AnsibleExitJson) as ctx:
                    sap_system_state.main()

        result = ctx.exception.args[0]
        self.assertFalse(result['changed'])
        self.assertIn("already GRAY", result['msg'])
        # StopSystem must never have been called
        mock_call.assert_not_called()

    def test_stop_waits_on_local_state_and_succeeds_despite_stale_instance_list(self):
        process_sequence = [
            [make_item("disp+work", sap_system_state.DISPSTATUS_GREEN)],  # initial state check
            [make_item("disp+work", sap_system_state.DISPSTATUS_GREEN)],  # first poll
            [make_item("disp+work", sap_system_state.DISPSTATUS_GRAY)],   # second poll -> done
        ]
        stale_instances = [make_instance("host1", "00", sap_system_state.DISPSTATUS_GREEN)]

        with patch.object(sap_system_state, 'connection', return_value=MagicMock()), \
                patch.object(sap_system_state, 'get_process_list', side_effect=process_sequence), \
                patch.object(sap_system_state, 'get_instance_list_safe', return_value=stale_instances), \
                patch.object(sap_system_state, 'call_function') as mock_call:
            with set_module_args({
                "sysnr": "00",
                "state": "stopped",
                "hostname": "localhost",
                "poll_interval": 0,
            }):
                with self.assertRaises(AnsibleExitJson) as ctx:
                    sap_system_state.main()

        result = ctx.exception.args[0]
        self.assertTrue(result['changed'])
        self.assertEqual(result['state'], sap_system_state.DISPSTATUS_GRAY)
        self.assertIn("successfully stopped", result['msg'])
        mock_call.assert_called_once()
        self.assertEqual(mock_call.call_args[0][1], "StopSystem")
