package contract_test

// Streaming requirements reference:
// tmp/specs/001-rag-cli/20-11-2025-ragadmin-reindex-streaming-design.md.

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestRagadminReindexStreamsProgressTTY(t *testing.T) {
	t.Parallel()

	stream := []ragadminStreamFrame{
		{
			status: 202,
			body: map[string]any{
				"job": map[string]any{
					"job_id":              "job-tty",
					"status":              "running",
					"stage":               "discovering",
					"percent_complete":    5,
					"documents_processed": 16,
					"requested_at":        "2025-11-20T00:00:00Z",
				},
			},
		},
		{
			status: 202,
			body: map[string]any{
				"job": map[string]any{
					"job_id":              "job-tty",
					"status":              "running",
					"stage":               "chunking",
					"percent_complete":    45,
					"documents_processed": 128,
					"requested_at":        "2025-11-20T00:00:05Z",
				},
			},
		},
		{
			status: 202,
			body: map[string]any{
				"job": map[string]any{
					"job_id":              "job-tty",
					"status":              "succeeded",
					"stage":               "completed",
					"percent_complete":    100,
					"documents_processed": 256,
					"completed_at":        "2025-11-20T00:00:12Z",
				},
			},
		},
	}

	scenario := ragadminScenario{
		name: "reindex-stream-tty",
		args: []string{
			"--socket",
			"",
			"reindex",
			"--trigger",
			"manual",
		},
		env: map[string]string{
			"RAG_BACKEND_FAKE_SERVICES": "1",
		},
		requestAssert: func(t *testing.T, frame map[string]any) {
			t.Helper()
			if path, _ := frame["path"].(string); path != "/v1/index/reindex" {
				t.Fatalf("expected reindex path, got %q", path)
			}
			body, _ := frame["body"].(map[string]any)
			if trigger, _ := body["trigger"].(string); trigger != "manual" {
				t.Fatalf("expected trigger manual, got %v", trigger)
			}
		},
		responseStream: stream,
		outputAssert: func(t *testing.T, output string) {
			t.Helper()
			if !strings.Contains(output, "Reindex succeeded") {
				t.Fatalf("expected success message in output:\n%s", output)
			}
			if strings.Count(output, "\r") < 2 {
				t.Fatalf("expected in-place progress updates, got output:\n%s", output)
			}
			if !strings.Contains(output, "discovering (5%)") {
				t.Fatalf("expected discovering stage in output:\n%s", output)
			}
			if !strings.Contains(output, "chunking (45%)") {
				t.Fatalf("expected chunking stage in output:\n%s", output)
			}
			if !strings.Contains(output, "docs=128") {
				t.Fatalf("expected documents processed in progress line:\n%s", output)
			}
		},
	}

	runRagadminScenario(t, scenario)
}

func TestRagadminReindexStreamsProgressJSON(t *testing.T) {
	t.Parallel()

	stream := []ragadminStreamFrame{
		{
			status: 202,
			body: map[string]any{
				"job": map[string]any{
					"job_id":              "job-json",
					"status":              "running",
					"stage":               "discovering",
					"percent_complete":    10,
					"documents_processed": 64,
					"requested_at":        "2025-11-20T01:00:00Z",
				},
			},
		},
		{
			status: 202,
			body: map[string]any{
				"job": map[string]any{
					"job_id":              "job-json",
					"status":              "running",
					"stage":               "embedding",
					"percent_complete":    60,
					"documents_processed": 512,
					"requested_at":        "2025-11-20T01:00:15Z",
				},
			},
		},
		{
			status: 202,
			body: map[string]any{
				"job": map[string]any{
					"job_id":              "job-json",
					"status":              "succeeded",
					"stage":               "completed",
					"percent_complete":    100,
					"documents_processed": 1024,
					"completed_at":        "2025-11-20T01:00:40Z",
				},
			},
		},
	}

	scenario := ragadminScenario{
		name: "reindex-stream-json",
		args: []string{
			"--socket",
			"",
			"--output",
			"json",
			"reindex",
			"--trigger",
			"manual",
		},
		env: map[string]string{
			"RAG_BACKEND_FAKE_SERVICES": "1",
		},
		requestAssert: func(t *testing.T, frame map[string]any) {
			t.Helper()
			if path, _ := frame["path"].(string); path != "/v1/index/reindex" {
				t.Fatalf("expected reindex path, got %q", path)
			}
		},
		responseStream: stream,
		outputAssert: func(t *testing.T, output string) {
			t.Helper()
			lines := strings.Split(strings.TrimSpace(output), "\n")
			if len(lines) != len(stream)+1 {
				t.Fatalf("expected %d progress events plus summary, got %d\n%s", len(stream)+1, len(lines), output)
			}
			for idx, line := range lines {
				var payload map[string]any
				if err := json.Unmarshal([]byte(line), &payload); err != nil {
					t.Fatalf("line %d is not valid json: %v\n%s", idx, err, line)
				}
				event, _ := payload["event"].(string)
				if idx < len(stream) && event != "progress" {
					t.Fatalf("expected progress event at line %d, got %q", idx, event)
				}
				if idx == len(stream) && event != "summary" {
					t.Fatalf("expected summary event at line %d, got %q", idx, event)
				}
			}
		},
	}

	runRagadminScenario(t, scenario)
}

func TestRagadminReindexTreatsErrorMessageAsFailure(t *testing.T) {
	t.Parallel()

	stream := []ragadminStreamFrame{
		{
			status: 202,
			body: map[string]any{
				"job": map[string]any{
					"job_id":           "job-error",
					"status":           "running",
					"stage":            "chunking",
					"percent_complete": 50,
				},
			},
		},
		{
			status: 202,
			body: map[string]any{
				"job": map[string]any{
					"job_id":           "job-error",
					"status":           "succeeded",
					"stage":            "completed",
					"percent_complete": 100,
					"error_message":    "vector ingest failed",
				},
			},
		},
	}

	scenario := ragadminScenario{
		name: "reindex-error-message",
		args: []string{
			"--socket",
			"",
			"reindex",
		},
		expectError:    true,
		responseStream: stream,
		outputAssert: func(t *testing.T, output string) {
			t.Helper()
			if !strings.Contains(output, "vector ingest failed") {
				t.Fatalf("expected error message in output:\n%s", output)
			}
			if !strings.Contains(output, "Reindex failed") {
				t.Fatalf("expected failure summary in output:\n%s", output)
			}
		},
	}

	runRagadminScenario(t, scenario)
}

func TestRagadminReindexForceFlag(t *testing.T) {
	t.Parallel()

	scenario := ragadminScenario{
		name: "reindex-force-flag",
		args: []string{
			"--socket",
			"",
			"reindex",
			"--force",
		},
		requestAssert: func(t *testing.T, frame map[string]any) {
			t.Helper()
			body, _ := frame["body"].(map[string]any)
			if force, _ := body["force"].(bool); !force {
				t.Fatalf("expected force flag to be true, body=%v", body)
			}
		},
		responseStream: []ragadminStreamFrame{
			{
				status: 202,
				body: map[string]any{
					"job": map[string]any{
						"job_id": "job-force",
						"status": "running",
						"stage":  "discovering",
					},
				},
			},
			{
				status: 200,
				body: map[string]any{
					"job": map[string]any{
						"job_id":           "job-force",
						"status":           "succeeded",
						"stage":            "completed",
						"percent_complete": 100,
					},
				},
			},
		},
	}

	runRagadminScenario(t, scenario)
}
