from kubernetes import client, config, watch
import datetime

def get_pod_logs(api_client, pod_name, namespace):
    """
    Fetches the recent logs from the crashed pod.
    This is the 'Analyze' step of MAPE-K.
    """
    try:
        logs = api_client.read_namespaced_pod_log(
            name=pod_name, 
            namespace=namespace, 
            tail_lines=50
        )
        return logs
    except Exception as e:
        return f"Could not retrieve logs: {e}"

def main():
    print("KubeWhisperer Observer Starting")
    print(f" [i] Time: {datetime.datetime.now()}")

    # 1. Connect
    try:
        config.load_kube_config()
        print(" [✓] Connected to Kubernetes Cluster")
    except Exception as e:
        print(f" [X] Connection Failed: {e}")
        return

    # 2. Setup
    v1 = client.CoreV1Api()
    w = watch.Watch()
    
    print(" [i] Listening for 'CrashLoopBackOff' events... (Press Ctrl+C to stop)")

    # 3. Watch Loop
    try:
        for event in w.stream(v1.list_pod_for_all_namespaces):
            pod = event['object']
            
            if pod.status.container_statuses:
                for container in pod.status.container_statuses:
                    
                    if container.state.waiting and container.state.waiting.reason == "CrashLoopBackOff":
                        
                        print(f"\nCRASH DETECTED")
                        print(f"      Pod: {pod.metadata.name}")
                        print(f"      Reason: {container.state.waiting.reason}")
                        
                        print("      [+] Fetching logs for analysis...")

                        logs = get_pod_logs(v1, pod.metadata.name, pod.metadata.namespace)
                        
                        print(f"      LOG SNIPPET START ")
                        print(logs.strip())
                        print(f"     LOG SNIPPET END ")
                        print("-" * 30)
                        
    except KeyboardInterrupt:
        print("\n [i] Observer stopped by user.")
    except Exception as e:
        print(f"\n [X] Error: {e}")

if __name__ == "__main__":
    main()