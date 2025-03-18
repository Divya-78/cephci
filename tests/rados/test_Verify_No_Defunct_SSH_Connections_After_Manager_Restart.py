"""
Module to verify Ceph Manager Failover functionality and ensure system stability
during continuous failover cycles. This test also checks for defunct SSH processes 
after each failover and applies a workaround if needed (for Pacific release).
The test is designed to run continuously through multiple failover cycles and ensure 
the robustness of the Ceph Manager failover process, as well as system stability with 
respect to SSH process management.
This test is particularly useful for validating that Ceph Manager failover does not 
leave lingering issues such as defunct SSH processes or abnormal system behavior.
"""

import time
import subprocess
from ceph.ceph_admin import CephAdmin
from ceph.rados.core_workflows import RadosOrchestrator
from ceph.rados.mgr_workflows import MgrWorkflows
from utility.log import Log

log = Log(__name__)

def run(ceph_cluster, **kw):
    """
    Test to verify Manager Failover and check for Defunct SSH Processes
    Test Steps:
        1. Failover of Active Manager Continuously
        2. Check for Defunct SSH Processes
        3. Ensure system stability after failover
        4. Application Workaround (if applicable) for defunct SSH
        5. Ensure No Crashes During Testing
    """

    log.info(run.__doc__)
    config = kw["config"]
    cephadm = CephAdmin(cluster=ceph_cluster, **config)
    rados_obj = RadosOrchestrator(node=cephadm)
    mgr_obj = MgrWorkflows(node=cephadm)
    
    # Step 1: Ensure the cluster is healthy
    log.info("Checking cluster health...")
    rados_obj.log_cluster_health()

    log.info("Step 1.2: Identify the active Ceph manager")
    # Using the get_active_mgr method to get the active manager
    active_mgr = mgr_obj.get_active_mgr()  # Get active manager using your method
    log.info(f"Current active manager is: {active_mgr}")

    # Step 1.3: Initiate manager failover by restarting the current active manager
    log.info("Step 1.3: Initiating manager failover")
    mgr_obj.set_mgr_fail(host=active_mgr)  # Use the method to fail the active manager

    # Step 1.4: Verify failover success
    log.info("Step 1.4: Verifying the failover")
    mgr_stats_after_failover = mgr_obj.get_mgr_stats()  # Get the mgr stats after failover
    new_active_mgr = mgr_stats_after_failover["active_name"]  # Extract new active manager from stats
    log.info(f"New active manager is: {new_active_mgr}")

    if active_mgr == new_active_mgr:
        log.error("Failover did not occur as expected")
        return 1

    # Repeat Steps 1.3 and 1.4 multiple times to simulate continuous failovers
    failover_cycles = 5
    for i in range(failover_cycles):
        log.info(f"Cycle {i+1}/{failover_cycles}: Initiating manager failover")
        mgr_obj.set_mgr_fail(host=active_mgr)  # Fail the current active manager
        time.sleep(10)  # Ensure enough time for failover

        log.info(f"Cycle {i+1}/{failover_cycles}: Verifying the failover")
        mgr_stats_after_failover = mgr_obj.get_mgr_stats()  # Get the mgr stats after failover
        new_active_mgr = mgr_stats_after_failover["active_name"]
        log.info(f"New active manager is: {new_active_mgr}")

        if active_mgr == new_active_mgr:
            log.error(f"Cycle {i+1}: Failover did not occur as expected")
            return 1
        active_mgr = new_active_mgr

        # Step 2: Check for defunct SSH processes
        log.info("Step 2: Checking for defunct SSH processes")
        defunct_processes = subprocess.check_output("ps aux | grep defunct", shell=True).decode()
        log.info(f"Defunct processes found: {defunct_processes}")

        if "defunct" in defunct_processes:
            log.error(f"Defunct processes found: {defunct_processes}")
            # Step 4: Apply Workaround (WA) for defunct processes (only for Pacific release)
            ceph_status = rados_obj.log_cluster_health()  # Using your log_cluster_health method
            if "Pacific" in ceph_status:
                log.info("Step 4: Applying workaround (WA) to remove defunct processes")
                result = mgr_obj.remove_mgr_service(host=active_mgr)  # Remove the active MGR
                if not result:
                    log.error(f"Failed to remove MGR {active_mgr}")
                    return 1
                result = mgr_obj.add_mgr_service(host=active_mgr)  # Add it back
                if not result:
                    log.error(f"Failed to add back MGR {active_mgr}")
                    return 1
                log.info("Workaround applied, verifying defunct processes again")

                defunct_processes_after_wa = subprocess.check_output("ps aux | grep defunct", shell=True).decode()
                log.error(f"Defunct processes found: {defunct_processes_after_wa}")


                if "defunct" in defunct_processes_after_wa:
                    log.error(f"Defunct processes still found after WA: {defunct_processes_after_wa}")
                    return 1
            else:
                log.info("No workaround needed as this is not Pacific release")
            return 1

        # Step 3: If no defunct SSH processes found
        log.info("Step 3: No defunct SSH processes found, verifying system health")
        cluster_status_after_failover = rados_obj.log_cluster_health()  # Using your log_cluster_health method
        if "HEALTH_OK" not in cluster_status_after_failover:
            log.error(f"System health is not OK after failover. Status: {cluster_status_after_failover}")
            return 1

        log.info("Step 3.1: Verifying SSH process behavior")
        ssh_processes = subprocess.check_output("ps aux | grep ssh", shell=True).decode()
        if "ssh" in ssh_processes:
            log.info("SSH processes found, ensuring no issues")
            if "defunct" in ssh_processes:
                log.error(f"Found defunct SSH processes: {ssh_processes}")
                return 1
        else:
            log.info("No SSH processes found. This is normal.")

    # Step 5: Ensure No Crashes Occur During Testing
    log.info("Step 5: Ensuring no crashes occurred during the testing")
    if rados_obj.check_crash_status():
        log.error("Test failed due to crash")
        return 1

    log.info("Test completed successfully without issues or crashes")
    return 0