"""
This is cephfs consistency group snapshot feature Utility module
It contains methods to run quiesce options - quiesce, release,cancel,include,exclude,all,query
It also contains method to mount quiesce members and clean up CG IO datasets
"""

import json
import random
import re

from tests.cephfs.cephfs_utilsV1 import FsUtils
from utility.log import Log

log = Log(__name__)


class CG_Snap_Utils(object):
    def __init__(self, ceph_cluster):
        """
        FS Snapshot Utility object
        Args:
            ceph_cluster (ceph.ceph.Ceph): ceph cluster
        """

        self.ceph_cluster = ceph_cluster
        self.mons = ceph_cluster.get_ceph_objects("mon")
        self.mgrs = ceph_cluster.get_ceph_objects("mgr")
        self.osds = ceph_cluster.get_ceph_objects("osd")
        self.mdss = ceph_cluster.get_ceph_objects("mds")
        self.clients = ceph_cluster.get_ceph_objects("client")
        self.fs_util = FsUtils(ceph_cluster)

    def get_qs_id(self, client, qs_members, fs_name="cephfs"):
        """
        This method is required to fetch quiesce set id, given the quiesce set members.
        If more than one quiesce set exists with quiesce members, the one with latest db_version
        is returned
        Params:
        client - A client object to run ceph cmds
        qs_members - A list of quiesce members, each member in format subvol1 or group1/subvol1 if
                subvol1 belongs to non-default group
        Returns: qs_id(type: str)- quiesce set ID with latest db_version
        """
        qs_member_dict = {}
        for qs_member in qs_members:
            if "/" in qs_member:
                group_name, subvol_name = re.split("/", qs_member)

                qs_member_dict.update(
                    {subvol_name: {"group_name": group_name, "mount_point": ""}}
                )
            else:
                subvol_name = qs_member
                qs_member_dict.update({subvol_name: {"mount_point": ""}})

        qs_all = self.get_qs_all(client, fs_name)
        qs_id_req = []
        for qs_id in qs_all["sets"]:
            found = 0
            for qs_member in qs_member_dict:
                if qs_member_dict[qs_member].get("group_name"):
                    qs_str = f"/volumes/{qs_member_dict[qs_member]['group_name']}/{qs_member}/"
                else:
                    qs_str = f"/volumes/_nogroup/{qs_member}/"

                for member in qs_all["sets"][qs_id]["members"]:
                    if qs_str in member:
                        found += 1
            if found == len(qs_member_dict.keys()):
                qs_id_req.append(qs_id)
        db_version = 0
        log.info(f"qs_id_reqd:{qs_id_req}")
        if len(qs_id_req) > 1:
            for qs_id in qs_all["sets"]:
                if qs_id in qs_id_req:
                    if qs_all["sets"][qs_id]["db_version"] > db_version:
                        qs_id_ret = qs_id
                        db_version = qs_all["sets"][qs_id]["db_version"]
            log.info(f"qs_id_ret : {qs_id_ret},db_version:{db_version}")
            return qs_id_ret
        elif len(qs_id_req) == 1:
            return qs_id_req[0]
        else:
            return 1

    def get_qs_all(self, client, fs_name="cephfs"):
        """
        This method is required to fetch quiesce set details of all(inactive and active) quiesce sets,
        Params:
        client - A client object to run ceph cmds
        qs_members - A list of quiesce members, each member in format subvol1 or group1/subvol1 if
                subvol1 belongs to non-default group
        Returns: qs_query ( type : dict) - output of quiesce --all
        """
        cmd = f"ceph fs subvolume quiesce {fs_name} --all --format json"

        out, rc = client.exec_command(
            sudo=True,
            cmd=cmd,
        )
        qs_query = json.loads(out)
        return qs_query

    def get_qs_query(self, client, qs_id, fs_name="cephfs", **kw_args):
        """
        This method is required to fetch quiesce set details of given quiesce set,
        Params:
        client - A client object to run ceph cmds
        qs_id - A str type input referring to quiesce set id whose details are to be fetched
        Returns: qs_query ( type : dict) - output of quiesce --query
        """
        cmd = f"ceph fs subvolume quiesce {fs_name} --query --set-id {qs_id} --format json"
        out, rc = client.exec_command(
            sudo=True,
            cmd=cmd,
        )
        qs_query = json.loads(out)
        return qs_query

    def cg_quiesce(
        self, client, qs_members, if_await=True, fs_name="cephfs", **kw_args
    ):
        """
        This method is required to perform quiesce on given quiesce members,
        Params:
        client - A client object to run ceph cmds
        qs_members - A list of quiesce members, each member in format subvol1 or group1/subvol1 if
                subvol1 belongs to non-default group
        if_await - Default : True (bool type), if --await to be used quiesce command
        kw_args - Other optional args can be given with dict type data such as,
        kw_args = {
        'qs_id' : cg_test, 'timeout' : 300,'expiration':300','task_validate' : True
        }
        task_validate(bool type) : This can be set if quiesce command response is to be validated, Default : True
        Returns: If quiesce passed, return qs_output ( type : dict) - output of quiesce cmd
                 If quiesce failed, return 1
        """
        qs_member_str = ""
        for qs_member in qs_members:
            qs_member_str += f' "{qs_member}?q=2" '
        cmd = f"ceph fs subvolume quiesce {fs_name} {qs_member_str} --format json"
        if kw_args.get("qs_id"):
            cmd += f"  --set-id {kw_args['qs_id']}"
        if if_await:
            cmd += "  --await"
        if kw_args.get("timeout"):
            cmd += f"  --timeout {kw_args['timeout']}"
        if kw_args.get("expiration"):
            cmd += f"  --expiration {kw_args['expiration']}"
        out, rc = client.exec_command(
            sudo=True,
            cmd=cmd,
        )
        qs_output = json.loads(out)
        if kw_args.get("task_validate", True):
            for qs_id in qs_output["sets"]:
                qs_state = qs_output["sets"][qs_id]["state"]["name"]
                if (if_await and qs_state == "QUIESCED") or (
                    if_await is False and qs_state == "QUIESCING"
                ):
                    log.info(
                        f"Quiesce Validated : await - {if_await},state - {qs_state}"
                    )
                else:
                    log.error(
                        f"Quiesce Validation failed - await - {if_await},state - {qs_state}"
                    )
                    return 1
        return qs_output

    def cg_quiesce_release(
        self, client, qs_id, if_await=True, fs_name="cephfs", **kw_args
    ):
        """
        This method is required to perform quiesce release on given quiesce set id,
        Params:
        client - A client object to run ceph cmds
        qs_id - A str type data referring to quiesce set id
        if_await - Default : True (bool type), if --await to be used in quiesce release command
        kw_args - Other optional args can be given with dict type data such as,
        kw_args = {
        'if_version' : 25,'task_validate' : True
        }
        if_version : db_version of quiesce set, quiesce release to succeed only if if_version matches
        task_validate(bool type) : This can be set if quiesce command response is to be validated, Default : True
        Returns: If quiesce release passed, return qs_output ( type : dict) - output of quiesce release cmd
                 If quiesce release failed, return 1
        """
        cmd = f"ceph fs subvolume quiesce {fs_name} --set-id {qs_id} --release --format json"
        if if_await:
            cmd += "  --await"
        if kw_args.get("if_version"):
            cmd += f"  --if_version {kw_args['if_version']}"
        out, rc = client.exec_command(
            sudo=True,
            cmd=cmd,
        )
        qs_output = json.loads(out)
        if kw_args.get("task_validate", True):
            for qs_id in qs_output["sets"]:
                qs_state = qs_output["sets"][qs_id]["state"]["name"]
                if (if_await and qs_state == "RELEASED") or (
                    if_await is False and qs_state == "RELEASING"
                ):
                    log.info(
                        f"Quiesce Release Validated : await - {if_await},state - {qs_state}"
                    )
                else:
                    log.error(
                        f"Quiesce Release Validation failed - await - {if_await},state - {qs_state}"
                    )
                    return 1

        return qs_output

    def cg_quiesce_cancel(
        self, client, qs_id, if_await=True, fs_name="cephfs", **kw_args
    ):
        """
        This method is required to perform quiesce cancel on given quiesce set id,
        Params:
        client - A client object to run ceph cmds
        qs_id - A str type data referring to quiesce set id
        if_await - Default : True (bool type), if --await to be used in quiesce cancel command
        kw_args - Other optional args can be given with dict type data such as,
        kw_args = {
        'task_validate' : True
        }
        task_validate(bool type) : This can be set if quiesce cancel command response is to be validated, Default : True
        Returns: If quiesce cancel passed, return qs_output ( type : dict) - output of quiesce cancel cmd
                 If quiesce cancel failed, return 1
        """
        cmd = f"ceph fs subvolume quiesce {fs_name} --set-id {qs_id} --cancel --format json"
        if if_await:
            cmd += "  --await"
        out, rc = client.exec_command(
            sudo=True,
            cmd=cmd,
        )
        qs_output = json.loads(out)
        if kw_args.get("task_validate", True):
            for qs_id in qs_output["sets"]:
                qs_state = qs_output["sets"][qs_id]["state"]["name"]
                if (if_await and qs_state == "CANCELED") or (
                    if_await is False and qs_state == "CANCELED"
                ):
                    log.info(
                        f"Quiesce Cancel Validated : await - {if_await},state - {qs_state}"
                    )
                else:
                    log.error(
                        f"Quiesce Cancel Validation failed - await - {if_await},state - {qs_state}"
                    )
                    return 1
        return qs_output

    def cg_quiesce_include(
        self, client, qs_id, qs_members_new, if_await=True, fs_name="cephfs", **kw_args
    ):
        """
        This method is required to include a new subvolume on given quiesce set id,
        Params:
        client - A client object to run ceph cmds
        qs_id - A str type data referring to quiesce set id
        qs_members_new(type : list) - A list of quiesce members to include in format subvolume_name or
        subvolumegroup1/subvolume_name
        if_await - Default : True (bool type), if --await to be used in quiesce include command
        kw_args - Other optional args can be given with dict type data such as,
        kw_args = {
        'task_validate' : True
        }
        task_validate(bool type) : This can be set if quiesce include command response is to be validated, Default:True
        Returns: If quiesce include passed, return qs_output ( type : dict) - output of quiesce include cmd
                 If quiesce include failed, return 1
        """
        qs_member_str = ""
        for qs_member in qs_members_new:
            qs_member_str += f' "{qs_member}?q=2" '
        cmd = f"ceph fs subvolume quiesce {fs_name} --set-id {qs_id} --include {qs_member_str} --format json"
        if if_await:
            cmd += "  --await"
        out, rc = client.exec_command(
            sudo=True,
            cmd=cmd,
        )
        qs_output = json.loads(out)
        member_found = 0
        member_quiesce = 0
        if kw_args.get("task_validate", True):
            for qs_id in qs_output["sets"]:
                qs_state = qs_output["sets"][qs_id]["state"]["name"]
                if (if_await and qs_state == "QUIESCED") or (
                    if_await is False and qs_state == "QUIESCING"
                ):
                    for qs_member_new in qs_members_new:
                        for qs_member in qs_output["sets"][qs_id]["members"]:
                            if qs_member_new in qs_member:
                                member_found += 1
                                member_state = qs_output["sets"][qs_id]["members"][
                                    qs_member
                                ]["state"]["name"]
                                if_exclude = qs_output["sets"][qs_id]["members"][
                                    qs_member
                                ]["excluded"]
                                if (
                                    if_await
                                    and member_state == "QUIESCED"
                                    and if_exclude is False
                                ) or (
                                    if_await is False
                                    and member_state == "QUIESCING"
                                    and if_exclude is False
                                ):
                                    member_quiesce += 1
                                    log.info(
                                        f"Include Validated for {qs_member_new}: state - {member_state}"
                                    )
                                else:
                                    log.error(
                                        f"Include Validation failed for {qs_member_new}: state - {qs_output}"
                                    )
            if member_found == len(qs_members_new):
                log.info("All new members were included in quiesce set")
            if member_quiesce == len(qs_members_new):
                log.info("All new members included are quiesced or been quiescing")
                return qs_output
            else:
                return 1
        return qs_output

    def cg_quiesce_exclude(
        self,
        client,
        qs_id,
        qs_members_exclude,
        if_await=True,
        fs_name="cephfs",
        **kw_args,
    ):
        """
        This method is required to exclude a subvolume from given quiesce set id,
        Params:
        client - A client object to run ceph cmds
        qs_id - A str type data referring to quiesce set id
        qs_members_exclude(type : list) - A list of quiesce members to exclude in format subvolume_name or
        subvolumegroup1/subvolume_name
        if_await - Default : True (bool type), if --await to be used in quiesce exclude command
        kw_args - Other optional args can be given with dict type data such as,
        kw_args = {
        'task_validate' : True
        }
        task_validate(bool type) : This can be set if quiesce include command response is to be validated, Default:True
        Returns: If quiesce exclude passed, return qs_output ( type : dict) - output of quiesce exclude cmd
                 If quiesce exclude failed, return 1
        """
        qs_member_str = ""
        for qs_member in qs_members_exclude:
            qs_member_str += f' "{qs_member}?q=2" '
        cmd = f"ceph fs subvolume quiesce {fs_name} --set-id {qs_id} --exclude {qs_member_str} --format json"
        if if_await:
            cmd += "  --await"
        out, rc = client.exec_command(
            sudo=True,
            cmd=cmd,
        )
        qs_output = json.loads(out)
        member_exclude = 0
        if kw_args.get("task_validate", True):
            for qs_id in qs_output["sets"]:
                for qs_member_exclude in qs_members_exclude:
                    for qs_member in qs_output["sets"][qs_id]["members"]:
                        if qs_member_exclude in qs_member:
                            exclude_state = qs_output["sets"][qs_id]["members"][
                                qs_member
                            ]["excluded"]
                            log.info(
                                f"{qs_member}:{qs_output['sets'][qs_id]['members'][qs_member]}"
                            )
                            if exclude_state is True:
                                member_exclude += 1
                                log.info(f"Exclude Validated for {qs_member_exclude}")
                            else:
                                log.error(
                                    f"Exclude Validation failed for {qs_member_exclude}: {qs_output}"
                                )

            if member_exclude == len(qs_members_exclude):
                log.info("All given members were excluded from quiesce-set")
                return qs_output
            else:
                return 1
        return qs_output

    def cg_quiesce_reset(
        self, client, qs_id, qs_members, if_await=True, fs_name="cephfs", **kw_args
    ):
        """
        This method is required to reset a given quiesce set id.
        Params:
        client - A client object to run ceph cmds
        qs_id - A str type data referring to quiesce set id
        qs_members(type : list) - A list of quiesce members part of quiesce set in format subvolume_name or
        subvolumegroup1/subvolume_name
        if_await - Default : True (bool type), if --await to be used in quiesce reset command
        kw_args - Other optional args can be given with dict type data such as,
        kw_args = {
        'task_validate' : True
        }
        task_validate(bool type) : This can be set if quiesce reset command response is to be validated, Default:True
        Returns: If quiesce reset passed, return qs_output ( type : dict) - output of quiesce reset cmd
                 If quiesce reset failed, return 1
        """
        qs_member_str = ""
        for qs_member in qs_members:
            qs_member_str += f' "{qs_member}?q=2" '
        cmd = f"ceph fs subvolume quiesce {fs_name} --set-id {qs_id} --reset {qs_member_str} --format json"
        if if_await:
            cmd += "  --await"
        out, rc = client.exec_command(
            sudo=True,
            cmd=cmd,
        )
        qs_output = json.loads(out)
        if kw_args.get("task_validate", True):
            for qs_id in qs_output["sets"]:
                qs_state = qs_output["sets"][qs_id]["state"]["name"]
                if (if_await and qs_state == "QUIESCED") or (
                    if_await is False and qs_state == "QUIESCING"
                ):
                    log.info(
                        f"Quiesce reset Validated : await - {if_await},state - {qs_state}"
                    )
                else:
                    log.error(
                        f"Quiesce reset Validation failed - await - {if_await},state - {qs_state}"
                    )
                    return 1
        return qs_output

    def cleanup_cg_io(self, client, mnt_pt_list, del_data=1):
        """
        This method is required to cleanup CG IO dataset and umount mountpoint
        Params:
        client - A client object to run cleanup
        mnt_pt_list(type : list) - list of mount points whose dataset needs a cleanup
        del_data : Default - 1, whether to delete data
        Returns: None
        """

        for mnt_pt in mnt_pt_list:
            if del_data == 1:
                client.exec_command(sudo=True, cmd=f"rm -rf  {mnt_pt}/cg_io")
            client.exec_command(sudo=True, cmd=f"umount -l  {mnt_pt}")

    def mount_qs_members(self, client, qs_members, fs_name="cephfs"):
        """
        This method is required to mount quiesce members
        Params:
        client - A client object to perform mount
        qs_members(type : list) - A list of quiesce members, each member in format subvol1 or group1/subvol1 if
                subvol1 belongs to non-default group
        Returns: qs_member_dict - a dict type data in below format,
        {subvolume : {'group_name' : groupname,'mount_point' : mountpoint}}
        """
        qs_member_dict = {}
        for qs_member in qs_members:
            if "/" in qs_member:
                group_name, subvol_name = re.split("/", qs_member)
                qs_member_dict.update(
                    {subvol_name: {"group_name": group_name, "mount_point": ""}}
                )
            else:
                subvol_name = qs_member
                qs_member_dict.update({subvol_name: {"mount_point": ""}})

        io_params = {
            "fs_util": self.fs_util,
            "client": client,
            "fs_name": fs_name,
            "export_created": 0,
        }
        mnt_type = ["kernel"]
        for qs_member in qs_member_dict:
            cmd = f"ceph fs subvolume getpath {fs_name} {qs_member}"
            if qs_member_dict[qs_member].get("group_name"):
                cmd += f" {qs_member_dict[qs_member].get('group_name')}"
            subvol_path, rc = client.exec_command(
                sudo=True,
                cmd=cmd,
            )
            qs_member_path = subvol_path.strip()
            log.info(f"qs_member_path:{qs_member_path}")
            io_params.update({"mnt_path": qs_member_path})
            path, _ = self.fs_util.mount_ceph(random.choice(mnt_type), io_params)
            qs_member_dict[qs_member].update({"mount_point": path})
            qs_member_dict[qs_member].update({"client": client.node.hostname})
        # setup io modules
        tool_cmd = {
            "smallfile": "git clone https://github.com/distributed-system-analysis/smallfile.git",
            "Crefi": "git clone https://github.com/vijaykumar-koppad/Crefi.git",
        }
        for io_tool in ["smallfile", "Crefi"]:
            try:
                out, rc = client.exec_command(
                    sudo=True,
                    cmd=f"ls /home/cephuser/{io_tool}",
                )
            except Exception as ex:
                if "No such file" in str(ex):
                    client.exec_command(
                        sudo=True,
                        cmd=f"cd /home/cephuser;{tool_cmd[io_tool]}",
                    )

        return qs_member_dict
