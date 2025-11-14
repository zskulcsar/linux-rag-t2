package cmd

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log/slog"
	"strings"
	"text/tabwriter"
	"time"

	"github.com/linux-rag-t2/cli/shared/ipc"
	"github.com/spf13/cobra"
)

// newHealthCommand returns the Cobra subcommand that executes `ragadmin health`.
func newHealthCommand() *cobra.Command {
	return &cobra.Command{
		Use:   "health",
		Short: "Display dependency and storage health",
		RunE: func(cmd *cobra.Command, _ []string) error {
			req := ipc.HealthRequest{TraceID: ipc.NewTraceID()}
			started := time.Now()

			return runWithClient(cmd, func(ctx context.Context, state *runtimeState, client *ipc.Client) error {
				logger := loggerForState(state).With(slog.String("trace_id", req.TraceID))
				logger.Info("ragadmin.health :: request")

				summary, err := client.HealthCheck(ctx, req)
				if err != nil {
					logger.Error("ragadmin.health :: error", slog.String("error", err.Error()))
					return err
				}

				logger.Info(
					"ragadmin.health :: success",
					slog.Duration("duration", time.Since(started)),
					slog.String("overall", strings.ToUpper(summary.OverallStatus)),
				)

				if err := renderHealthSummary(cmd.OutOrStdout(), state.OutputFormat, summary); err != nil {
					return err
				}

				appendAuditEntry(
					state,
					"admin_health",
					"*",
					"success",
					summary.TraceID,
					fmt.Sprintf("overall=%s", strings.ToLower(summary.OverallStatus)),
				)
				return nil
			})
		},
	}
}

// renderHealthSummary writes the health summary to stdout using the requested format.
func renderHealthSummary(out io.Writer, format string, summary ipc.HealthSummary) error {
	if format == "json" {
		data, err := json.MarshalIndent(summary, "", "  ")
		if err != nil {
			return err
		}
		_, err = out.Write(append(data, '\n'))
		return err
	}

	if _, err := fmt.Fprintf(out, "Overall Status: %s\n", strings.ToUpper(summary.OverallStatus)); err != nil {
		return err
	}
	if summary.TraceID != "" {
		if _, err := fmt.Fprintf(out, "Trace ID: %s\n", summary.TraceID); err != nil {
			return err
		}
	}

	if len(summary.Results) == 0 {
		_, err := fmt.Fprintln(out, "No component checks reported.")
		return err
	}

	tw := tabwriter.NewWriter(out, 0, 4, 2, ' ', 0)
	if _, err := fmt.Fprintln(tw, "COMPONENT\tSTATUS\tDETAILS"); err != nil {
		return err
	}
	for _, result := range summary.Results {
		component := formatComponentName(result.Component)
		status := strings.ToUpper(result.Status)
		if status == "" {
			status = "UNKNOWN"
		}
		if _, err := fmt.Fprintf(tw, "%s\t%s\t%s\n", component, status, result.Message); err != nil {
			return err
		}
		if trimmed := strings.TrimSpace(result.Remediation); trimmed != "" {
			if _, err := fmt.Fprintf(tw, "  Remediation\t\t%s\n", trimmed); err != nil {
				return err
			}
		}
	}
	if err := tw.Flush(); err != nil {
		return err
	}
	return nil
}
