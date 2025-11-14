package contract_test

import (
	"strings"
	"testing"
)

func TestRagadminReindexShowsProgress(t *testing.T) {
	t.Parallel()

	scenario := ragadminScenario{
		name: "reindex-progress",
		args: []string{
			"--socket",
			"",
			"reindex",
			"--trigger",
			"manual",
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
		responseStatus: 202,
		responseBody: map[string]any{
			"job": map[string]any{
				"job_id":              "job-123",
				"source_alias":        "*",
				"status":              "succeeded",
				"requested_at":        "2024-11-01T00:00:00Z",
				"started_at":          "2024-11-01T00:00:01Z",
				"completed_at":        "2024-11-01T00:00:10Z",
				"documents_processed": 2048,
				"stage":               "writing",
				"percent_complete":    100,
				"trigger":             "manual",
			},
		},
		outputAssert: func(t *testing.T, output string) {
			t.Helper()
			if !strings.Contains(output, "Reindex succeeded") {
				t.Fatalf("expected success message in output:\n%s", output)
			}
			if !strings.Contains(output, "Stage: writing (100%)") {
				t.Fatalf("expected stage line in output:\n%s", output)
			}
			if !strings.Contains(output, "Duration:") {
				t.Fatalf("expected duration line in output:\n%s", output)
			}
		},
	}

	runRagadminScenario(t, scenario)
}
