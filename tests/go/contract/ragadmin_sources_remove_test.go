package contract_test

import (
	"strings"
	"testing"
)

func TestRagadminSourcesRemoveQuarantinesSource(t *testing.T) {
	t.Parallel()

	scenario := ragadminScenario{
		name: "sources-remove-quarantine",
		args: []string{
			"--socket",
			"",
			"sources",
			"remove",
			"linuxwiki",
			"--reason",
			"Duplicate content detected",
		},
		requestAssert: func(t *testing.T, frame map[string]any) {
			t.Helper()
			if path, _ := frame["path"].(string); path != "/v1/sources/linuxwiki" {
				t.Fatalf("expected remove request to target alias path, got %q", path)
			}
			body, _ := frame["body"].(map[string]any)
			if reason, _ := body["reason"].(string); !strings.Contains(reason, "Duplicate") {
				t.Fatalf("expected removal reason to describe duplicate content, got %v", reason)
			}
		},
		responseStatus: 202,
		responseBody: map[string]any{
			"source": map[string]any{
				"alias":    "linuxwiki",
				"status":   "quarantined",
				"location": "/data/linuxwiki_en.zim",
				"type":     "kiwix",
			},
			"quarantine": map[string]any{
				"reason":     "Duplicate content detected",
				"requested":  "2024-11-04T09:00:00Z",
				"trace_id":   "remove-trace",
				"documents":  128,
				"next_steps": "Re-add once deduplicated",
			},
		},
		outputAssert: func(t *testing.T, output string) {
			t.Helper()
			if !strings.Contains(output, "linuxwiki") {
				t.Fatalf("expected alias in output:\n%s", output)
			}
			if !strings.Contains(output, "quarantined") {
				t.Fatalf("expected quarantine status in output:\n%s", output)
			}
			if !strings.Contains(output, "Duplicate content detected") {
				t.Fatalf("expected removal reason echoed in output:\n%s", output)
			}
		},
	}

	runRagadminScenario(t, scenario)
}
