package main

import (
	"context"
	"fmt"
	"os"
	"path/filepath"
	"time"

	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/tools/clientcmd"
)

func main() {
	fmt.Println(" KubeWhisperer Go-Agent Starting...")

	// 1. Locate Kubeconfig
	// On Windows, this is usually %USERPROFILE%\.kube\config
	userHomeDir, err := os.UserHomeDir()
	if err != nil {
		fmt.Printf("[X] Error getting home dir: %v\n", err)
		os.Exit(1)
	}
	kubeConfigPath := filepath.Join(userHomeDir, ".kube", "config")

	// 2. Load Configuration
	config, err := clientcmd.BuildConfigFromFlags("", kubeConfigPath)
	if err != nil {
		fmt.Printf("[X] Error loading kubeconfig: %v\n", err)
		fmt.Println("    (Make sure your Kubernetes cluster is running!)")
		os.Exit(1)
	}

	// 3. Create the API Client (The "Clientset")
	clientset, err := kubernetes.NewForConfig(config)
	if err != nil {
		fmt.Printf("[X] Error creating K8s client: %v\n", err)
		os.Exit(1)
	}

	fmt.Println("[✓] Connected to Kubernetes Cluster!")

	// 4. Simple Polling Loop (Proof of Connection)
	// This loops forever, asking the cluster "How many pods exist?"
	for {
		pods, err := clientset.CoreV1().Pods("default").List(context.TODO(), metav1.ListOptions{})
		if err != nil {
			fmt.Printf("[!] Error listing pods: %v\n", err)
		} else {
			fmt.Printf("[i] Cluster Status: Found %d pods in 'default' namespace.\n", len(pods.Items))
		}

		// Sleep for 5 seconds to act like a gentle observer
		time.Sleep(5 * time.Second)
	}
}
