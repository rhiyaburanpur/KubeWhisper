from kubernetes import client, config, watch
import datetime

def main():
    print("KubeWhisperer Observer Starting")
    print(f" [i] Time: {datetime.datetime.now()}")

    try:
        config.load_kube_config()
        print("Connected to Kubernetes Cluster")
    except Exception as e:
        print(f"Connection Failed: {e}")
        return

    v1 = client.CoreV1Api()
    w = watch.Watch()
    
    print(" [i] Listening for 'CrashLoopBackOff' events...")

    try:
        for event in w.stream(v1.list_pod_for_all_namespaces):
            pod = event['object']

            if pod.status.container_statuses:
                for container in pod.status.container_statuses:
                    
                    if container.state.waiting and container.state.waiting.reason == "CrashLoopBackOff":

                        print(f"\nCRASH DETECTED")
                        print(f"      Pod: {pod.metadata.name}")
                        print(f"      Namespace: {pod.metadata.namespace}")
                        print(f"      Reason: {container.state.waiting.reason}")
                        print("-" * 30)
                        
    except KeyboardInterrupt:
        print("\n [i] Observer stopped by user.")

if __name__ == "__main__":
    main()