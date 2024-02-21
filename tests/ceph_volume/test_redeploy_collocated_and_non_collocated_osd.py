from json import loads

from ceph.waiter import WaitUntil
from cephci.utils.configs import get_configs
from cli.cephadm.cephadm import CephAdm
from cli.exceptions import OperationFailedError
from cli.utilities.utils import (
    create_yaml_config,
    get_lvm_on_osd_container,
    get_running_containers,
)


def _get_osd_db_id(osd_ids, lvm_list):
    """Get OSD id and associated devices name
    Args:
        osd_ids (list): list of osd ids
        lvm_list (list): list of lvm
    return (dict): osd id associated with device
    """
    osds = {}
    for id in osd_ids:
        for item in lvm_list.get(id):
            if item.get("type") == "db":
                osds[id] = item["devices"]
    return osds


def run(ceph_cluster, **kw):
    """Re-deploy collocated and non-collocated OSDs with wrong dedicated DB size"""

    # Get configs
    get_configs()
    config = kw.get("config")

    # Get the installer and OSD nodes
    installer = ceph_cluster.get_nodes(role="installer")[0]
    osd_nodes = ceph_cluster.get_nodes(role="osd")

    # Create spec for unmanaged OSDs
    specs = config.get("spec")
    specs["unmanaged"] = "true"
    file = create_yaml_config(installer, specs)

    # Update OSD as unmanged
    c = {"pos_args": [], "input": file}
    CephAdm(nodes=installer).ceph.orch.apply(**c)

    # Get the lvm list before OSD Zap
    running_containers, _ = get_running_containers(
        installer, format="json", expr="name=osd", sudo=True
    )
    container_ids = [item.get("Names")[0] for item in loads(running_containers)]
    lvm_list = get_lvm_on_osd_container(container_ids[0], installer)

    # Identify an OSD ID to perform
    osd_ids = list(lvm_list.keys())

    # Zap OSD on node
    conf = {"zap": True, "force": True}
    osd_rm = CephAdm(osd_nodes[0]).ceph.orch.osd.rm(osd_id=osd_ids[0], **conf)
    if not osd_rm:
        raise OperationFailedError("Failed to remove osd")

    # Wait until the rm operation is complete
    timeout, interval = 300, 6
    for w in WaitUntil(timeout=timeout, interval=interval):
        conf = {"format": "json"}
        out = CephAdm(osd_nodes[0]).ceph.orch.osd.rm(status=True, **conf)
        if "No OSD remove/replace operations reported" in out:
            break
    if w.expired:
        raise OperationFailedError("Failed to perform osd rm operation. Timed out!")

    # Create collocated OSDs on node
    c = {"pos_args": ["--all-available-devices"], "service_name": "osd"}
    CephAdm(osd_nodes[0]).ceph.orch.apply(**c)

    # Make the service managed
    specs["unmanaged"] = "false"
    file = create_yaml_config(installer, specs)

    # Create OSDs with yaml file
    c = {"pos_args": [], "input": file}
    CephAdm(nodes=installer).ceph.orch.apply(**c)

    # Get OSD and device before zap
    osd_db_before = _get_osd_db_id(osd_ids=osd_ids, lvm_list=lvm_list)

    # Perform osd zap
    conf = {"zap": True, "force": True}
    osd_rm = CephAdm(osd_nodes[0]).ceph.orch.osd.rm(osd_id=osd_ids[0], **conf)
    if not osd_rm:
        raise OperationFailedError("Failed to remove osd")

    # Wait until the rm operation is complete
    timeout, interval = 300, 6
    for w in WaitUntil(timeout=timeout, interval=interval):
        conf = {"format": "json"}
        out = CephAdm(osd_nodes[0]).ceph.orch.osd.rm(status=True, **conf)
        if "No OSD remove/replace operations reported" in out:
            break
    if w.expired:
        raise OperationFailedError("Failed to perform osd rm operation. Timed out!")

    # Get the lvm list after OSD Zap
    running_containers, _ = get_running_containers(
        installer, format="json", expr="name=osd", sudo=True
    )
    container_ids = [item.get("Names")[0] for item in loads(running_containers)]
    lvm_list = get_lvm_on_osd_container(container_ids[0], installer)

    # Identify an OSD ID to perform
    osd_ids = list(lvm_list.keys())

    # Get OSD and device after zap
    osd_db_after = _get_osd_db_id(osd_ids=osd_ids, lvm_list=lvm_list)

    # Validate if db device has changed
    if osd_db_before != osd_db_after:
        raise OperationFailedError(
            "Faild to re-deploy non-collocated and collocated OSD"
        )

    return 0
