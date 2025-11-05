package ragman_test

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"testing"

	"github.com/linux-rag-t2/cli/shared/ipc"
)

type driverOptions struct {
	ConfidenceThreshold float64 `json:"confidence_threshold"`
	TraceID             string  `json:"trace_id"`
	Presenter           string  `json:"presenter"`
}

type driverPayload struct {
	Response ipc.QueryResponse `json:"response"`
	Options  driverOptions     `json:"options"`
}

type driverResult struct {
	Output string `json:"output"`
	Error  string `json:"error"`
}

func TestRenderMarkdownStructuredSections(t *testing.T) {
	resp := ipc.QueryResponse{
		Summary: "Use chmod to update file permissions.",
		Steps:   []string{"Inspect current permissions with ls -l.", "Run chmod with the desired mode."},
		References: []ipc.QueryReference{
			{Label: "chmod(1)", URL: "man:chmod", Notes: "POSIX manual"},
			{Label: "chmod(1)", URL: "man:chmod", Notes: "POSIX manual"},
		},
		Citations: []ipc.QueryCitation{
			{Alias: "man-pages", DocumentRef: "chmod(1)", Excerpt: "chmod changes file mode bits."},
			{Alias: "man-pages", DocumentRef: "chmod(1)", Excerpt: "chmod changes file mode bits."},
		},
		Confidence: 0.82,
		TraceID:    "trace-response",
		LatencyMS:  420,
	}

	output := invokeRenderer(t, resp, driverOptions{
		ConfidenceThreshold: 0.35,
		TraceID:             "trace-cli",
		Presenter:           "markdown",
	})

	lines := strings.Split(output, "\n")
	if len(lines) == 0 || lines[0] != "Confidence 82% (threshold 35%)" {
		t.Fatalf("expected confidence header, got:\n%s", output)
	}
	requireContains(t, output, "Summary", "Steps", "References")
	if count := strings.Count(output, "man-pages"); count != 1 {
		t.Fatalf("expected deduplicated citation alias, got %d occurrences\n%s", count, output)
	}
	if !strings.Contains(output, "Trace ID: trace-response") {
		t.Fatalf("expected trace id from response in output:\n%s", output)
	}
}

func TestRenderPlainLowConfidenceFallback(t *testing.T) {
	resp := ipc.QueryResponse{
		Summary:    "Some backend-specific guidance that should be wrapped by the CLI.",
		Confidence: 0.14,
		NoAnswer:   true,
	}

	output := invokeRenderer(t, resp, driverOptions{
		ConfidenceThreshold: 0.35,
		TraceID:             "trace-low-confidence",
		Presenter:           "plain",
	})

	if !strings.Contains(output, "No answer found") {
		t.Fatalf("expected fallback block, got:\n%s", output)
	}
	if !strings.Contains(output, "Confidence 14% (threshold 35%)") {
		t.Fatalf("expected confidence percentage in fallback:\n%s", output)
	}
	if !strings.Contains(strings.ToLower(output), "rephrase your query") {
		t.Fatalf("expected guidance to rephrase query:\n%s", output)
	}
}

func TestRenderJSONIncludesTelemetryFields(t *testing.T) {
	resp := ipc.QueryResponse{
		Summary:            "Context truncated message from backend.",
		Citations:          []ipc.QueryCitation{{Alias: "man-pages", DocumentRef: "chmod(1)"}},
		Confidence:         0.62,
		TraceID:            "",
		LatencyMS:          512,
		RetrievalLatencyMS: ptr(220),
		LLMLatencyMS:       ptr(292),
		IndexVersion:       ptr("catalog/v1"),
		ContextTruncated:   true,
		SemanticChunkCount: ptr(7),
	}

	output := invokeRenderer(t, resp, driverOptions{
		ConfidenceThreshold: 0.5,
		TraceID:             "trace-from-cli",
		Presenter:           "json",
	})

	var payload map[string]any
	if err := json.Unmarshal([]byte(output), &payload); err != nil {
		t.Fatalf("decode json: %v\noutput:\n%s", err, output)
	}

	for _, key := range []string{"summary", "citations", "confidence", "confidence_threshold", "trace_id", "context_truncated"} {
		if _, ok := payload[key]; !ok {
			t.Fatalf("expected key %q in payload: %v", key, payload)
		}
	}
	if got := payload["trace_id"]; got != "trace-from-cli" {
		t.Fatalf("expected trace id fallback, got %v", got)
	}
	if got := payload["context_truncated"]; got != true {
		t.Fatalf("expected context_truncated true, got %v", got)
	}
	if got := payload["semantic_chunk_count"]; got != float64(7) {
		t.Fatalf("expected semantic_chunk_count 7, got %v", got)
	}
}

func TestRenderMarkdownContextTruncatedWarning(t *testing.T) {
	resp := ipc.QueryResponse{
		Summary:          "The retrieved context exceeded the configured token budget and was truncated.",
		Confidence:       0.91,
		ContextTruncated: true,
		TraceID:          "trace-truncation",
	}

	output := invokeRenderer(t, resp, driverOptions{
		ConfidenceThreshold: 0.35,
		TraceID:             "cli-trace",
		Presenter:           "markdown",
	})

	if !strings.Contains(output, "Context truncated") {
		t.Fatalf("expected truncation warning in output:\n%s", output)
	}
	if strings.Contains(output, "Steps") || strings.Contains(output, "References") {
		t.Fatalf("truncation fallback should omit steps and references:\n%s", output)
	}
}

func invokeRenderer(t *testing.T, resp ipc.QueryResponse, opts driverOptions) string {
	t.Helper()

	payload := driverPayload{
		Response: resp,
		Options:  opts,
	}

	data, err := json.Marshal(payload)
	if err != nil {
		t.Fatalf("marshal payload: %v", err)
	}

	cmd := exec.Command("go", "run", "./cli/ragman/internal/io/testdriver")
	cmd.Dir = findRepoRoot(t)
	cmd.Env = append(os.Environ(),
		fmt.Sprintf("GOCACHE=%s", filepath.Join(t.TempDir(), "gocache")),
	)
	cmd.Stdin = bytes.NewReader(data)

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr

	if err := cmd.Run(); err != nil {
		t.Fatalf("go run failed: %v\nstderr:\n%s", err, stderr.String())
	}

	var result driverResult
	if err := json.Unmarshal(stdout.Bytes(), &result); err != nil {
		t.Fatalf("decode driver output: %v\nstdout:\n%s", err, stdout.String())
	}
	if result.Error != "" {
		t.Fatalf("renderer returned error: %s", result.Error)
	}
	return result.Output
}

func findRepoRoot(t *testing.T) string {
	t.Helper()

	wd, err := os.Getwd()
	if err != nil {
		t.Fatalf("failed to determine working directory: %v", err)
	}

	dir := wd
	for {
		if _, err := os.Stat(filepath.Join(dir, "go.work")); err == nil {
			return dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			t.Fatalf("could not locate repository root from %s", wd)
		}
		dir = parent
	}
}

func requireContains(t *testing.T, haystack string, needles ...string) {
	t.Helper()
	for _, needle := range needles {
		if !strings.Contains(haystack, needle) {
			t.Fatalf("expected %q to contain %q", haystack, needle)
		}
	}
}

func ptr[T any](v T) *T {
	return &v
}
