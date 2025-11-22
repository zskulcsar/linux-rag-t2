package contract_test

import (
	"bufio"
	"context"
	"encoding/json"
	"fmt"
	"net"
	"os"
	"path/filepath"
	"testing"
	"time"

	"github.com/linux-rag-t2/cli/shared/ipc"
)

func TestClientHandshakeAndQueryFraming(t *testing.T) {
	t.Parallel()

	socketPath := filepath.Join(t.TempDir(), "backend.sock")

	ready := make(chan struct{})
	errCh := make(chan error, 1)
	go func() {
		errCh <- runStubServer(socketPath, ready)
	}()

	select {
	case <-ready:
	case <-time.After(2 * time.Second):
		t.Fatalf("stub server did not start listening on %s", socketPath)
	}

	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()

	client, err := ipc.NewClient(ipc.Config{
		SocketPath: socketPath,
		ClientID:   "contract-tests",
	})
	if err != nil {
		t.Fatalf("failed to create IPC client: %v", err)
	}
	t.Cleanup(func() {
		_ = client.Close()
	})

	resp, err := client.Query(ctx, ipc.QueryRequest{
		Question:         "How do I change file permissions?",
		MaxContextTokens: 4096,
		TraceID:          "contract-trace",
	})
	if err != nil {
		t.Fatalf("expected query to succeed, got error: %v", err)
	}

	if resp.Summary != "Use chmod to adjust permissions." {
		t.Fatalf("unexpected summary: %q", resp.Summary)
	}
	if len(resp.Steps) == 0 {
		t.Fatal("expected at least one procedural step in response")
	}
	if resp.Confidence <= 0 {
		t.Fatalf("expected positive confidence score, got %v", resp.Confidence)
	}
	if resp.TraceID != "contract-trace" {
		t.Fatalf("expected trace propagation, got %q", resp.TraceID)
	}

	select {
	case err := <-errCh:
		if err != nil {
			t.Fatalf("stub server error: %v", err)
		}
	case <-time.After(2 * time.Second):
		t.Fatal("stub server did not finish expectations")
	}
}

func runStubServer(socketPath string, ready chan<- struct{}) error {
	_ = os.Remove(socketPath)
	listener, err := net.Listen("unix", socketPath)
	if err != nil {
		return fmt.Errorf("failed to bind unix socket: %w", err)
	}
	defer listener.Close()

	close(ready)

	conn, err := listener.Accept()
	if err != nil {
		return fmt.Errorf("failed to accept connection: %w", err)
	}
	defer conn.Close()

	reader := bufio.NewReader(conn)
	writer := bufio.NewWriter(conn)

	handshake, err := readJSONFrame(reader)
	if err != nil {
		return err
	}
	if handshakeType, _ := handshake["type"].(string); handshakeType != "handshake" {
		return fmt.Errorf("expected handshake frame, got %v", handshake)
	}
	if protocol, _ := handshake["protocol"].(string); protocol != "rag-cli-ipc" {
		return fmt.Errorf("unexpected protocol: %v", protocol)
	}
	if clientID, _ := handshake["client"].(string); clientID != "contract-tests" {
		return fmt.Errorf("unexpected client identifier: %v", clientID)
	}

	if err := writeJSONFrame(writer, map[string]any{
		"type":     "handshake_ack",
		"protocol": "rag-cli-ipc",
		"version":  1,
		"server":   "contract-stub",
	}); err != nil {
		return err
	}

	request, err := readJSONFrame(reader)
	if err != nil {
		return err
	}
	if frameType, _ := request["type"].(string); frameType != "request" {
		return fmt.Errorf("expected request frame, got %v", request)
	}
	path, _ := request["path"].(string)
	if path != "/v1/query" {
		return fmt.Errorf("unexpected request path: %q", path)
	}

	correlationID, _ := request["correlation_id"].(string)
	if correlationID == "" {
		return fmt.Errorf("expected correlation id to be populated")
	}

	body, ok := request["body"].(map[string]any)
	if !ok {
		return fmt.Errorf("request body must be an object, got %T", request["body"])
	}
	if question, _ := body["question"].(string); question != "How do I change file permissions?" {
		return fmt.Errorf("unexpected question payload: %v", body)
	}
	if tokens, _ := body["max_context_tokens"].(float64); int(tokens) != 4096 {
		return fmt.Errorf("expected max_context_tokens to be 4096, got %v", body["max_context_tokens"])
	}
	if trace, _ := body["trace_id"].(string); trace != "contract-trace" {
		return fmt.Errorf("expected trace_id propagation, got %v", trace)
	}

	if err := writeJSONFrame(writer, map[string]any{
		"type":           "response",
		"status":         200,
		"correlation_id": correlationID,
		"body": map[string]any{
			"summary":    "Use chmod to adjust permissions.",
			"steps":      []any{"Run chmod with desired mode", "Verify permissions with ls -l"},
			"references": []any{map[string]any{"label": "chmod(1)"}},
			"confidence": 0.82,
			"trace_id":   "contract-trace",
			"latency_ms": 120,
		},
	}); err != nil {
		return err
	}

	if err := writer.Flush(); err != nil {
		return fmt.Errorf("failed to flush response: %w", err)
	}

	return nil
}

func readJSONFrame(reader *bufio.Reader) (map[string]any, error) {
	lengthLine, err := reader.ReadString('\n')
	if err != nil {
		return nil, fmt.Errorf("failed to read length prefix: %w", err)
	}

	var payloadLength int
	if _, err := fmt.Sscanf(lengthLine, "%d\n", &payloadLength); err != nil {
		return nil, fmt.Errorf("invalid length prefix %q: %w", lengthLine, err)
	}

	payload := make([]byte, payloadLength)
	if _, err := reader.Read(payload); err != nil {
		return nil, fmt.Errorf("failed to read payload: %w", err)
	}

	next, err := reader.ReadByte()
	if err != nil {
		return nil, fmt.Errorf("failed to read frame terminator: %w", err)
	}
	if next != '\n' {
		return nil, fmt.Errorf("expected trailing newline terminator, got %q", next)
	}

	var message map[string]any
	if err := json.Unmarshal(payload, &message); err != nil {
		return nil, fmt.Errorf("failed to decode payload %q: %w", string(payload), err)
	}

	return message, nil
}

func writeJSONFrame(writer *bufio.Writer, message map[string]any) error {
	payload, err := json.Marshal(message)
	if err != nil {
		return fmt.Errorf("failed to marshal response: %w", err)
	}

	if _, err := fmt.Fprintf(writer, "%d\n", len(payload)); err != nil {
		return fmt.Errorf("failed to write length prefix: %w", err)
	}
	if _, err := writer.Write(payload); err != nil {
		return fmt.Errorf("failed to write payload: %w", err)
	}
	if err := writer.WriteByte('\n'); err != nil {
		return fmt.Errorf("failed to write frame terminator: %w", err)
	}
	return nil
}
