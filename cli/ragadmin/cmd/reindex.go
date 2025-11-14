package cmd

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"math"
	"strings"
	"time"

	"github.com/linux-rag-t2/cli/shared/ipc"
	"github.com/spf13/cobra"
)

func newReindexCommand() *cobra.Command {
	var opts struct {
		trigger string
	}

	cmd := &cobra.Command{
		Use:   "reindex",
		Short: "Trigger an index rebuild and display progress",
		RunE: func(cmd *cobra.Command, _ []string) error {
			trigger := strings.ToLower(strings.TrimSpace(opts.trigger))
			if trigger == "" {
				trigger = "manual"
			}
			if !isValidTrigger(trigger) {
				return fmt.Errorf("unsupported trigger %q (expected manual|init|scheduled)", trigger)
			}

			req := ipc.ReindexRequest{
				TraceID: ipc.NewTraceID(),
				Trigger: trigger,
			}
			started := time.Now()

			return runWithClient(cmd, func(ctx context.Context, state *runtimeState, client *ipc.Client) error {
				job, err := client.StartReindex(ctx, req)
				elapsed := time.Since(started)
				if err != nil {
					return err
				}

				if err := renderReindexResult(cmd.OutOrStdout(), state.OutputFormat, job, elapsed); err != nil {
					return err
				}

				status := strings.ToLower(job.Status)
				target := job.SourceAlias
				if target == "" {
					target = "*"
				}
				details := fmt.Sprintf("stage=%s", strings.TrimSpace(job.Stage))
				appendAuditEntry(state, "index_reindex", target, status, req.TraceID, details)

				if status != "succeeded" {
					if job.ErrorMessage != "" {
						return fmt.Errorf("reindex failed: %s", job.ErrorMessage)
					}
					return fmt.Errorf("reindex finished with status %s", job.Status)
				}
				return nil
			})
		},
	}

	cmd.Flags().StringVar(&opts.trigger, "trigger", "manual", "Reindex trigger (manual|init|scheduled)")
	return cmd
}

func renderReindexResult(out io.Writer, format string, job ipc.IngestionJob, elapsed time.Duration) error {
	if format == "json" {
		payload := map[string]any{
			"job":         job,
			"duration_ms": elapsed.Milliseconds(),
		}
		data, err := json.MarshalIndent(payload, "", "  ")
		if err != nil {
			return err
		}
		_, err = out.Write(append(data, '\n'))
		return err
	}

	statusLine := fmt.Sprintf("Reindex %s (job %s)", strings.ToLower(job.Status), job.JobID)
	stage := strings.TrimSpace(job.Stage)
	if stage == "" {
		stage = strings.ToLower(job.Status)
	}
	stageLine := fmt.Sprintf("Stage: %s", stage)
	if job.PercentComplete != nil {
		stageLine = fmt.Sprintf("Stage: %s (%s)", stage, formatPercent(*job.PercentComplete))
	}

	if _, err := fmt.Fprintln(out, statusLine); err != nil {
		return err
	}
	if _, err := fmt.Fprintln(out, stageLine); err != nil {
		return err
	}
	if job.ErrorMessage != "" {
		if _, err := fmt.Fprintf(out, "Error: %s\n", job.ErrorMessage); err != nil {
			return err
		}
	}
	_, err := fmt.Fprintf(out, "Duration: %s\n", formatDuration(elapsed))
	return err
}

func formatPercent(value float64) string {
	return fmt.Sprintf("%d%%", int(math.Round(value)))
}

func formatDuration(d time.Duration) string {
	if d < time.Millisecond {
		return d.String()
	}
	return d.Round(10 * time.Millisecond).String()
}

func isValidTrigger(value string) bool {
	switch strings.ToLower(strings.TrimSpace(value)) {
	case "manual", "init", "scheduled":
		return true
	default:
		return false
	}
}
