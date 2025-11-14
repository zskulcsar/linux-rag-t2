package cmd

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"text/tabwriter"
	"time"

	"github.com/linux-rag-t2/cli/shared/ipc"
	"github.com/spf13/cobra"
)

// newInitCommand returns the Cobra subcommand that runs `ragadmin init`.
func newInitCommand() *cobra.Command {
	return &cobra.Command{
		Use:   "init",
		Short: "Initialize ragcli directories and seed default sources",
		RunE: func(cmd *cobra.Command, _ []string) error {
			req := ipc.InitRequest{TraceID: ipc.NewTraceID()}
			started := time.Now()

			return runWithClient(cmd, func(ctx context.Context, state *runtimeState, client *ipc.Client) error {
				logger := loggerForState(state).With(slog.String("trace_id", req.TraceID))
				logger.Info("ragadmin.init :: request")

				kiwixDir, err := ensureKiwixDataDir(state)
				if err != nil {
					logger.Error("ragadmin.init :: kiwix_dir_error", slog.String("error", err.Error()))
					return err
				}

				resp, err := client.InitSystem(ctx, req)
				if err != nil {
					logger.Error("ragadmin.init :: error", slog.String("error", err.Error()))
					return err
				}

				duration := time.Since(started)
				logger.Info(
					"ragadmin.init :: success",
					slog.Duration("duration", duration),
					slog.Int("catalog_version", resp.CatalogVersion),
				)

				if err := renderInitSummary(cmd.OutOrStdout(), state.OutputFormat, resp, kiwixDir); err != nil {
					return err
				}

				appendAuditEntry(
					state,
					"admin_init",
					"*",
					"success",
					resp.TraceID,
					fmt.Sprintf("catalog_version=%d", resp.CatalogVersion),
				)
				return nil
			})
		},
	}
}

// renderInitSummary writes the init response to stdout using the selected format.
func renderInitSummary(out io.Writer, format string, resp ipc.InitResponse, kiwixDir string) error {
	if format == "json" {
		payload := map[string]any{
			"init":         resp,
			"kiwix_dir":    kiwixDir,
			"seeded_count": len(resp.SeededSources),
		}
		data, err := json.MarshalIndent(payload, "", "  ")
		if err != nil {
			return err
		}
		_, err = out.Write(append(data, '\n'))
		return err
	}

	if _, err := fmt.Fprintf(out, "Catalog Version: %d\n", resp.CatalogVersion); err != nil {
		return err
	}
	if kiwixDir != "" {
		if _, err := fmt.Fprintf(out, "Kiwix Data: %s\n", kiwixDir); err != nil {
			return err
		}
	}
	if len(resp.CreatedDirectories) > 0 {
		if _, err := fmt.Fprintln(out, "Created:"); err != nil {
			return err
		}
		for _, dir := range resp.CreatedDirectories {
			if _, err := fmt.Fprintf(out, "  - %s\n", dir); err != nil {
				return err
			}
		}
	}

	if _, err := fmt.Fprintln(out, "Seeded Sources:"); err != nil {
		return err
	}
	if len(resp.SeededSources) == 0 {
		if _, err := fmt.Fprintln(out, "  (no new sources)"); err != nil {
			return err
		}
	} else {
		tw := tabwriter.NewWriter(out, 0, 4, 2, ' ', 0)
		if _, err := fmt.Fprintln(tw, "ALIAS\tTYPE\tSTATUS\tLOCATION"); err != nil {
			return err
		}
		for _, source := range resp.SeededSources {
			line := fmt.Sprintf(
				"%s\t%s\t%s\t%s",
				source.Alias,
				strings.ToUpper(source.Type),
				strings.ToUpper(source.Status),
				source.Location,
			)
			if _, err := fmt.Fprintln(tw, line); err != nil {
				return err
			}
		}
		if err := tw.Flush(); err != nil {
			return err
		}
	}

	if len(resp.DependencyChecks) > 0 {
		if _, err := fmt.Fprintln(out, "Dependencies:"); err != nil {
			return err
		}
		for _, check := range resp.DependencyChecks {
			line := fmt.Sprintf(
				"  - %s: %s (%s)",
				formatComponentName(check.Component),
				strings.ToUpper(check.Status),
				check.Message,
			)
			if _, err := fmt.Fprintln(out, line); err != nil {
				return err
			}
			if check.Remediation != "" {
				if _, err := fmt.Fprintf(out, "      Remediation: %s\n", check.Remediation); err != nil {
					return err
				}
			}
		}
	}

	return nil
}

// ensureKiwixDataDir creates the kiwix data directory using the best candidate path.
func ensureKiwixDataDir(state *runtimeState) (string, error) {
	candidates := kiwixDirCandidates(state)
	seen := make(map[string]struct{}, len(candidates))

	var firstErr error
	for _, dir := range candidates {
		dir = strings.TrimSpace(dir)
		if dir == "" {
			continue
		}
		if _, ok := seen[dir]; ok {
			continue
		}
		seen[dir] = struct{}{}

		if err := os.MkdirAll(dir, 0o755); err != nil {
			if firstErr == nil {
				firstErr = err
			}
			continue
		}
		return dir, nil
	}
	if firstErr != nil {
		return "", fmt.Errorf("ragadmin: create kiwix directory: %w", firstErr)
	}
	return "", fmt.Errorf("ragadmin: unable to determine kiwix directory")
}

// kiwixDirCandidates returns ordered directory candidates for kiwix data.
func kiwixDirCandidates(state *runtimeState) []string {
	var candidates []string

	if custom := strings.TrimSpace(os.Getenv("RAGCLI_DATA_HOME")); custom != "" {
		candidates = append(candidates, filepath.Join(custom, "kiwix"))
	}
	if dataHome := strings.TrimSpace(os.Getenv("XDG_DATA_HOME")); dataHome != "" {
		candidates = append(candidates, filepath.Join(dataHome, "ragcli", "kiwix"))
	}
	if state != nil && strings.TrimSpace(state.ConfigPath) != "" {
		configDir := filepath.Dir(state.ConfigPath)
		candidates = append(candidates, filepath.Join(configDir, "kiwix"))
	}
	if runtimeDir := strings.TrimSpace(os.Getenv("XDG_RUNTIME_DIR")); runtimeDir != "" {
		candidates = append(candidates, filepath.Join(runtimeDir, "ragcli", "kiwix"))
	}
	if home, err := os.UserHomeDir(); err == nil && strings.TrimSpace(home) != "" {
		candidates = append(candidates, filepath.Join(home, ".local", "share", "ragcli", "kiwix"))
	}
	return candidates
}
