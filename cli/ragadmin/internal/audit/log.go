// Package audit provides JSON-line audit logging helpers for the CLI.
package audit

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"strings"
	"sync"
)

// Logger appends newline-delimited JSON audit entries.
type Logger struct {
	path string
	mu   sync.Mutex
}

// NewLogger creates a logger using the provided path. When empty, the default
// XDG-compliant audit path is used.
func NewLogger(path string) (*Logger, error) {
	resolved := strings.TrimSpace(path)
	if resolved == "" {
		var err error
		resolved, err = defaultLogPath()
		if err != nil {
			return nil, err
		}
	}
	return &Logger{path: resolved}, nil
}

// Append writes the entry as a JSON line to the audit log.
func (l *Logger) Append(entry map[string]any) error {
	if l == nil || entry == nil {
		return nil
	}

	l.mu.Lock()
	defer l.mu.Unlock()

	if err := os.MkdirAll(filepath.Dir(l.path), 0o755); err != nil {
		return fmt.Errorf("audit: create directory: %w", err)
	}

	handle, err := os.OpenFile(l.path, os.O_CREATE|os.O_APPEND|os.O_WRONLY, 0o600)
	if err != nil {
		return fmt.Errorf("audit: open log: %w", err)
	}
	defer handle.Close()

	if err := json.NewEncoder(handle).Encode(entry); err != nil {
		return fmt.Errorf("audit: encode entry: %w", err)
	}
	return nil
}

func defaultLogPath() (string, error) {
	if xdg := strings.TrimSpace(os.Getenv("XDG_DATA_HOME")); xdg != "" {
		return filepath.Join(xdg, "ragcli", "audit.log"), nil
	}
	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("audit: determine home directory: %w", err)
	}
	return filepath.Join(home, ".local", "share", "ragcli", "audit.log"), nil
}
