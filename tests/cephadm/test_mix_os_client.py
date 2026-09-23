"""DMFG mix-OS client wrapper: align Tools repos, then run test_client.

Shared test_client behavior is unchanged for other suites.
"""

import importlib

from mix_os_helpers import align_ceph_tools_repos_on_node
from utility.log import Log

log = Log(__name__)


def run(ceph_cluster, **kwargs):
    """Align Ceph Tools URLs on client nodes, then configure the client."""
    config = kwargs.get("config") or {}
    # Resolve target nodes the same way test_client expects.
    nodes_cfg = config.get("nodes", config.get("node"))
    targets = []
    if isinstance(nodes_cfg, list):
        for entry in nodes_cfg:
            if isinstance(entry, dict):
                targets.extend(entry.keys())
            else:
                targets.append(entry)
    elif nodes_cfg:
        targets.append(nodes_cfg)

    from ceph.utils import get_node_by_id

    for name in targets:
        node = get_node_by_id(ceph_cluster, name)
        if node:
            align_ceph_tools_repos_on_node(node)

    log.info("Running test_client after mix-OS Tools repo alignment")
    test_client = importlib.import_module("test_client")
    return test_client.run(ceph_cluster, **kwargs)
