// Command testdriver renders query responses for unit tests outside the ragman module.
//
// The binary reads a JSON payload from stdin with the following structure:
//
//	{
//	  "response": { ... ipc.QueryResponse fields ... },
//	  "options": {
//	    "confidence_threshold": 0.35,
//	    "trace_id": "trace-123",
//	    "presenter": "markdown"
//	  }
//	}
//
// It prints a JSON object to stdout containing either the rendered output or an error.
package main

import (
	"encoding/json"
	"fmt"
	"io"
	"os"
	"strings"

	renderio "github.com/linux-rag-t2/cli/ragman/internal/io"
	"github.com/linux-rag-t2/cli/shared/ipc"
)

type driverPayload struct {
	Response ipc.QueryResponse `json:"response"`
	Options  driverOptions     `json:"options"`
}

type driverOptions struct {
	ConfidenceThreshold float64 `json:"confidence_threshold"`
	TraceID             string  `json:"trace_id"`
	Presenter           string  `json:"presenter"`
}

type driverResult struct {
	Output string `json:"output,omitempty"`
	Error  string `json:"error,omitempty"`
}

func main() {
	payload, err := readPayload(os.Stdin)
	if err != nil {
		writeResult(driverResult{Error: err.Error()})
		os.Exit(1)
	}

	opts := renderio.Options{
		ConfidenceThreshold: payload.Options.ConfidenceThreshold,
		TraceID:             payload.Options.TraceID,
		Presenter:           parsePresenter(payload.Options.Presenter),
	}

	output, err := renderio.Render(payload.Response, opts)
	if err != nil {
		writeResult(driverResult{Error: err.Error()})
		os.Exit(1)
	}

	writeResult(driverResult{Output: output})
}

func readPayload(r io.Reader) (driverPayload, error) {
	data, err := io.ReadAll(r)
	if err != nil {
		return driverPayload{}, fmt.Errorf("read payload: %w", err)
	}
	if len(data) == 0 {
		return driverPayload{}, fmt.Errorf("read payload: empty input")
	}

	var payload driverPayload
	if err := json.Unmarshal(data, &payload); err != nil {
		return driverPayload{}, fmt.Errorf("decode payload: %w", err)
	}
	return payload, nil
}

func writeResult(result driverResult) {
	enc := json.NewEncoder(os.Stdout)
	enc.SetIndent("", "  ")
	_ = enc.Encode(result)
}

func parsePresenter(value string) renderio.Format {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case string(renderio.FormatPlain):
		return renderio.FormatPlain
	case string(renderio.FormatJSON):
		return renderio.FormatJSON
	case string(renderio.FormatMarkdown), "":
		return renderio.FormatMarkdown
	default:
		return renderio.Format(value)
	}
}
