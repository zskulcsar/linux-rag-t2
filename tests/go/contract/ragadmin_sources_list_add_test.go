package contract_test

import (
	"strings"
	"testing"
)

func TestRagadminSourcesListTableOutput(t *testing.T) {
	t.Parallel()

	scenario := ragadminScenario{
		name: "sources-list-table",
		args: []string{
			"--socket",
			"",
			"sources",
			"list",
		},
		requestAssert: func(t *testing.T, frame map[string]any) {
			t.Helper()
			if path, _ := frame["path"].(string); path != "/v1/sources" {
				t.Fatalf("expected list request to hit /v1/sources, got %q", path)
			}
			if frameType, _ := frame["type"].(string); frameType != "request" {
				t.Fatalf("expected request frame, got %q", frameType)
			}
			body, _ := frame["body"].(map[string]any)
			if _, ok := body["trace_id"].(string); !ok {
				t.Fatal("expected trace identifier to propagate for catalog listing")
			}
		},
		responseBody: map[string]any{
			"sources": []any{
				map[string]any{
					"alias":        "man-pages",
					"type":         "man",
					"language":     "en",
					"status":       "active",
					"location":     "/usr/share/man",
					"size_bytes":   409600,
					"last_updated": "2024-10-01T12:00:00Z",
				},
				map[string]any{
					"alias":        "linuxwiki",
					"type":         "kiwix",
					"language":     "en",
					"status":       "pending_validation",
					"location":     "/data/linuxwiki_en.zim",
					"size_bytes":   734003200,
					"last_updated": "2024-09-15T09:30:00Z",
				},
			},
			"updated_at": "2024-11-01T12:00:00Z",
			"trace_id":   "catalog-list-trace",
		},
		outputAssert: func(t *testing.T, output string) {
			t.Helper()
			if !strings.Contains(output, "ALIAS") {
				t.Fatalf("expected table header in output:\n%s", output)
			}
			for _, token := range []string{"man-pages", "/usr/share/man", "linuxwiki", "pending_validation"} {
				if !strings.Contains(output, token) {
					t.Fatalf("expected output to include %q:\n%s", token, output)
				}
			}
		},
	}

	runRagadminScenario(t, scenario)
}

func TestRagadminSourcesAddRequestPayload(t *testing.T) {
	t.Parallel()

	scenario := ragadminScenario{
		name: "sources-add-kiwix",
		args: []string{
			"--socket",
			"",
			"sources",
			"add",
			"--alias",
			"linuxwiki",
			"--type",
			"kiwix",
			"--path",
			"/data/linuxwiki_en.zim",
			"--language",
			"en",
			"--notes",
			"Offline Linux wiki snapshot",
			"--checksum",
			"abc123deadbeef",
		},
		requestAssert: func(t *testing.T, frame map[string]any) {
			t.Helper()
			if path, _ := frame["path"].(string); path != "/v1/sources" {
				t.Fatalf("expected add request to hit /v1/sources, got %q", path)
			}
			body, _ := frame["body"].(map[string]any)
			if alias, _ := body["alias"].(string); alias != "linuxwiki" {
				t.Fatalf("expected alias linuxwiki, got %v", alias)
			}
			if sourceType, _ := body["type"].(string); sourceType != "kiwix" {
				t.Fatalf("expected type kiwix, got %v", sourceType)
			}
			if location, _ := body["location"].(string); location != "/data/linuxwiki_en.zim" {
				t.Fatalf("expected location /data/linuxwiki_en.zim, got %v", location)
			}
			if language, _ := body["language"].(string); language != "en" {
				t.Fatalf("expected language en, got %v", language)
			}
			if notes, _ := body["notes"].(string); !strings.Contains(notes, "Offline") {
				t.Fatalf("expected notes to describe snapshot, got %v", notes)
			}
			if checksum, _ := body["checksum"].(string); checksum != "abc123deadbeef" {
				t.Fatalf("expected checksum abc123deadbeef, got %v", checksum)
			}
		},
		responseStatus: 201,
		responseBody: map[string]any{
			"source": map[string]any{
				"alias":        "linuxwiki",
				"type":         "kiwix",
				"language":     "en",
				"status":       "pending_validation",
				"location":     "/data/linuxwiki_en.zim",
				"size_bytes":   734003200,
				"checksum":     "abc123deadbeef",
				"last_updated": "2024-11-02T08:00:00Z",
			},
			"ingestion_job": map[string]any{
				"job_id":    "job-linuxwiki",
				"status":    "queued",
				"trigger":   "manual",
				"requested": "2024-11-02T08:00:00Z",
			},
		},
		outputAssert: func(t *testing.T, output string) {
			t.Helper()
			if !strings.Contains(output, "linuxwiki") {
				t.Fatalf("expected alias in output:\n%s", output)
			}
			if !strings.Contains(output, "queued for ingestion") {
				t.Fatalf("expected queued status in output:\n%s", output)
			}
		},
	}

	runRagadminScenario(t, scenario)
}
