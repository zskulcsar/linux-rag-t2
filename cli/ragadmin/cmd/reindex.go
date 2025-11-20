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
		force   bool
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
				Force:   opts.force,
			}
			started := time.Now()

			return runWithClient(cmd, func(ctx context.Context, state *runtimeState, client *ipc.Client) error {
				renderer := newReindexProgressRenderer(cmd.OutOrStdout(), state.OutputFormat)
				job, streamErr := client.StartReindexStream(ctx, req, func(job ipc.IngestionJob) error {
					return renderer.Handle(job)
				})
				elapsed := time.Since(started)

				if err := renderer.Complete(job, elapsed); err != nil {
					return err
				}

				status := normalizedJobStatus(job)
				target := job.SourceAlias
				if target == "" {
					target = "*"
				}
				details := fmt.Sprintf("stage=%s", strings.TrimSpace(job.Stage))
				appendAuditEntry(state, "index_reindex", target, status, req.TraceID, details)

				if streamErr != nil {
					return streamErr
				}

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
	cmd.Flags().BoolVar(&opts.force, "force", false, "Force rebuild even if source checksums are unchanged")
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

	status := normalizedJobStatus(job)
	statusLine := fmt.Sprintf("Reindex %s (job %s)", status, job.JobID)
	stage := strings.TrimSpace(job.Stage)
	if stage == "" {
		stage = status
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

type reindexProgressRenderer struct {
	out           io.Writer
	format        string
	lastLineWidth int
	wroteProgress bool
}

func newReindexProgressRenderer(out io.Writer, format string) *reindexProgressRenderer {
	return &reindexProgressRenderer{
		out:    out,
		format: format,
	}
}

func (r *reindexProgressRenderer) Handle(job ipc.IngestionJob) error {
	if r.format == "json" {
		payload := map[string]any{
			"event": "progress",
			"job":   job,
		}
		data, err := json.Marshal(payload)
		if err != nil {
			return err
		}
		_, err = r.out.Write(append(data, '\n'))
		return err
	}

	line := r.buildProgressLine(job)
	padding := ""
	if r.lastLineWidth > len(line) {
		padding = strings.Repeat(" ", r.lastLineWidth-len(line))
	}
	r.lastLineWidth = len(line)
	r.wroteProgress = true
	_, err := fmt.Fprintf(r.out, "\r%s%s", line, padding)
	return err
}

func (r *reindexProgressRenderer) Complete(job ipc.IngestionJob, elapsed time.Duration) error {
	if r.format == "json" {
		payload := map[string]any{
			"event":       "summary",
			"job":         job,
			"duration_ms": elapsed.Milliseconds(),
		}
		data, err := json.Marshal(payload)
		if err != nil {
			return err
		}
		_, err = r.out.Write(append(data, '\n'))
		return err
	}

	if r.wroteProgress {
		if _, err := fmt.Fprint(r.out, "\n"); err != nil {
			return err
		}
	}
	return renderReindexResult(r.out, "table", job, elapsed)
}

func (r *reindexProgressRenderer) buildProgressLine(job ipc.IngestionJob) string {
	status := normalizedJobStatus(job)
	stage := formatProgressStage(job)
	line := fmt.Sprintf("Reindex %s — Stage: %s", status, stage)
	if job.DocumentsProcessed > 0 {
		line = fmt.Sprintf("%s docs=%d", line, job.DocumentsProcessed)
	}
	return line
}

func formatProgressStage(job ipc.IngestionJob) string {
	stage := strings.TrimSpace(job.Stage)
	if stage == "" {
		stage = normalizedJobStatus(job)
	}
	if job.PercentComplete != nil {
		return fmt.Sprintf("%s (%s)", stage, formatPercent(*job.PercentComplete))
	}
	return stage
}

func normalizedJobStatus(job ipc.IngestionJob) string {
	status := strings.ToLower(strings.TrimSpace(job.Status))
	if status == "" {
		status = "running"
	}
	if job.ErrorMessage != "" && status == "succeeded" {
		return "failed"
	}
	return status
}
