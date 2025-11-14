package contract_test

import (
	"strings"
	"testing"
)

func TestRagadminInitDisplaysCreatedDirectories(t *testing.T) {
	t.Parallel()

	scenario := ragadminScenario{
		name: "admin-init",
		args: []string{
			"--socket",
			"",
			"init",
		},
		requestAssert: func(t *testing.T, frame map[string]any) {
			t.Helper()
			if path, _ := frame["path"].(string); path != "/v1/admin/init" {
				t.Fatalf("expected init request to hit /v1/admin/init, got %q", path)
			}
		},
		responseBody: map[string]any{
			"catalog_version": 5,
			"created_directories": []any{
				"/home/example/.config/ragcli",
				"/home/example/.local/share/ragcli",
				"/tmp/ragcli",
			},
			"seeded_sources": []any{
				map[string]any{
					"alias":        "man-pages",
					"type":         "man",
					"location":     "/usr/share/man",
					"language":     "en",
					"status":       "active",
					"last_updated": "2024-11-03T08:12:00Z",
				},
				map[string]any{
					"alias":        "info-pages",
					"type":         "info",
					"location":     "/usr/share/info",
					"language":     "en",
					"status":       "active",
					"last_updated": "2024-11-03T08:12:00Z",
				},
			},
		},
		outputAssert: func(t *testing.T, output string) {
			t.Helper()
			for _, token := range []string{"Created:", ".config/ragcli", "man-pages", "info-pages"} {
				if !strings.Contains(output, token) {
					t.Fatalf("expected init output to mention %q:\n%s", token, output)
				}
			}
		},
	}

	runRagadminScenario(t, scenario)
}

func TestRagadminHealthDisplaysComponentStatuses(t *testing.T) {
	t.Parallel()

	scenario := ragadminScenario{
		name: "admin-health",
		args: []string{
			"--socket",
			"",
			"health",
		},
		requestAssert: func(t *testing.T, frame map[string]any) {
			t.Helper()
			if path, _ := frame["path"].(string); path != "/v1/admin/health" {
				t.Fatalf("expected health request to hit /v1/admin/health, got %q", path)
			}
		},
		responseBody: map[string]any{
			"overall_status": "warn",
			"trace_id":       "admin-health-trace",
			"results": []any{
				map[string]any{
					"component":   "disk_capacity",
					"status":      "warn",
					"message":     "9% free space remaining",
					"remediation": "Delete temporary files or expand the partition.",
				},
				map[string]any{
					"component": "ollama",
					"status":    "pass",
					"message":   "Local models loaded",
				},
				map[string]any{
					"component": "weaviate",
					"status":    "pass",
					"message":   "Cluster ready",
				},
			},
		},
		outputAssert: func(t *testing.T, output string) {
			t.Helper()
			for _, token := range []string{"Disk Capacity", "WARN", "9% free", "Ollama", "Weaviate"} {
				if !strings.Contains(output, token) {
					t.Fatalf("expected health output to include %q:\n%s", token, output)
				}
			}
		},
	}

	runRagadminScenario(t, scenario)
}
