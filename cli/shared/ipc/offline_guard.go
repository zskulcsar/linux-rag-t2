// Package ipc hosts offline enforcement helpers to keep the CLI sandboxed from remote network access.
package ipc

import (
	"context"
	"errors"
	"log/slog"
	"net"
	"net/http"
	"strings"
	"sync"
)

// ErrExternalNetworkBlocked is returned when the offline guard prevents an outbound HTTP call.
var ErrExternalNetworkBlocked = errors.New("ipc: external network access blocked")

// offline guard state is guarded by a global mutex to support nested installs.
var (
	offlineGuardMu                sync.Mutex
	offlineGuardInstallCount      int
	offlineGuardOriginalTransport http.RoundTripper
)

// offlineTransport wraps the base transport to enforce loopback-only requests.
type offlineTransport struct {
	base http.RoundTripper
	log  *slog.Logger
}

// InstallOfflineHTTPGuard wraps the default HTTP transport to block outbound requests to non-loopback hosts.
// The returned restore function must be invoked to revert to the original transport once offline enforcement is no longer required.
// InstallOfflineHTTPGuard swaps the default HTTP transport with an offline-enforcing wrapper.
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

// RoundTrip enforces loopback-only HTTP requests for the wrapped transport.
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

// isRemoteHost reports whether the host lies outside the loopback range.
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

// slogdiscardHandler is a no-op handler used when slog lacks a configured logger.
type slogdiscardHandler struct{}

// Enabled indicates that no log levels are handled by the discard logger.
func (slogdiscardHandler) Enabled(context.Context, slog.Level) bool { return false }

// Handle drops all log records without processing.
func (slogdiscardHandler) Handle(context.Context, slog.Record) error { return nil }

// WithAttrs returns the discard logger unchanged.
func (slogdiscardHandler) WithAttrs([]slog.Attr) slog.Handler { return slogdiscardHandler{} }

// WithGroup returns the discard logger unchanged for grouped logging.
func (slogdiscardHandler) WithGroup(string) slog.Handler { return slogdiscardHandler{} }
