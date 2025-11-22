package contract_test

import (
	"strings"
	"testing"
)

func TestRagadminSourcesUpdateMetadata(t *testing.T) {
	t.Parallel()

	scenario := ragadminScenario{
		name: "sources-update-metadata",
		args: []string{
			"--socket",
			"",
			"sources",
			"update",
			"man-pages",
			"--language",
			"en",
			"--status",
			"quarantined",
			"--notes",
			"Path missing on disk",
		},
		requestAssert: func(t *testing.T, frame map[string]any) {
			t.Helper()
			if path, _ := frame["path"].(string); path != "/v1/sources/man-pages" {
				t.Fatalf("expected update path to include alias, got %q", path)
			}
			body, _ := frame["body"].(map[string]any)
			if _, ok := body["alias"]; ok {
				t.Fatalf("alias must remain immutable, body should not include alias: %v", body)
			}
			if language, _ := body["language"].(string); language != "en" {
				t.Fatalf("expected language en, got %v", language)
			}
			if status, _ := body["status"].(string); status != "quarantined" {
				t.Fatalf("expected status quarantined, got %v", status)
			}
			if notes, _ := body["notes"].(string); !strings.Contains(notes, "Path missing") {
				t.Fatalf("expected notes to mention missing path, got %v", notes)
			}
		},
		responseBody: map[string]any{
			"source": map[string]any{
				"alias":        "man-pages",
				"type":         "man",
				"language":     "en",
				"status":       "quarantined",
				"location":     "/usr/share/man",
				"size_bytes":   5242880,
				"last_updated": "2024-11-03T10:15:00Z",
				"notes":        "Path missing on disk",
			},
		},
		outputAssert: func(t *testing.T, output string) {
			t.Helper()
			if !strings.Contains(output, "man-pages") {
				t.Fatalf("expected alias in output:\n%s", output)
			}
			if !strings.Contains(output, "metadata updated") {
				t.Fatalf("expected metadata confirmation in output:\n%s", output)
			}
			if !strings.Contains(output, "quarantined") {
				t.Fatalf("expected updated status in output:\n%s", output)
			}
		},
	}

	runRagadminScenario(t, scenario)
}
