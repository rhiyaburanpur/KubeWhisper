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
	"sync"
	"time"

	corev1 "k8s.io/api/core/v1"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/client-go/kubernetes"
	"k8s.io/client-go/tools/clientcmd"
)

// CrashReport matches the Pydantic model in the Python Brain API.
// T1MonitorMs and T2AnalyzeMs are the MAPE-K stage timestamps captured
// by the agent before the request is sent.
type CrashReport struct {
	PodName     string  `json:"pod_name"`
	ErrorLog    string  `json:"error_log"`
	ScenarioID  string  `json:"scenario_id"`
	T1MonitorMs float64 `json:"t1_monitor_ms"`
	T2AnalyzeMs float64 `json:"t2_analyze_ms"`
}

type logEntry struct {
	Level   string `json:"level"`
	Service string `json:"service"`
	Msg     string `json:"msg"`
	Pod     string `json:"pod,omitempty"`
	TraceID string `json:"trace_id,omitempty"`
	Error   string `json:"error,omitempty"`
}

func logJSON(level, msg, pod, traceID, errStr string) {
	entry := logEntry{
		Level:   level,
		Service: "go-agent",
		Msg:     msg,
		Pod:     pod,
		TraceID: traceID,
		Error:   errStr,
	}
	line, _ := json.Marshal(entry)
	fmt.Println(string(line))
}

func nowMs() float64 {
	return float64(time.Now().UnixNano()) / 1e6
}

// --- Deduplication Cache ---

var (
	diagnosisCache   = make(map[string]time.Time)
	diagnosisCacheMu sync.Mutex
)

const cacheTTL = 5 * time.Minute

func shouldDiagnose(podName string) bool {
	diagnosisCacheMu.Lock()
	defer diagnosisCacheMu.Unlock()
	lastSeen, exists := diagnosisCache[podName]
	if exists && time.Since(lastSeen) < cacheTTL {
		return false
	}
	diagnosisCache[podName] = time.Now()
	return true
}

// --- Circuit Breaker ---

type circuitState int

const (
	closed   circuitState = iota
	open     circuitState = iota
	halfOpen circuitState = iota
)

type circuitBreaker struct {
	mu               sync.Mutex
	state            circuitState
	failures         int
	failureThreshold int
	lastFailureAt    time.Time
	cooldownDuration time.Duration
}

func newCircuitBreaker() *circuitBreaker {
	return &circuitBreaker{
		state:            closed,
		failureThreshold: 3,
		cooldownDuration: 30 * time.Second,
	}
}

func (cb *circuitBreaker) allow() bool {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	switch cb.state {
	case closed:
		return true
	case open:
		if time.Since(cb.lastFailureAt) >= cb.cooldownDuration {
			cb.state = halfOpen
			logJSON("info", "Circuit half-open: probing brain", "", "", "")
			return true
		}
		return false
	case halfOpen:
		return true
	}
	return false
}

func (cb *circuitBreaker) recordSuccess() {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	cb.state = closed
	cb.failures = 0
}

func (cb *circuitBreaker) recordFailure() {
	cb.mu.Lock()
	defer cb.mu.Unlock()
	cb.failures++
	cb.lastFailureAt = time.Now()
	if cb.failures >= cb.failureThreshold {
		cb.state = open
		logJSON("warn", fmt.Sprintf("Circuit opened after %d failures. Pausing for %s.", cb.failures, cb.cooldownDuration), "", "", "")
	}
}

var breaker = newCircuitBreaker()

// --- HTTP Client ---

func sendCrashReport(podName string, logs string, t1Ms float64) {
	traceID := fmt.Sprintf("%d", time.Now().UnixNano())[:8]

	if !breaker.allow() {
		logJSON("warn", "Circuit open: skipping brain request", podName, traceID, "brain unreachable")
		return
	}

	brainURL := os.Getenv("BRAIN_URL")
	if brainURL == "" {
		brainURL = "http://localhost:8000/analyze"
	}

	apiKey := os.Getenv("KUBEWHISPERER_API_KEY")
	if apiKey == "" {
		logJSON("error", "KUBEWHISPERER_API_KEY not set. Aborting.", podName, traceID, "missing env var")
		return
	}

	// T2: logs fetched, about to send to brain
	t2Ms := nowMs()

	// scenario_id is read from the pod label "scenario" if present.
	// For non-benchmark pods this will be "unknown".
	scenarioID := os.Getenv("SCENARIO_ID")
	if scenarioID == "" {
		scenarioID = "unknown"
	}

	report := CrashReport{
		PodName:     podName,
		ErrorLog:    logs,
		ScenarioID:  scenarioID,
		T1MonitorMs: t1Ms,
		T2AnalyzeMs: t2Ms,
	}

	jsonData, err := json.Marshal(report)
	if err != nil {
		logJSON("error", "JSON marshal error", podName, traceID, err.Error())
		breaker.recordFailure()
		return
	}

	req, err := http.NewRequest("POST", brainURL, bytes.NewBuffer(jsonData))
	if err != nil {
		logJSON("error", "Request build error", podName, traceID, err.Error())
		breaker.recordFailure()
		return
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-API-Key", apiKey)
	req.Header.Set("X-Trace-ID", traceID)

	logJSON("info", "Sending crash report to brain", podName, traceID, "")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		logJSON("error", "Brain connection failed", podName, traceID, err.Error())
		breaker.recordFailure()
		return
	}
	defer resp.Body.Close()

	body, err := io.ReadAll(resp.Body)
	if err != nil {
		logJSON("error", "Error reading brain response", podName, traceID, err.Error())
		breaker.recordFailure()
		return
	}

	if resp.StatusCode != http.StatusOK {
		logJSON("error", fmt.Sprintf("Brain returned HTTP %d", resp.StatusCode), podName, traceID, string(body))
		breaker.recordFailure()
		return
	}

	breaker.recordSuccess()
	logJSON("info", "Diagnosis received", podName, traceID, "")
	fmt.Println("\n" + string(body))
}

// --- Log Fetcher ---

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

// --- Main ---

func main() {
	logJSON("info", "KubeWhisperer Go-Agent starting", "", "", "")

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

	logJSON("info", "Watching for CrashLoopBackOff and ImagePullBackOff events", "", "", "")

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

					// T1: crash event detected
					t1Ms := nowMs()

					logJSON("warn", fmt.Sprintf("Crash detected: %s", reason), pod.Name, "", "")

					logs := getLogs(clientset, pod.Name)
					sendCrashReport(pod.Name, logs, t1Ms)
				}
			}
		}
	}
}
