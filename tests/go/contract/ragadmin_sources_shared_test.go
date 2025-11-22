package contract_test

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"testing"
	"time"
)

type ragadminScenario struct {
	name           string
	args           []string
	requestAssert  func(t *testing.T, frame map[string]any)
	responseStatus int
	responseBody   map[string]any
	responseStream []ragadminStreamFrame
	env            map[string]string
	expectError    bool
	outputAssert   func(t *testing.T, output string)
}

func runRagadminScenario(t *testing.T, scenario ragadminScenario) {
	t.Helper()

	if scenario.responseBody == nil && len(scenario.responseStream) == 0 {
		t.Fatalf("scenario %q requires a stub response body or stream", scenario.name)
	}

	socketDir := t.TempDir()
	socketPath := filepath.Join(socketDir, "backend.sock")

	configDir := filepath.Join(socketDir, "config")
	if err := os.MkdirAll(filepath.Join(configDir, "ragcli"), 0o755); err != nil {
		t.Fatalf("failed to create config dir: %v", err)
	}
	configPath := filepath.Join(configDir, "ragcli", "config.yaml")
	configContent := "ragman:\n  confidence_threshold: 0.35\n  presenter_default: markdown\nragadmin:\n  output_default: table\n"
	if err := os.WriteFile(configPath, []byte(configContent), 0o600); err != nil {
		t.Fatalf("failed to write config file: %v", err)
	}

	args := append([]string(nil), scenario.args...)
	for idx := range args {
		if args[idx] == "" && idx > 0 && args[idx-1] == "--socket" {
			args[idx] = socketPath
		}
	}

	ready := make(chan struct{})
	serverErr := make(chan error, 1)
	go func() {
		serverErr <- runRagadminStub(t, socketPath, scenario, ready)
	}()

	select {
	case <-ready:
	case <-time.After(2 * time.Second):
		t.Fatalf("stub server did not start listening on %s", socketPath)
	}

	cmdArgs := append([]string{"run", "./cli/ragadmin"}, args...)
	cmd := exec.Command("go", cmdArgs...)
	cmd.Dir = findRepoRoot(t)
	env := append(os.Environ(),
		fmt.Sprintf("XDG_RUNTIME_DIR=%s", socketDir),
		fmt.Sprintf("XDG_CONFIG_HOME=%s", configDir),
		fmt.Sprintf("RAGCLI_CONFIG=%s", configPath),
	)
	for key, value := range scenario.env {
		env = append(env, fmt.Sprintf("%s=%s", key, value))
	}
	cmd.Env = env

	output, err := cmd.CombinedOutput()

	if err := <-serverErr; err != nil {
		t.Fatalf("stub server failed for scenario %q: %v", scenario.name, err)
	}

	if scenario.expectError {
		if err == nil {
			t.Fatalf("expected ragadmin CLI to fail for scenario %q, but it succeeded:\n%s", scenario.name, string(output))
		}
	} else if err != nil {
		t.Fatalf("expected ragadmin CLI to succeed for scenario %q: %v\noutput:\n%s", scenario.name, err, string(output))
	}

	if scenario.outputAssert != nil {
		scenario.outputAssert(t, string(output))
	}
}

func runRagadminStub(t *testing.T, socketPath string, scenario ragadminScenario, ready chan<- struct{}) error {
	t.Helper()

	_ = os.Remove(socketPath)
	listener, err := net.Listen("unix", socketPath)
	if err != nil {
		return fmt.Errorf("failed to bind unix socket: %w", err)
	}
	defer listener.Close()

	if unixListener, ok := listener.(*net.UnixListener); ok {
		_ = unixListener.SetDeadline(time.Now().Add(5 * time.Second))
	}

	close(ready)

	conn, err := listener.Accept()
	if err != nil {
		return fmt.Errorf("failed to accept connection: %w", err)
	}
	defer conn.Close()

	reader := bufio.NewReader(conn)
	writer := bufio.NewWriter(conn)

	if _, err := readFrame(context.Background(), reader, conn); err != nil {
		return fmt.Errorf("failed to read handshake: %w", err)
	}
	if err := writeFrame(writer, map[string]any{
		"type":     "handshake_ack",
		"protocol": "rag-cli-ipc",
		"version":  1,
		"server":   "ragadmin-contract-stub",
	}); err != nil {
		return fmt.Errorf("failed to write handshake ack: %w", err)
	}

	data, err := readFrame(context.Background(), reader, conn)
	if err != nil {
		return fmt.Errorf("failed to read request: %w", err)
	}

	var frame map[string]any
	if err := json.Unmarshal(data, &frame); err != nil {
		return fmt.Errorf("failed to decode request frame: %w", err)
	}
	if scenario.requestAssert != nil {
		scenario.requestAssert(t, frame)
	}

	correlationID, _ := frame["correlation_id"].(string)

	if len(scenario.responseStream) > 0 {
		for _, streamFrame := range scenario.responseStream {
			status := streamFrame.status
			if status == 0 {
				status = scenario.responseStatus
			}
			if status == 0 {
				status = 200
			}
			body := streamFrame.body
			if body == nil {
				body = scenario.responseBody
			}
			if err := writeFrame(writer, map[string]any{
				"type":           "response",
				"status":         status,
				"correlation_id": correlationID,
				"body":           body,
			}); err != nil {
				return fmt.Errorf("failed to write stream response frame: %w", err)
			}
		}
		return nil
	}

	status := scenario.responseStatus
	if status == 0 {
		status = 200
	}
	if err := writeFrame(writer, map[string]any{
		"type":           "response",
		"status":         status,
		"correlation_id": correlationID,
		"body":           scenario.responseBody,
	}); err != nil {
		return fmt.Errorf("failed to write response frame: %w", err)
	}

	return nil
}

type ragadminStreamFrame struct {
	status int
	body   map[string]any
}
