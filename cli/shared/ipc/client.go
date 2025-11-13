// Package ipc provides newline-delimited JSON clients and helpers for the backend Unix socket transport.
package ipc

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

// Client is a newline-delimited JSON IPC client that communicates with the backend server.
type Client struct {
	conn   net.Conn
	reader *bufio.Reader
	writer *bufio.Writer
	log    *slog.Logger

	clientID          string
	awaitHandshakeAck bool
	mu                sync.Mutex
	retrySchedule     []time.Duration
}

// NewClient establishes a Unix socket connection, performs the handshake, and returns a ready client.
func NewClient(cfg Config) (*Client, error) {
	if strings.TrimSpace(cfg.SocketPath) == "" {
		return nil, errors.New("ipc: socket path must be provided")
	}
	clientID := strings.TrimSpace(cfg.ClientID)
	if clientID == "" {
		clientID = defaultClientID
	}

	dialTimeout := cfg.DialTimeout
	if dialTimeout <= 0 {
		dialTimeout = defaultDialTimout
	}

	socket := cfg.SocketPath
	if !filepath.IsAbs(socket) {
		socket = filepath.Clean(socket)
	}

	logger := cfg.Logger
	if logger == nil {
		logger = slog.Default()
	}
	log := logger.With("socket", socket, "client", clientID)
	retrySchedule := normalizeRetrySchedule(cfg.RetrySchedule)
	log.Info("IPCClient.NewClient(config) :: dial")

	ctx, cancel := context.WithTimeout(context.Background(), dialTimeout)
	defer cancel()

	var d net.Dialer
	conn, err := d.DialContext(ctx, "unix", socket)
	if err != nil {
		log.Error("IPCClient.NewClient(config) :: dial_failed", slog.String("error", err.Error()))
		return nil, fmt.Errorf("ipc: dial unix socket: %w", err)
	}

	c := &Client{
		conn:              conn,
		reader:            bufio.NewReader(conn),
		writer:            bufio.NewWriter(conn),
		clientID:          clientID,
		retrySchedule:     retrySchedule,
		log:               log,
		awaitHandshakeAck: true,
	}

	if err := c.sendHandshake(); err != nil {
		_ = c.Close()
		return nil, err
	}

	log.Info("IPCClient.NewClient(config) :: ready")
	return c, nil
}

// sendHandshake sends the initial identification frame to the backend.
func (c *Client) sendHandshake() error {
	c.log.Info("IPCClient.sendHandshake() :: start")

	frame := handshakeFrame{
		Type:     handshakeType,
		Protocol: protocolName,
		Version:  protocolVersion,
		Client:   c.clientID,
	}
	if err := writeFrame(c.writer, frame); err != nil {
		c.log.Error("IPCClient.sendHandshake() :: write_failed", slog.String("error", err.Error()))
		return fmt.Errorf("ipc: write handshake: %w", err)
	}

	c.awaitHandshakeAck = true
	c.log.Info("IPCClient.sendHandshake() :: pending_ack")
	return nil
}

// Close releases the underlying socket connection.
func (c *Client) Close() error {
	c.mu.Lock()
	defer c.mu.Unlock()
	if c.conn == nil {
		return nil
	}
	err := c.conn.Close()
	c.conn = nil
	return err
}

// Query sends a /v1/query request and decodes the structured response.
func (c *Client) Query(ctx context.Context, req QueryRequest) (QueryResponse, error) {
	c.mu.Lock()
	defer c.mu.Unlock()

	if c.conn == nil {
		return QueryResponse{}, errors.New("ipc: client closed")
	}
	req.Question = strings.TrimSpace(req.Question)
	if req.Question == "" {
		return QueryResponse{}, errors.New("ipc: question must be provided")
	}
	req.ConversationID = strings.TrimSpace(req.ConversationID)
	req.TraceID = strings.TrimSpace(req.TraceID)
	if req.MaxContextTokens <= 0 {
		req.MaxContextTokens = defaultMaxContextTokens
	}

	correlationID := newCorrelationID()
	c.log.Info(
		"IPCClient.Query(ctx, request) :: send",
		slog.String("correlation_id", correlationID),
	)

	frame := requestFrame{
		Type:          requestType,
		Path:          queryPath,
		CorrelationID: correlationID,
		Body:          req,
	}
	if err := writeFrame(c.writer, frame); err != nil {
		c.log.Error(
			"IPCClient.Query(ctx, request) :: write_failed",
			slog.String("error", err.Error()),
		)
		return QueryResponse{}, fmt.Errorf("ipc: write query request: %w", err)
	}

	if c.awaitHandshakeAck {
		if err := c.consumeHandshakeAck(ctx); err != nil {
			return QueryResponse{}, err
		}
	}

	data, err := c.readFrameWithRetry(ctx)
	if err != nil {
		c.log.Error(
			"IPCClient.Query(ctx, request) :: read_failed",
			slog.String("error", err.Error()),
		)
		return QueryResponse{}, fmt.Errorf("ipc: read query response: %w", err)
	}

	var respFrame responseFrame
	if err := json.Unmarshal(data, &respFrame); err != nil {
		return QueryResponse{}, fmt.Errorf("ipc: decode response frame: %w", err)
	}

	if respFrame.Type != responseType {
		return QueryResponse{}, fmt.Errorf("ipc: unexpected frame type %q", respFrame.Type)
	}
	if respFrame.CorrelationID != correlationID {
		return QueryResponse{}, fmt.Errorf("ipc: correlation id mismatch %q", respFrame.CorrelationID)
	}
	if respFrame.Status != 200 {
		return QueryResponse{}, fmt.Errorf("ipc: backend returned status %d", respFrame.Status)
	}

	queryResp, err := DecodeQueryResponse(respFrame.Body)
	if err != nil {
		return QueryResponse{}, fmt.Errorf("ipc: decode query response: %w", err)
	}

	c.log.Info(
		"IPCClient.Query(ctx, request) :: ok",
		slog.String("correlation_id", correlationID),
		slog.String("trace_id", queryResp.TraceID),
	)

	return queryResp, nil
}

