// Package ipc houses transport frame helpers used by the shared CLI IPC client.
package ipc

import (
	"bufio"
	"context"
	"crypto/rand"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net"
	"strings"
	"time"
)

// handshakeFrame encodes the client handshake payload.
type handshakeFrame struct {
	Type     string `json:"type"`
	Protocol string `json:"protocol"`
	Version  int    `json:"version"`
	Client   string `json:"client"`
}

// handshakeAckFrame encodes the server acknowledgement payload.
type handshakeAckFrame struct {
	Type     string `json:"type"`
	Protocol string `json:"protocol"`
	Version  int    `json:"version"`
	Server   string `json:"server"`
}

// requestFrame represents a newline-delimited JSON request envelope.
type requestFrame struct {
	Type          string `json:"type"`
	Path          string `json:"path"`
	CorrelationID string `json:"correlation_id"`
	Body          any    `json:"body"`
}

// responseFrame represents a newline-delimited JSON response envelope.
type responseFrame struct {
	Type          string          `json:"type"`
	Status        int             `json:"status"`
	CorrelationID string          `json:"correlation_id"`
	Body          json.RawMessage `json:"body"`
}

// writeFrame marshals and emits a length-prefixed JSON frame.
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

// readFrame reads and validates a length-prefixed JSON frame.
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
	if payloadLength > maxFrameSize {
		return nil, fmt.Errorf("invalid length prefix %d: exceeds max frame size", payloadLength)
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

var correlationIDGenerator = func() string {
	var buf [16]byte
	if _, err := rand.Read(buf[:]); err != nil {
		return hex.EncodeToString([]byte(time.Now().Format(time.RFC3339Nano)))
	}
	return hex.EncodeToString(buf[:])
}

// newCorrelationID generates a random hexadecimal correlation identifier.
func newCorrelationID() string {
	return correlationIDGenerator()
}

// NewTraceID exposes a helper for generating trace identifiers shared across commands.
func NewTraceID() string {
	return newCorrelationID()
}
