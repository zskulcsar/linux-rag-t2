package contract_test

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"
	"time"
)

type ragmanScenario struct {
	name          string
	args          []string
	requestAssert func(t *testing.T, body map[string]any)
	responseBody  map[string]any
	outputAssert  func(t *testing.T, output string)
}

func TestRagmanQueryMarkdownOutput(t *testing.T) {
	t.Parallel()

	scenario := ragmanScenario{
		name: "markdown-output",
		args: []string{
			"query",
			"--socket",
			"", // placeholder replaced at runtime
			"How do I change file permissions?",
		},
		requestAssert: func(t *testing.T, body map[string]any) {
			t.Helper()
			if question, _ := body["question"].(string); !strings.Contains(question, "permissions") {
				t.Fatalf("expected question about permissions, got %v", question)
			}
			if tokens, _ := body["max_context_tokens"].(float64); int(tokens) != 4096 {
				t.Fatalf("expected default context tokens 4096, got %v", body["max_context_tokens"])
			}
			if _, ok := body["conversation_id"]; ok {
				t.Fatalf("did not expect conversation id for base scenario, got %v", body["conversation_id"])
			}
		},
		responseBody: map[string]any{
			"summary": "Use chmod to update file permissions.",
			"steps": []any{
				"Inspect current permissions with ls -l.",
				"Run chmod with the desired mode.",
				"Confirm the change completed successfully.",
			},
			"references": []any{
				map[string]any{
					"label": "chmod(1)",
					"url":   "man:chmod",
					"notes": "POSIX manual",
				},
				map[string]any{
					"label": "chmod(1)",
					"url":   "man:chmod",
					"notes": "POSIX manual",
				},
			},
			"citations": []any{
				map[string]any{
					"alias":        "man-pages",
					"document_ref": "chmod(1)",
					"excerpt":      "chmod changes file mode bits.",
				},
				map[string]any{
					"alias":        "man-pages",
					"document_ref": "chmod(1)",
					"excerpt":      "chmod changes file mode bits.",
				},
			},
			"confidence":             0.82,
			"trace_id":               "trace-123",
			"latency_ms":             420,
			"retrieval_latency_ms":   120,
			"llm_latency_ms":         260,
			"index_version":          "catalog/v1",
			"no_answer":              false,
			"answer":                 "Detailed markdown answer",
			"semantic_chunk_count":   6,
			"context_truncated":      false,
			"confidence_threshold":   0.35,
			"stale_index_detected":   false,
			"backend_correlation_id": "contract-correlation",
		},
		outputAssert: func(t *testing.T, output string) {
			t.Helper()
			if !strings.Contains(output, "Summary") {
				t.Fatalf("expected Summary section in output:\n%s", output)
			}
			if !strings.Contains(output, "Steps") {
				t.Fatalf("expected Steps section in output:\n%s", output)
			}
			if !strings.Contains(output, "References") {
				t.Fatalf("expected References section in output:\n%s", output)
			}
			if !strings.Contains(output, "chmod(1)") {
				t.Fatalf("expected cited reference in output:\n%s", output)
			}
			if !strings.Contains(output, "Confidence") {
				t.Fatalf("expected confidence indicator in output:\n%s", output)
			}
		},
	}

	runRagmanScenario(t, scenario)
}

func TestRagmanQueryJSONOutput(t *testing.T) {
	t.Parallel()

	scenario := ragmanScenario{
		name: "json-output",
		args: []string{
			"query",
			"--socket",
			"", // placeholder replaced at runtime
			"--json",
			"--context-tokens",
			"2048",
			"--conversation",
			"ssh-hardening",
			"Fix SSH permissions",
		},
		requestAssert: func(t *testing.T, body map[string]any) {
			t.Helper()
			if tokens, _ := body["max_context_tokens"].(float64); int(tokens) != 2048 {
				t.Fatalf("expected explicit context tokens 2048, got %v", body["max_context_tokens"])
			}
			if conv, _ := body["conversation_id"].(string); conv != "ssh-hardening" {
				t.Fatalf("expected conversation id `ssh-hardening`, got %v", conv)
			}
		},
		responseBody: map[string]any{
			"summary": "Restrict SSH permissions to owner.",
			"steps": []any{
				"Remove group and other write bits from ~/.ssh.",
				"Ensure authorized_keys is readable only by owner.",
			},
			"references": []any{
				map[string]any{
					"label": "sshd_config(5)",
					"url":   "man:sshd_config",
				},
			},
			"citations": []any{
				map[string]any{
					"alias":        "man-pages",
					"document_ref": "sshd_config(5)",
				},
			},
			"confidence":           0.91,
			"trace_id":             "trace-json",
			"latency_ms":           380,
			"retrieval_latency_ms": 140,
			"llm_latency_ms":       240,
			"index_version":        "catalog/v1",
			"no_answer":            false,
		},
		outputAssert: func(t *testing.T, output string) {
			t.Helper()
			var payload map[string]any
			if err := json.Unmarshal([]byte(output), &payload); err != nil {
				t.Fatalf("expected JSON output, got error: %v\n%s", err, output)
			}
			for _, key := range []string{"summary", "steps", "references", "citations", "confidence"} {
				if _, ok := payload[key]; !ok {
					t.Fatalf("expected %s in JSON payload, got %v", key, payload)
				}
			}
		},
	}

	runRagmanScenario(t, scenario)
}

