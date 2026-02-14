package main

import (
	"context"
	"fmt"
	"os"
	"path/filepath"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/tools/clientcmd"
)

func main() {
	fmt.Println(" KubeWhisperer Go-Agent: Watcher Mode Active")

	// 1. Config Setup
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

	// 2. The Watcher
	// We subscribe to the event stream instead of polling
	fmt.Println("[i] Listening for CrashLoopBackOff events...")

	watcher, err := clientset.CoreV1().Pods("default").Watch(context.TODO(), metav1.ListOptions{})
	if err != nil {
		panic(err.Error())
	}

	// 3. The Event Loop
	// This channel receives events as they happen in real-time
	ch := watcher.ResultChan()
	for event := range ch {
		// Type assertion: Convert the generic object to a Pod
		pod, ok := event.Object.(*corev1.Pod)
		if !ok {
			continue
		}

		// We only care about modifications (status updates)
		if event.Type != "MODIFIED" {
			continue
		}

		// Check Container Statuses for Crashes
		for _, containerStatus := range pod.Status.ContainerStatuses {
			if containerStatus.State.Waiting != nil {
				reason := containerStatus.State.Waiting.Reason

				if reason == "CrashLoopBackOff" || reason == "ImagePullBackOff" {
					fmt.Printf("\n[!] CRASH DETECTED: Pod %s -> %s\n", pod.Name, reason)

					// TODO: Phase 6 - We will send this signal to the Python Brain here
					fmt.Println("    [->] Capturing context... (Pending Link to Brain)")
				}
			}
		}
	}
}
