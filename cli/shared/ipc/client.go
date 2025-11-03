package ipc

import (
	"bufio"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"net"
	"net/http"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

const (
	protocolName    = "rag-cli-ipc"
	protocolVersion = 1

	requestType   = "request"
	responseType  = "response"
	handshakeType = "handshake"
	handshakeAck  = "handshake_ack"
	queryPath     = "/v1/query"

	defaultClientID   = "ipc-client"
	defaultDialTimout = 2 * time.Second
)

// Config describes how to construct a new IPC client.
type Config struct {
	SocketPath  string
	ClientID    string
	DialTimeout time.Duration
	Logger      *slog.Logger
}

// Client is a newline-delimited JSON IPC client that communicates with the backend server.
type Client struct {
	conn   net.Conn
	reader *bufio.Reader
	writer *bufio.Writer
	log    *slog.Logger

	clientID          string
	awaitHandshakeAck bool
	mu                sync.Mutex
}

// ErrExternalNetworkBlocked is returned when the offline guard prevents an outbound HTTP call.
var ErrExternalNetworkBlocked = errors.New("ipc: external network access blocked")

var (
	offlineGuardMu                sync.Mutex
	offlineGuardInstallCount      int
	offlineGuardOriginalTransport http.RoundTripper
)

type offlineTransport struct {
	base http.RoundTripper
	log  *slog.Logger
}

// QueryRequest mirrors the backend contract for issuing query operations.
type QueryRequest struct {
	Question         string `json:"question"`
	MaxContextTokens int    `json:"max_context_tokens"`
	TraceID          string `json:"trace_id,omitempty"`
}

// QueryReference captures a single reference entry returned by the backend.
type QueryReference struct {
	Label string `json:"label"`
	URL   string `json:"url,omitempty"`
	Notes string `json:"notes,omitempty"`
}

// QueryResponse represents the structured answer returned by the backend query endpoint.
type QueryResponse struct {
	Summary    string           `json:"summary"`
	Steps      []string         `json:"steps"`
	References []QueryReference `json:"references"`
	Confidence float64          `json:"confidence"`
	TraceID    string           `json:"trace_id"`
	LatencyMS  int              `json:"latency_ms"`
}

type handshakeFrame struct {
	Type     string `json:"type"`
	Protocol string `json:"protocol"`
	Version  int    `json:"version"`
	Client   string `json:"client"`
}

type handshakeAckFrame struct {
	Type     string `json:"type"`
	Protocol string `json:"protocol"`
	Version  int    `json:"version"`
	Server   string `json:"server"`
}

type requestFrame struct {
	Type          string       `json:"type"`
	Path          string       `json:"path"`
	CorrelationID string       `json:"correlation_id"`
	Body          QueryRequest `json:"body"`
}

type responseFrame struct {
	Type          string          `json:"type"`
	Status        int             `json:"status"`
	CorrelationID string          `json:"correlation_id"`
	Body          json.RawMessage `json:"body"`
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
	if strings.TrimSpace(req.Question) == "" {
		return QueryResponse{}, errors.New("ipc: question must be provided")
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

	data, err := readFrame(ctx, c.reader, c.conn)
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

	var queryResp QueryResponse
	if err := json.Unmarshal(respFrame.Body, &queryResp); err != nil {
		return QueryResponse{}, fmt.Errorf("ipc: decode query response: %w", err)
	}

	c.log.Info(
		"IPCClient.Query(ctx, request) :: ok",
		slog.String("correlation_id", correlationID),
		slog.String("trace_id", queryResp.TraceID),
	)

	return queryResp, nil
}

func (c *Client) consumeHandshakeAck(ctx context.Context) error {
	data, err := readFrame(ctx, c.reader, c.conn)
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

func newCorrelationID() string {
	var buf [16]byte
	if _, err := rand.Read(buf[:]); err != nil {
		return hex.EncodeToString([]byte(time.Now().Format(time.RFC3339Nano)))
	}
	return hex.EncodeToString(buf[:])
}

// InstallOfflineHTTPGuard wraps the default HTTP transport to block outbound requests to non-loopback hosts.
// The returned restore function must be invoked to revert to the original transport once offline enforcement is no longer required.
func InstallOfflineHTTPGuard() func() {
	offlineGuardMu.Lock()
	defer offlineGuardMu.Unlock()

	if offlineGuardInstallCount == 0 {
		offlineGuardOriginalTransport = http.DefaultTransport
		logger := slog.Default()
		if logger == nil {
			logger = slog.New(slogdiscardHandler{})
		}
		http.DefaultTransport = &offlineTransport{
			base: offlineGuardOriginalTransport,
			log:  logger.With(slog.String("component", "ipc.offline_guard")),
		}
	}
	offlineGuardInstallCount++

	return func() {
		offlineGuardMu.Lock()
		defer offlineGuardMu.Unlock()

		if offlineGuardInstallCount == 0 {
			return
		}
		offlineGuardInstallCount--
		if offlineGuardInstallCount == 0 && offlineGuardOriginalTransport != nil {
			http.DefaultTransport = offlineGuardOriginalTransport
			offlineGuardOriginalTransport = nil
		}
	}
}

func (t *offlineTransport) RoundTrip(req *http.Request) (*http.Response, error) {
	if req == nil || req.URL == nil {
		return t.base.RoundTrip(req)
	}

	host := req.URL.Hostname()
	if isRemoteHost(host) {
		if t.log != nil {
			t.log.Warn(
				"OfflineGuard blocked outbound HTTP request",
				slog.String("method", req.Method),
				slog.String("url", req.URL.Redacted()),
			)
		}
		return nil, ErrExternalNetworkBlocked
	}

	return t.base.RoundTrip(req)
}

func isRemoteHost(host string) bool {
	if host == "" {
		return false
	}

	lowered := strings.ToLower(host)
	if lowered == "localhost" {
		return false
	}

	ip := net.ParseIP(host)
	if ip == nil {
		return true
	}

	return !ip.IsLoopback()
}

type slogdiscardHandler struct{}

func (slogdiscardHandler) Enabled(context.Context, slog.Level) bool  { return false }
func (slogdiscardHandler) Handle(context.Context, slog.Record) error { return nil }
func (slogdiscardHandler) WithAttrs([]slog.Attr) slog.Handler        { return slogdiscardHandler{} }
func (slogdiscardHandler) WithGroup(string) slog.Handler             { return slogdiscardHandler{} }