func TestRagmanQueryPlainOutput(t *testing.T) {
	t.Parallel()

	scenario := ragmanScenario{
		name: "plain-output",
		args: []string{
			"query",
			"--socket",
			"", // placeholder replaced at runtime
			"--plain",
			"Reset file permissions",
		},
		requestAssert: func(t *testing.T, body map[string]any) {
			t.Helper()
			if strings.Contains(strings.ToLower(body["question"].(string)), "reset") == false {
				t.Fatalf("expected reset scenario, got %v", body["question"])
			}
		},
		responseBody: map[string]any{
			"summary": "Reset permissions with chmod --reference.",
			"steps": []any{
				"Capture reference permissions from a known-good file.",
				"Apply chmod --reference to the target.",
			},
			"references": []any{
				map[string]any{"label": "chmod(1)"},
			},
			"citations": []any{
				map[string]any{
					"alias":        "man-pages",
					"document_ref": "chmod(1)",
				},
			},
			"confidence": 0.76,
			"trace_id":   "trace-plain",
		},
		outputAssert: func(t *testing.T, output string) {
			t.Helper()
			if strings.Contains(output, "Summary") {
				t.Fatalf("plain output should not contain markdown headings, got %s", output)
			}
			if !strings.Contains(output, "chmod --reference") {
				t.Fatalf("expected instructional text in plain output:\n%s", output)
			}
		},
	}

	runRagmanScenario(t, scenario)
}

func TestRagmanQueryNoAnswerFallback(t *testing.T) {
	t.Parallel()

	scenario := ragmanScenario{
		name: "no-answer",
		args: []string{
			"query",
			"--socket",
			"", // placeholder replaced at runtime
			"How do I boot Windows with ragman?",
		},
		requestAssert: func(t *testing.T, body map[string]any) {
			t.Helper()
			if question, _ := body["question"].(string); !strings.Contains(question, "Windows") {
				t.Fatalf("expected Windows question, got %v", question)
			}
		},
		responseBody: map[string]any{
			"summary":                "Answer is below the confidence threshold. Please rephrase your query or refresh sources via ragadmin.",
			"steps":                  []any{},
			"references":             []any{},
			"citations":              []any{},
			"confidence":             0.14,
			"trace_id":               "trace-no-answer",
			"no_answer":              true,
			"confidence_threshold":   0.35,
			"latency_ms":             210,
			"retrieval_latency_ms":   90,
			"llm_latency_ms":         120,
			"index_version":          "catalog/v1",
			"backend_correlation_id": "no-answer-correlation",
		},
		outputAssert: func(t *testing.T, output string) {
			t.Helper()
			if !strings.Contains(output, "rephrase your query") {
				t.Fatalf("expected low-confidence guidance in output:\n%s", output)
			}
		},
	}

	runRagmanScenario(t, scenario)
}

