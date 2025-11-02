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
	done := make(chan struct{})
	go runStubServer(t, socketPath, ready, done)

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
	case <-done:
	case <-time.After(2 * time.Second):
		t.Fatal("stub server did not finish expectations")
	}
}

func runStubServer(t *testing.T, socketPath string, ready chan<- struct{}, done chan<- struct{}) {
	t.Helper()

	_ = os.Remove(socketPath)
	listener, err := net.Listen("unix", socketPath)
	if err != nil {
		t.Fatalf("failed to bind unix socket: %v", err)
	}

	close(ready)

	conn, err := listener.Accept()
	if err != nil {
		listener.Close()
		t.Fatalf("failed to accept connection: %v", err)
	}

	reader := bufio.NewReader(conn)
	writer := bufio.NewWriter(conn)

	handshake := mustReadFrame(t, reader)
	if handshakeType, _ := handshake["type"].(string); handshakeType != "handshake" {
		t.Fatalf("expected handshake frame, got %v", handshake)
	}
	if protocol, _ := handshake["protocol"].(string); protocol != "rag-cli-ipc" {
		t.Fatalf("unexpected protocol: %v", protocol)
	}
	if clientID, _ := handshake["client"].(string); clientID != "contract-tests" {
		t.Fatalf("unexpected client identifier: %v", clientID)
	}

	mustWriteFrame(t, writer, map[string]any{
		"type":     "handshake_ack",
		"protocol": "rag-cli-ipc",
		"version":  1,
		"server":   "contract-stub",
	})

	request := mustReadFrame(t, reader)
	if frameType, _ := request["type"].(string); frameType != "request" {
		t.Fatalf("expected request frame, got %v", request)
	}
	path, _ := request["path"].(string)
	if path != "/v1/query" {
		t.Fatalf("unexpected request path: %q", path)
	}

	correlationID, _ := request["correlation_id"].(string)
	if correlationID == "" {
		t.Fatal("expected correlation id to be populated")
	}

	body, ok := request["body"].(map[string]any)
	if !ok {
		t.Fatalf("request body must be an object, got %T", request["body"])
	}
	if question, _ := body["question"].(string); question != "How do I change file permissions?" {
		t.Fatalf("unexpected question payload: %v", body)
	}
	if tokens, _ := body["max_context_tokens"].(float64); int(tokens) != 4096 {
		t.Fatalf("expected max_context_tokens to be 4096, got %v", body["max_context_tokens"])
	}
	if trace, _ := body["trace_id"].(string); trace != "contract-trace" {
		t.Fatalf("expected trace_id propagation, got %v", trace)
	}

	mustWriteFrame(t, writer, map[string]any{
		"type":           "response",
		"status":         200,
		"correlation_id": correlationID,
		"body": map[string]any{
			"summary":   "Use chmod to adjust permissions.",
			"steps":     []any{"Run chmod with desired mode", "Verify permissions with ls -l"},
			"references": []any{map[string]any{"label": "chmod(1)"}},
			"confidence": 0.82,
			"trace_id":   "contract-trace",
			"latency_ms": 120,
		},
	})

	if err := writer.Flush(); err != nil {
		t.Fatalf("failed to flush response: %v", err)
	}

	conn.Close()
	listener.Close()
	close(done)
}

func mustReadFrame(t *testing.T, reader *bufio.Reader) map[string]any {
	t.Helper()

	lengthLine, err := reader.ReadString('\n')
	if err != nil {
		t.Fatalf("failed to read length prefix: %v", err)
	}

	var payloadLength int
	if _, err := fmt.Sscanf(lengthLine, "%d\n", &payloadLength); err != nil {
		t.Fatalf("invalid length prefix %q: %v", lengthLine, err)
	}

	payload := make([]byte, payloadLength)
	if _, err := reader.Read(payload); err != nil {
		t.Fatalf("failed to read payload: %v", err)
	}

	next, err := reader.ReadByte()
	if err != nil {
		t.Fatalf("failed to read frame terminator: %v", err)
	}
	if next != '\n' {
		t.Fatalf("expected trailing newline terminator, got %q", next)
	}

	var message map[string]any
	if err := json.Unmarshal(payload, &message); err != nil {
		t.Fatalf("failed to decode payload %q: %v", string(payload), err)
	}

	return message
}

func mustWriteFrame(t *testing.T, writer *bufio.Writer, message map[string]any) {
	t.Helper()

	payload, err := json.Marshal(message)
	if err != nil {
		t.Fatalf("failed to marshal response: %v", err)
	}

	if _, err := fmt.Fprintf(writer, "%d\n", len(payload)); err != nil {
		t.Fatalf("failed to write length prefix: %v", err)
	}
	if _, err := writer.Write(payload); err != nil {
		t.Fatalf("failed to write payload: %v", err)
	}
	if err := writer.WriteByte('\n'); err != nil {
		t.Fatalf("failed to write frame terminator: %v", err)
	}
}
