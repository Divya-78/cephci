"""DMFG mix-OS deploy wrapper around test_cephadm.

Applies process-local patches so shared CephAdmin/utils libraries stay
unchanged, then runs the standard cephadm deploy workflow.
"""

import importlib

from mix_os_helpers import (
    patch_cephadm_install_installer_only,
    patch_cephobject_shortname,
    patch_setup_repos_for_mix_os,
)
from utility.log import Log

log = Log(__name__)


def run(ceph_cluster, **kwargs):
    """Patch mix-OS behavior, then execute test_cephadm deploy."""
    patch_cephobject_shortname()
    patch_cephadm_install_installer_only()
    patch_setup_repos_for_mix_os()

    log.info("Running test_cephadm with mix-OS patches applied")
    test_cephadm = importlib.import_module("test_cephadm")
    return test_cephadm.run(ceph_cluster, **kwargs)