func runRagmanScenario(t *testing.T, scenario ragmanScenario) {
	t.Helper()

	socketDir := t.TempDir()
	socketPath := filepath.Join(socketDir, "backend.sock")

	configDir := filepath.Join(socketDir, "config")
	if err := os.MkdirAll(filepath.Join(configDir, "ragcli"), 0o755); err != nil {
		t.Fatalf("failed to create config dir: %v", err)
	}
	configPath := filepath.Join(configDir, "ragcli", "config.yaml")
	configContent := "ragman:\n  confidence_threshold: 0.35\n  presenter_default: markdown\nragadmin:\n  output_default: table\n"
	if err := os.WriteFile(configPath, []byte(configContent), 0o644); err != nil {
		t.Fatalf("failed to write config: %v", err)
	}

	args := make([]string, len(scenario.args))
	copy(args, scenario.args)
	for idx, value := range args {
		if value == "" && idx+1 < len(args) && args[idx-1] == "--socket" {
			args[idx] = socketPath
		}
	}

	goStubReady := make(chan struct{})
	goStubResult := make(chan error, 1)
	go func() {
		goStubResult <- runRagmanStub(t, socketPath, scenario, goStubReady)
	}()
	select {
	case <-goStubReady:
	case <-time.After(2 * time.Second):
		t.Fatalf("stub server did not start listening on %s", socketPath)
	}

	cmdArgs := append([]string{"run", "./cli/ragman"}, args...)
	cmd := exec.Command("go", cmdArgs...)
	cmd.Dir = findRepoRoot(t)
	cmd.Env = append(os.Environ(),
		fmt.Sprintf("XDG_RUNTIME_DIR=%s", socketDir),
		fmt.Sprintf("XDG_CONFIG_HOME=%s", configDir),
		fmt.Sprintf("RAGCLI_CONFIG=%s", configPath),
	)

	output, err := cmd.CombinedOutput()
	if err != nil {
		t.Fatalf("expected ragman CLI to succeed for scenario %q: %v\noutput:\n%s", scenario.name, err, string(output))
	}

	if err := <-goStubResult; err != nil {
		t.Fatalf("stub server failed for scenario %q: %v", scenario.name, err)
	}

	scenario.outputAssert(t, string(output))
}

func runRagmanStub(t *testing.T, socketPath string, scenario ragmanScenario, ready chan<- struct{}) error {
	t.Helper()

	_ = os.Remove(socketPath)
	listener, err := net.Listen("unix", socketPath)
	if err != nil {
		return fmt.Errorf("failed to bind unix socket: %w", err)
	}
	defer listener.Close()

	close(ready)

	if unixListener, ok := listener.(*net.UnixListener); ok {
		if err := unixListener.SetDeadline(time.Now().Add(5 * time.Second)); err != nil {
			return fmt.Errorf("failed to set listener deadline: %w", err)
		}
	}

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
		"server":   "ragman-contract-stub",
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
	body, _ := frame["body"].(map[string]any)
	if scenario.requestAssert != nil {
		scenario.requestAssert(t, body)
	}
	correlationID, _ := frame["correlation_id"].(string)

	if err := writeFrame(writer, map[string]any{
		"type":           "response",
		"status":         200,
		"correlation_id": correlationID,
		"body":           scenario.responseBody,
	}); err != nil {
		return fmt.Errorf("failed to write response frame: %w", err)
	}

	return nil
}

func findRepoRoot(t *testing.T) string {
	t.Helper()

	wd, err := os.Getwd()
	if err != nil {
		t.Fatalf("failed to determine working directory: %v", err)
	}

	dir := wd
	for {
		if _, err := os.Stat(filepath.Join(dir, "go.work")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Fatalf("could not locate repository root from %s", wd)
		}
		dir = parent
	}
}
func writeFrame(writer *bufio.Writer, payload any) error {
	bytes, err := json.Marshal(payload)
	if err != nil {
		return err
	}

	if _, err := fmt.Fprintf(writer, "%d\n", len(bytes)); err != nil {
		return err
	}
	if _, err := writer.Write(bytes); err != nil {
		return err
	}
	if err := writer.WriteByte('\n'); err != nil {
		return err
	}
	return writer.Flush()
}

func readFrame(ctx context.Context, reader *bufio.Reader, conn net.Conn) ([]byte, error) {
	if ctx == nil {
		ctx = context.Background()
	}

	var cancel context.CancelFunc
	if deadline, ok := ctx.Deadline(); ok {
		if err := conn.SetReadDeadline(deadline); err != nil {
			return nil, err
		}
		cancel = func() { _ = conn.SetReadDeadline(time.Time{}) }
	} else {
		cancel = func() {}
	}
	defer cancel()

	lengthLine, err := reader.ReadString('\n')
	if err != nil {
		return nil, err
	}

	var payloadLength int
	if _, err := fmt.Sscanf(lengthLine, "%d\n", &payloadLength); err != nil {
		return nil, fmt.Errorf("invalid length prefix %q: %w", strings.TrimSpace(lengthLine), err)
	}
	if payloadLength < 0 {
		return nil, fmt.Errorf("invalid length prefix %d: negative length", payloadLength)
	}

	payload := make([]byte, payloadLength)
	if _, err := io.ReadFull(reader, payload); err != nil {
		return nil, err
	}

	term, err := reader.ReadByte()
	if err != nil {
		return nil, err
	}
	if term != '\n' {
		return nil, fmt.Errorf("expected newline terminator, got %q", term)
	}

	return payload, nil
}
