"""DMFG helpers for mixed-OS (RHEL10 admin + RHEL9 workers/clients) runs.

Kept under tests/cephadm so shared libraries are untouched.
"""

import re

from utility.log import Log

log = Log(__name__)


def _os_major(node):
    try:
        return node.distro_info["VERSION_ID"].split(".")[0]
    except (AttributeError, KeyError, IndexError, TypeError):
        return None


def align_repo_url_to_node_os(repo_url, node):
    """Rewrite compose URL platform segment to the node's RHEL major version."""
    if not repo_url:
        return repo_url
    major = _os_major(node)
    if not major:
        return repo_url

    if re.search(r"rhel-\d+", repo_url):
        aligned = re.sub(r"rhel-\d+", f"rhel-{major}", repo_url)
    elif re.search(r"rhel\d+", repo_url):
        aligned = re.sub(r"rhel\d+", f"rhel{major}", repo_url)
    else:
        return repo_url

    if aligned != repo_url:
        log.info(
            "Aligned repo URL for %s to RHEL%s: %s",
            getattr(node, "hostname", node),
            major,
            aligned,
        )
    return aligned


def rewrite_rhel10_yum_mirrors_to_node_os(node):
    """Point cloud-init RHEL10 BaseOS/AppStream URLs at the node's RHEL compose.

    Inventory such as ibm-eu-rhel-10-*.yaml injects ``.../repos/10/2/...`` onto
    every node. On RHEL9 that breaks prereq installs (podman, lvm2).
    """
    major = _os_major(node)
    if major != "9":
        return

    try:
        parts = node.distro_info["VERSION_ID"].split(".")
        minor = parts[1] if len(parts) > 1 else "8"
    except (AttributeError, KeyError, IndexError, TypeError):
        minor = "8"

    # IBM 9.2 el9cp client RPMs need OpenSSL symbols (e.g. OPENSSL_3.4.0)
    # that are not in older RHEL 9.6 AppStream mirrors — prefer >= 9.8.
    try:
        if int(minor) < 8:
            minor = "8"
    except ValueError:
        minor = "8"

    log.info(
        "Rewriting RHEL10 yum baseurls to repos/9/%s/ on %s",
        minor,
        getattr(node, "hostname", node),
    )
    node.exec_command(
        sudo=True,
        cmd=(
            f"sed -i -E 's|repos/10/[0-9]+/|repos/9/{minor}/|g' "
            "/etc/yum.repos.d/*.repo"
        ),
        check_ec=False,
    )
    node.exec_command(sudo=True, cmd="yum clean all", check_ec=False)


def align_ceph_tools_repos_on_node(node):
    """Rewrite rhel10/rhel-10 segments in Ceph Tools repo files on the node."""
    major = _os_major(node)
    if not major:
        return

    # Only touch compose-style Ceph repo files written by setup_repos / set_tool_repo.
    node.exec_command(
        sudo=True,
        cmd=(
            f"for f in /etc/yum.repos.d/ceph_build.repo "
            f"/etc/yum.repos.d/rh_ceph.repo /etc/yum.repos.d/*Tools*.repo; do "
            f"[ -f \"$f\" ] || continue; "
            f"sed -i -E 's|rhel-10|rhel-{major}|g; s|rhel10|rhel{major}|g' \"$f\"; "
            f"done"
        ),
        check_ec=False,
    )
    node.exec_command(sudo=True, cmd="yum clean all", check_ec=False)
    log.info(
        "Aligned Ceph Tools yum repos on %s for RHEL%s",
        getattr(node, "hostname", node),
        major,
    )


def patch_cephobject_shortname():
    """Expose shortname on CephObject for IBM Package/Cli during mix-OS deploy."""
    from ceph.ceph import CephObject

    if getattr(CephObject, "_mix_os_shortname_patched", False):
        return

    CephObject.shortname = property(lambda self: self.node.shortname)
    CephObject._mix_os_shortname_patched = True
    log.info("Patched CephObject.shortname for mix-OS IBM license setup")


def patch_cephadm_install_installer_only():
    """Install cephadm RPM only on the installer (avoid el10cp on RHEL9 workers)."""
    from ceph.ceph_admin import CephAdmin
    from cli.utilities.configure import setup_ibm_licence

    if getattr(CephAdmin, "_mix_os_install_patched", False):
        return

    def install(self, **kwargs):
        cmd = "yum -y install cephadm"
        if kwargs.get("rpm_version", None):
            cmd = f"{cmd}-{kwargs['rpm_version']}"
        if kwargs.get("nogpgcheck", True):
            cmd += " --nogpgcheck"

        nodes = self.cluster.get_nodes(ignore="client")
        if kwargs.get("upgrade", False):
            if kwargs.get("upgrade_client", True):
                nodes = self.cluster.get_nodes()
            for node in nodes:
                if self.config.get("ibm_build"):
                    setup_ibm_licence(node, build_type=None)
                node.exec_command(sudo=True, cmd="yum update metadata", check_ec=False)
                upd_cmd = "yum update --nogpgcheck -y 'ceph*'"
                if kwargs.get("rpm_version", None):
                    upd_cmd = f"{upd_cmd}-{kwargs['rpm_version']}"
                node.exec_command(sudo=True, cmd=upd_cmd)
                node.exec_command(cmd="rpm -qa | grep ceph")
            return

        node = self.installer
        if self.config.get("product") == "ibm":
            setup_ibm_licence(node, build_type=None)
        node.exec_command(sudo=True, cmd=cmd, long_running=True)
        node.exec_command(cmd="rpm -qa | grep cephadm")

    CephAdmin.install = install
    CephAdmin._mix_os_install_patched = True
    log.info("Patched CephAdmin.install to installer-only for mix-OS")


def patch_setup_repos_for_mix_os():
    """Align Tools compose URLs per node OS inside setup_repos (mix-OS only)."""
    import ceph.utils as ceph_utils

    if getattr(ceph_utils, "_mix_os_setup_repos_patched", False):
        return

    original = ceph_utils.setup_repos

    def setup_repos(ceph, base_url, *args, **kwargs):
        base_url = align_repo_url_to_node_os(base_url, ceph)
        installer_url = kwargs.get("installer_url")
        if installer_url is not None:
            kwargs["installer_url"] = align_repo_url_to_node_os(installer_url, ceph)
        return original(ceph, base_url, *args, **kwargs)

    ceph_utils.setup_repos = setup_repos
    ceph_utils._mix_os_setup_repos_patched = True
    log.info("Patched setup_repos for mix-OS Tools URL alignment")
