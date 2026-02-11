import time
import datetime
from kubernetes import client, config, watch
from src.brain.synapse import Synapse

# DEDUPLICATION CACHE
# Format: { "pod_name": last_diagnosis_timestamp }
diagnosis_cache = {}
CACHE_TTL = 300  # 5 minutes in seconds

def get_crash_logs(core_v1, pod_name, namespace="default"):
    """
    Fetches the last 50 lines of logs from a crashed pod.
    """
    try:
        # previous=True gets the logs of the CRASHED instance
        logs = core_v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            tail_lines=50,
            previous=True
        )
        return logs
    except Exception as e:
        return f"Could not retrieve logs: {e}"

def should_diagnose(pod_name):
    """
    Returns True if we should diagnose this pod.
    Returns False if we diagnosed it recently (within CACHE_TTL).
    """
    now = time.time()
    last_seen = diagnosis_cache.get(pod_name)
    
    if last_seen and (now - last_seen) < CACHE_TTL:
        return False
    
    diagnosis_cache[pod_name] = now
    return True

def monitor_cluster():
    print(" [agent] KubeWhisperer Observer Starting...")
    config.load_kube_config()
    v1 = client.CoreV1Api()
    w = watch.Watch()

    try:
        print(" [agent] Connecting to Neuro-Symbolic Engine...")
        brain = Synapse()
    except Exception as e:
        print(f" [X] Synapse Failed: {e}")
        return

    print(" [i] Listening for CrashLoopBackOff...")

    try:
        for event in w.stream(v1.list_pod_for_all_namespaces):
            pod = event['object']
            
            # Optimization: Only check pods that have status fields
            if not pod.status.container_statuses:
                continue

            for container in pod.status.container_statuses:
                if container.state.waiting and container.state.waiting.reason in ["CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull"]:
                    
                    pod_name = pod.metadata.name
                    
                    # DEDUPLICATION CHECK
                    if not should_diagnose(pod_name):
                        # Use continue to silently skip, or print a debug message
                        # print(f" [i] Skipping {pod_name} (Recently Diagnosed)")
                        continue

                    print(f"\n [!] CRASH DETECTED: {pod_name}")
                    
                    print(" [agent] Fetching evidence...")
                    logs = get_crash_logs(v1, pod_name, pod.metadata.namespace)
                    
                    print(" [agent] Analyzing...")
                    diagnosis = brain.reason(logs)
                    
                    print("\n" + "="*40)
                    print(" KUBEWHISPERER DIAGNOSIS")
                    print("="*40)
                    print(diagnosis)
                    print("="*40 + "\n")

    except KeyboardInterrupt:
        print("\n [agent] Shutting down.")

if __name__ == "__main__":
    monitor_cluster()