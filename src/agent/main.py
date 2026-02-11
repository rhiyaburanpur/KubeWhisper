import time
from kubernetes import client, config, watch
from src.brain.synapse import Synapse

def get_crash_logs(core_v1, pod_name, namespace="default"):
    try:
        logs = core_v1.read_namespaced_pod_log(
            name=pod_name,
            namespace=namespace,
            tail_lines=50,
            previous=True
        )
        return logs
    except Exception as e:
        return f"Could not retrieve logs: {e}"

def monitor_cluster():
    print(" [agent] Loading Kubernetes Config...")
    config.load_kube_config()
    v1 = client.CoreV1Api()
    w = watch.Watch()

    print(" [agent] Connecting to Neural Engine...")
    brain = Synapse()

    print(" [agent] KubeWhisperer Observer Active. Watching for crashes...")

    try:
        for event in w.stream(v1.list_namespaced_pod, namespace="default"):
            pod = event['object']
            event_type = event['type']

            if event_type != "MODIFIED":
                continue

            if pod.status.container_statuses:
                for container in pod.status.container_statuses:
                    if container.state.waiting and container.state.waiting.reason in ["CrashLoopBackOff", "ImagePullBackOff", "ErrImagePull"]:
                        
                        error_reason = container.state.waiting.reason
                        print(f"\n [!] CRASH DETECTED: {pod.metadata.name} -> {error_reason}")
                        
                        print(" [agent] Fetching evidence...")
                        logs = get_crash_logs(v1, pod.metadata.name)
                        
                        print(" [agent] Consulting Knowledge Base & Gemini...")
                        diagnosis = brain.reason(logs)
                        
                        print("\n" + "="*40)
                        print(" 🤖 KUBEWHISPERER DIAGNOSIS")
                        print("="*40)
                        print(diagnosis)
                        print("="*40 + "\n")
                        
                        time.sleep(10)

    except KeyboardInterrupt:
        print(" [agent] Shutting down.")

if __name__ == "__main__":
    monitor_cluster()