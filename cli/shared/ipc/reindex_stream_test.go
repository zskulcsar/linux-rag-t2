package ipc

// These tests codify the streaming behavior described in
// tmp/specs/001-rag-cli/20-11-2025-ragadmin-reindex-streaming-design.md.

import (
	"bufio"
	"bytes"
	"context"
	"errors"
	"io"
	"log/slog"
	"net"
	"testing"
	"time"
)

func TestStartReindexStreamInvokesCallbackForEachFrame(t *testing.T) {
	jobs := []IngestionJob{
		{
			JobID:              "job-123",
			Status:             "running",
			Stage:              "discovering",
			PercentComplete:    floatPtr(5),
			RequestedAt:        "2024-11-20T00:00:00Z",
			DocumentsProcessed: 4,
		},
		{
			JobID:              "job-123",
			Status:             "running",
			Stage:              "chunking",
			PercentComplete:    floatPtr(45),
			RequestedAt:        "2024-11-20T00:00:01Z",
			DocumentsProcessed: 128,
		},
		{
			JobID:              "job-123",
			Status:             "succeeded",
			Stage:              "completed",
			PercentComplete:    floatPtr(100),
			CompletedAt:        "2024-11-20T00:00:04Z",
			DocumentsProcessed: 256,
		},
	}
	client := newTestReindexClient(t, jobs)

	var stages []string
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()

	finalJob, err := client.StartReindexStream(ctx, ReindexRequest{Trigger: "manual"}, func(job IngestionJob) error {
		stages = append(stages, job.Stage)
		return nil
	})
	if err != nil {
		t.Fatalf("StartReindexStream() error = %v", err)
	}
	if finalJob.Status != "succeeded" {
		t.Fatalf("expected final status succeeded, got %s", finalJob.Status)
	}
	if len(stages) != len(jobs) {
		t.Fatalf("expected %d callbacks, got %d (stages=%v)", len(jobs), len(stages), stages)
	}
	if stages[len(stages)-1] != "completed" {
		t.Fatalf("expected last stage completed, got %s", stages[len(stages)-1])
	}
}

func TestStartReindexStreamForwardsCallbackErrors(t *testing.T) {
	jobs := []IngestionJob{
		{
			JobID:           "job-456",
			Status:          "running",
			Stage:           "discovering",
			PercentComplete: floatPtr(10),
		},
		{
			JobID:           "job-456",
			Status:          "succeeded",
			Stage:           "completed",
			PercentComplete: floatPtr(100),
		},
	}
	client := newTestReindexClient(t, jobs)

	expectedErr := errors.New("callback failed")
	var processed int

	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()

	_, err := client.StartReindexStream(ctx, ReindexRequest{Trigger: "manual"}, func(job IngestionJob) error {
		processed++
		return expectedErr
	})
	if !errors.Is(err, expectedErr) {
		t.Fatalf("expected callback error, got %v", err)
	}
	if processed != 1 {
		t.Fatalf("expected callback to run once before error, got %d", processed)
	}
}

func newTestReindexClient(t *testing.T, jobs []IngestionJob) *Client {
	t.Helper()

	oldGenerator := correlationIDGenerator
	correlationIDGenerator = func() string { return "test-correlation" }
	t.Cleanup(func() { correlationIDGenerator = oldGenerator })

	var payload bytes.Buffer
	writer := bufio.NewWriter(&payload)
	for _, job := range jobs {
		frame := map[string]any{
			"type":           responseType,
			"status":         statusAccepted,
			"correlation_id": "test-correlation",
			"body": map[string]any{
				"job": job,
			},
		}
		if err := writeFrame(writer, frame); err != nil {
			t.Fatalf("failed to encode frame: %v", err)
		}
	}
	if err := writer.Flush(); err != nil {
		t.Fatalf("failed to flush encoded frames: %v", err)
	}

	return &Client{
		conn:              &stubConn{},
		reader:            bufio.NewReader(bytes.NewReader(payload.Bytes())),
		writer:            bufio.NewWriter(io.Discard),
		log:               slog.New(slog.NewTextHandler(io.Discard, nil)),
		awaitHandshakeAck: false,
	}
}

func floatPtr(value float64) *float64 {
	return &value
}

type stubConn struct{}

func (c *stubConn) Read(p []byte) (int, error)       { return 0, io.EOF }
func (c *stubConn) Write(p []byte) (int, error)      { return len(p), nil }
func (c *stubConn) Close() error                     { return nil }
func (c *stubConn) LocalAddr() net.Addr              { return fakeAddr("ipc-test") }
func (c *stubConn) RemoteAddr() net.Addr             { return fakeAddr("ipc-test") }
func (c *stubConn) SetDeadline(time.Time) error      { return nil }
func (c *stubConn) SetReadDeadline(time.Time) error  { return nil }
func (c *stubConn) SetWriteDeadline(time.Time) error { return nil }

type fakeAddr string

func (a fakeAddr) Network() string { return string(a) }
func (a fakeAddr) String() string  { return string(a) }
