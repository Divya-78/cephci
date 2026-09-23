"""DMFG mix-OS prereq wrapper: fix RHEL9 yum mirrors, then run install_prereq.

Shared install_prereq.py is left unchanged. This module is only referenced by
mix-OS suites under suites/tentacle/cephadm/.
"""

import importlib

from mix_os_helpers import rewrite_rhel10_yum_mirrors_to_node_os
from utility.log import Log

log = Log(__name__)


def run(**kw):
    """Rewrite RHEL10 inventory mirrors on RHEL9 nodes, then install prereqs."""
    ceph_nodes = kw.get("ceph_nodes") or []
    for node in ceph_nodes:
        rewrite_rhel10_yum_mirrors_to_node_os(node)

    log.info("Running standard install_prereq after mix-OS yum mirror rewrite")
    install_prereq_mod = importlib.import_module("install_prereq")
    return install_prereq_mod.run(**kw)
