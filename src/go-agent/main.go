package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"path/filepath"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/tools/clientcmd"
)

// CrashReport matches the Pydantic model in the Python API.
type CrashReport struct {
	PodName  string `json:"pod_name"`
	ErrorLog string `json:"error_log"`
}

var diagnosisCache = make(map[string]time.Time)

const cacheTTL = 5 * time.Minute

// shouldDiagnose tracks pod events to prevent redundant diagnoses.
func shouldDiagnose(podName string) bool {
	lastSeen, exists := diagnosisCache[podName]
	if exists && time.Since(lastSeen) < cacheTTL {
		return false
	}
	diagnosisCache[podName] = time.Now()
	return true
}

// sendCrashReport sends the crash report payload to the Python Brain Server via HTTP POST.
func sendCrashReport(podName string, logs string) {
	fmt.Printf(" [->] Sending crash report for %s to Neural Engine...\n", podName)

	report := CrashReport{
		PodName:  podName,
		ErrorLog: logs,
	}

	jsonData, err := json.Marshal(report)
	if err != nil {
		fmt.Printf(" [X] JSON Error: %v\n", err)
		return
	}

	resp, err := http.Post("http://localhost:8000/analyze", "application/json", bytes.NewBuffer(jsonData))
	if err != nil {
		fmt.Printf(" [X] Brain Connection Failed: %v\n", err)
		return
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		fmt.Printf(" [X] Error reading response body: %v\n", err)
		return
	}

	fmt.Println("\n" + string(body))
}

// getLogs fetches the latest log dump for the crashed container.
func getLogs(clientset *kubernetes.Clientset, podName string) string {
	podLogOpts := corev1.PodLogOptions{
		TailLines: func(i int64) *int64 { return &i }(50),
		Previous:  true,
	}
	req := clientset.CoreV1().Pods("default").GetLogs(podName, &podLogOpts)
	podLogs, err := req.Stream(context.TODO())
	if err != nil {
		return fmt.Sprintf("Error fetching logs: %v", err)
	}
	defer podLogs.Close()

	buf := new(bytes.Buffer)
	_, err = io.Copy(buf, podLogs)
	if err != nil {
		return "Error reading logs"
	}
	return buf.String()
}

func main() {
	fmt.Println(" KubeWhisperer Go-Agent: Hybrid Mode Active")

	userHomeDir, _ := os.UserHomeDir()
	kubeConfigPath := filepath.Join(userHomeDir, ".kube", "config")
	config, err := clientcmd.BuildConfigFromFlags("", kubeConfigPath)
	if err != nil {
		panic(err.Error())
	}

	clientset, err := kubernetes.NewForConfig(config)
	if err != nil {
		panic(err.Error())
	}

	fmt.Println("[i] Watching for CrashLoopBackOff events...")
	watcher, err := clientset.CoreV1().Pods("default").Watch(context.TODO(), metav1.ListOptions{})
	if err != nil {
		panic(err.Error())
	}

	ch := watcher.ResultChan()
	for event := range ch {
		pod, ok := event.Object.(*corev1.Pod)
		if !ok || event.Type != "MODIFIED" {
			continue
		}

		for _, containerStatus := range pod.Status.ContainerStatuses {
			if containerStatus.State.Waiting != nil {
				reason := containerStatus.State.Waiting.Reason

				if reason == "CrashLoopBackOff" || reason == "ImagePullBackOff" {
					if !shouldDiagnose(pod.Name) {
						continue
					}

					fmt.Printf("\n[!] CRASH DETECTED: Pod %s -> %s\n", pod.Name, reason)

					logs := getLogs(clientset, pod.Name)
					sendCrashReport(pod.Name, logs)
				}
			}
		}
	}
}