// consumeHandshakeAck waits for the server handshake acknowledgement.
func (c *Client) consumeHandshakeAck(ctx context.Context) error {
	data, err := c.readFrameWithRetry(ctx)
	if err != nil {
		c.log.Error("IPCClient.consumeHandshakeAck(ctx) :: read_failed", slog.String("error", err.Error()))
		return fmt.Errorf("ipc: read handshake acknowledgement: %w", err)
	}

	var ack handshakeAckFrame
	if err := json.Unmarshal(data, &ack); err != nil {
		return fmt.Errorf("ipc: decode handshake acknowledgement: %w", err)
	}

	if ack.Type != handshakeAck {
		return fmt.Errorf("ipc: unexpected handshake acknowledgement type %q", ack.Type)
	}
	if ack.Protocol != protocolName {
		return fmt.Errorf("ipc: server protocol mismatch %q", ack.Protocol)
	}
	if ack.Version != protocolVersion {
		return fmt.Errorf("ipc: server protocol version %d unsupported", ack.Version)
	}

	c.awaitHandshakeAck = false
	c.log.Info("IPCClient.consumeHandshakeAck(ctx) :: ack", slog.String("server", ack.Server))
	return nil
}

// readFrameWithRetry reads a frame, retrying on temporary network errors.
func (c *Client) readFrameWithRetry(ctx context.Context) ([]byte, error) {
	var attempt int
	for {
		data, err := readFrame(ctx, c.reader, c.conn)
		if err == nil {
			return data, nil
		}
		if !isRetryableError(err) || attempt >= len(c.retrySchedule) {
			return nil, err
		}

		delay := c.retrySchedule[attempt]
		attempt++
		c.log.Warn(
			"IPCClient.readFrameWithRetry(ctx) :: retry",
			slog.String("error", err.Error()),
			slog.Duration("delay", delay),
			slog.Int("attempt", attempt),
		)
		if err := sleepWithContext(ctx, delay); err != nil {
			return nil, err
		}
	}
}

// normalizeRetrySchedule sanitizes custom retry schedules and falls back to defaults.
func normalizeRetrySchedule(schedule []time.Duration) []time.Duration {
	if len(schedule) == 0 {
		return append([]time.Duration(nil), defaultRetrySchedule...)
	}

	out := make([]time.Duration, 0, len(schedule))
	for _, delay := range schedule {
		if delay <= 0 {
			continue
		}
		out = append(out, delay)
	}
	if len(out) == 0 {
		return append([]time.Duration(nil), defaultRetrySchedule...)
	}
	return out
}

// isRetryableError reports whether the error warrants another frame read attempt.
func isRetryableError(err error) bool {
	if err == nil {
		return false
	}

	var netErr net.Error
	if errors.As(err, &netErr) {
		if netErr.Timeout() {
			return true
		}
	}

	return errors.Is(err, io.ErrUnexpectedEOF)
}

// sleepWithContext pauses for the delay or until the context is cancelled.
func sleepWithContext(ctx context.Context, delay time.Duration) error {
	if delay <= 0 {
		return nil
	}

	if ctx == nil {
		ctx = context.Background()
	}

	timer := time.NewTimer(delay)
	defer timer.Stop()

	select {
	case <-ctx.Done():
		return ctx.Err()
	case <-timer.C:
		return nil
	}
}
