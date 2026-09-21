"""Unit tests for ceph.ceph_admin.maintenance.MaintenanceMixin.check_maintenance_status"""

import json
from unittest import mock

import pytest

from ceph.ceph_admin.maintenance import HostMaintenanceFailure, MaintenanceMixin


FSID = "f64f341c-655d-11eb-8778-fa163e914bcc"

DAEMONS = [
    {"daemon_type": "osd", "daemon_id": "0"},
    {"daemon_type": "mds", "daemon_id": "cephfs.node2.abc"},
    {"daemon_type": "haproxy", "daemon_id": "ingress.node2"},
]

EXPECTED_CONTAINERS = [
    f"ceph-{FSID}-osd-0",
    f"ceph-{FSID}-mds-cephfs-node2-abc",
    f"ceph-{FSID}-haproxy-ingress-node2",
]


def _podman_output(names):
    return json.dumps([{"Names": [n]} for n in names])


class MockMaintenance(MaintenanceMixin):
    def __init__(self, host_status, ps_daemons):
        self._host_status = host_status
        self._ps_daemons = ps_daemons

    def get_host_status(self, hostname):
        return self._host_status

    def shell(self, args):
        return (FSID, "")

    def ps(self, config):
        return (json.dumps(self._ps_daemons), "")


def _make_node():
    node = mock.Mock()
    node.hostname = "ceph-node2"
    return node


class TestCheckMaintenanceStatusEnter:
    def _subject(self, exec_side_effects):
        obj = MockMaintenance(host_status="maintenance", ps_daemons=DAEMONS)
        node = _make_node()
        node.exec_command.side_effect = exec_side_effects
        return obj, node

    @mock.patch("ceph.ceph_admin.maintenance.sleep", return_value=None)
    def test_enter_succeeds_when_no_containers(self, _sleep):
        obj, node = self._subject([("", "")])
        assert obj.check_maintenance_status("enter", node) is True

    @mock.patch("ceph.ceph_admin.maintenance.sleep", return_value=None)
    def test_enter_succeeds_after_one_retry(self, _sleep):
        obj, node = self._subject([(_podman_output(EXPECTED_CONTAINERS), ""), ("", "")])
        assert obj.check_maintenance_status("enter", node) is True

    @mock.patch("ceph.ceph_admin.maintenance.sleep", return_value=None)
    def test_enter_succeeds_when_unrelated_containers_remain(self, _sleep):
        obj, node = self._subject([(_podman_output(["some-other-container"]), "")])
        assert obj.check_maintenance_status("enter", node) is True

    @mock.patch("ceph.ceph_admin.maintenance.sleep", return_value=None)
    def test_enter_fails_when_daemons_stay_up_throughout_retries(self, _sleep):
        obj, node = self._subject([(_podman_output(EXPECTED_CONTAINERS), "")] * 20)
        assert obj.check_maintenance_status("enter", node) is False

    @mock.patch("ceph.ceph_admin.maintenance.sleep", return_value=None)
    def test_enter_returns_false_when_status_is_not_maintenance(self, _sleep):
        obj = MockMaintenance(host_status="active", ps_daemons=DAEMONS)
        node = _make_node()
        assert obj.check_maintenance_status("enter", node) is False


class TestCheckMaintenanceStatusExit:
    def _subject(self, exec_side_effects, host_status="active"):
        obj = MockMaintenance(host_status=host_status, ps_daemons=DAEMONS)
        node = _make_node()
        node.exec_command.side_effect = exec_side_effects
        return obj, node

    @mock.patch("ceph.ceph_admin.maintenance.sleep", return_value=None)
    def test_exit_succeeds_when_all_daemons_up_immediately(self, _sleep):
        obj, node = self._subject([(_podman_output(EXPECTED_CONTAINERS), "")])
        assert obj.check_maintenance_status("exit", node) is True

    @mock.patch("ceph.ceph_admin.maintenance.sleep", return_value=None)
    def test_exit_succeeds_after_empty_then_all_up(self, _sleep):
        obj, node = self._subject([("", ""), (_podman_output(EXPECTED_CONTAINERS), "")])
        assert obj.check_maintenance_status("exit", node) is True

    @mock.patch("ceph.ceph_admin.maintenance.sleep", return_value=None)
    def test_exit_succeeds_after_partial_then_all_up(self, _sleep):
        obj, node = self._subject([
            (_podman_output(EXPECTED_CONTAINERS[:1]), ""),
            (_podman_output(EXPECTED_CONTAINERS), ""),
        ])
        assert obj.check_maintenance_status("exit", node) is True

    @mock.patch("ceph.ceph_admin.maintenance.sleep", return_value=None)
    def test_exit_fails_when_daemons_never_come_up(self, _sleep):
        obj, node = self._subject([("", "")] * 20)
        assert obj.check_maintenance_status("exit", node) is False

    @mock.patch("ceph.ceph_admin.maintenance.sleep", return_value=None)
    def test_exit_fails_when_only_partial_daemons_come_up(self, _sleep):
        obj, node = self._subject([(_podman_output(EXPECTED_CONTAINERS[:1]), "")] * 20)
        assert obj.check_maintenance_status("exit", node) is False

    @mock.patch("ceph.ceph_admin.maintenance.sleep", return_value=None)
    def test_exit_returns_false_when_status_still_maintenance(self, _sleep):
        obj, node = self._subject(
            [(_podman_output(EXPECTED_CONTAINERS), "")], host_status="maintenance"
        )
        assert obj.check_maintenance_status("exit", node) is False


class TestCheckMaintenanceStatusNoDaemons:
    def test_exit_with_no_daemons_and_not_in_maintenance(self):
        obj = MockMaintenance(host_status="active", ps_daemons=[])
        assert obj.check_maintenance_status("exit", _make_node()) is True

    def test_exit_with_no_daemons_but_still_in_maintenance(self):
        obj = MockMaintenance(host_status="maintenance", ps_daemons=[])
        assert obj.check_maintenance_status("exit", _make_node()) is False

    def test_enter_with_no_daemons(self):
        obj = MockMaintenance(host_status="maintenance", ps_daemons=[])
        assert obj.check_maintenance_status("enter", _make_node()) is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
