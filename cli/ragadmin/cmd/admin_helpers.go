package cmd

import (
	"log/slog"
	"strings"
)

// formatComponentName turns backend component identifiers into friendly names.
func formatComponentName(value string) string {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "disk_capacity":
		return "Disk Capacity"
	case "index_freshness":
		return "Index Freshness"
	case "source_access":
		return "Source Access"
	case "ollama":
		return "Ollama"
	case "weaviate":
		return "Weaviate"
	default:
		formatted := strings.TrimSpace(value)
		if formatted == "" {
			return "Unknown"
		}
		formatted = strings.ReplaceAll(formatted, "_", " ")
		parts := strings.Fields(formatted)
		for i, part := range parts {
			if len(part) == 0 {
				continue
			}
			lower := strings.ToLower(part)
			parts[i] = strings.ToUpper(lower[:1]) + lower[1:]
		}
		return strings.Join(parts, " ")
	}
}

// loggerForState returns the state logger or falls back to slog.Default.
func loggerForState(state *runtimeState) *slog.Logger {
	if state != nil && state.Logger != nil {
		return state.Logger
	}
	return slog.Default()
}
