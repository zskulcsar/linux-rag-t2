// Package ipc centralizes shared transport primitives for the CLI <-> backend Unix socket protocol.
package ipc

import (
	"log/slog"
	"time"
)

// Transport constants used by the shared IPC client and helpers.
const (
	protocolName    = "rag-cli-ipc"
	protocolVersion = 1

	requestType   = "request"
	responseType  = "response"
	handshakeType = "handshake"
	handshakeAck  = "handshake_ack"
	queryPath     = "/v1/query"

	defaultClientID         = "ipc-client"
	defaultDialTimout       = 2 * time.Second
	defaultMaxContextTokens = 4096

	maxFrameSize = 16 << 20 // 16 MiB guardrail for transport frames.
)

// defaultRetrySchedule defines the progressive delays between frame read retries.
var defaultRetrySchedule = []time.Duration{
	250 * time.Millisecond,
	500 * time.Millisecond,
	1 * time.Second,
}

// Config describes how to construct a new IPC client.
type Config struct {
	SocketPath    string
	ClientID      string
	DialTimeout   time.Duration
	Logger        *slog.Logger
	RetrySchedule []time.Duration
}
