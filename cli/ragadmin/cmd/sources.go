package cmd

import (
	"context"
	"encoding/json"
	"fmt"
	"io"
	"strings"
	"text/tabwriter"
	"time"

	"github.com/linux-rag-t2/cli/shared/ipc"
	"github.com/spf13/cobra"
)

const (
	mutationAdd    = "add"
	mutationUpdate = "update"
	mutationRemove = "remove"
)

func newSourcesCommand() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "sources",
		Short: "Manage knowledge sources",
		RunE: func(cmd *cobra.Command, _ []string) error {
			return cmd.Help()
		},
	}

	cmd.AddCommand(
		newSourcesListCommand(),
		newSourcesAddCommand(),
		newSourcesUpdateCommand(),
		newSourcesRemoveCommand(),
	)
	return cmd
}

func newSourcesListCommand() *cobra.Command {
	return &cobra.Command{
		Use:   "list",
		Short: "List catalogued knowledge sources",
		RunE: func(cmd *cobra.Command, _ []string) error {
			return runWithClient(cmd, func(ctx context.Context, state *runtimeState, client *ipc.Client) error {
				resp, err := client.ListSources(ctx, ipc.SourceListRequest{TraceID: ipc.NewTraceID()})
				if err != nil {
					return err
				}
				return renderSourceList(cmd.OutOrStdout(), state.OutputFormat, resp)
			})
		},
	}
}

func newSourcesAddCommand() *cobra.Command {
	var opts struct {
		alias      string
		sourceType string
		path       string
		language   string
		notes      string
		checksum   string
	}

	cmd := &cobra.Command{
		Use:   "add",
		Short: "Register a new knowledge source",
		RunE: func(cmd *cobra.Command, _ []string) error {
			opts.sourceType = strings.ToLower(strings.TrimSpace(opts.sourceType))
			if !isValidSourceType(opts.sourceType) {
				return fmt.Errorf("unsupported source type %q (expected man|kiwix|info)", opts.sourceType)
			}
			opts.path = strings.TrimSpace(opts.path)
			if opts.path == "" {
				return fmt.Errorf("path is required")
			}
			if opts.language = strings.TrimSpace(opts.language); opts.language == "" {
				opts.language = "en"
			}

			traceID := ipc.NewTraceID()
			req := ipc.SourceCreateRequest{
				TraceID:  traceID,
				Alias:    strings.TrimSpace(opts.alias),
				Type:     opts.sourceType,
				Location: opts.path,
				Language: opts.language,
				Notes:    strings.TrimSpace(opts.notes),
				Checksum: strings.TrimSpace(opts.checksum),
			}

			return runWithClient(cmd, func(ctx context.Context, state *runtimeState, client *ipc.Client) error {
				resp, err := client.CreateSource(ctx, req)
				if err != nil {
					return err
				}
				if err := renderSourceMutation(cmd.OutOrStdout(), state.OutputFormat, mutationAdd, resp); err != nil {
					return err
				}
				appendAuditEntry(state, "source_add", resp.Source.Alias, "success", traceID, fmt.Sprintf("location=%s", resp.Source.Location))
				return nil
			})
		},
	}

	cmd.Flags().StringVar(&opts.alias, "alias", "", "Optional alias override (defaults to filename)")
	cmd.Flags().StringVar(&opts.sourceType, "type", "", "Source type (man|kiwix|info)")
	cmd.Flags().StringVar(&opts.path, "path", "", "Path to the source content")
	cmd.Flags().StringVar(&opts.language, "language", "en", "Content language (default: en)")
	cmd.Flags().StringVar(&opts.notes, "notes", "", "Optional notes describing the source")
	cmd.Flags().StringVar(&opts.checksum, "checksum", "", "Optional checksum override")
	_ = cmd.MarkFlagRequired("type")
	_ = cmd.MarkFlagRequired("path")

	return cmd
}

func newSourcesUpdateCommand() *cobra.Command {
	var opts struct {
		path     string
		language string
		status   string
		notes    string
	}

	cmd := &cobra.Command{
		Use:   "update <alias>",
		Short: "Update source metadata",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			alias := strings.TrimSpace(args[0])
			if alias == "" {
				return fmt.Errorf("alias must be provided")
			}

			req := ipc.SourceUpdateRequest{
				TraceID: ipc.NewTraceID(),
			}

			if trimmed := strings.TrimSpace(opts.path); trimmed != "" {
				req.Location = trimmed
			}
			if trimmed := strings.TrimSpace(opts.language); trimmed != "" {
				req.Language = trimmed
			}
			if trimmed := strings.TrimSpace(opts.status); trimmed != "" {
				if !isValidSourceStatus(trimmed) {
					return fmt.Errorf("unsupported status %q (expected pending_validation|active|quarantined|error)", trimmed)
				}
				req.Status = trimmed
			}
			if trimmed := strings.TrimSpace(opts.notes); trimmed != "" {
				req.Notes = trimmed
			}

			if req.Location == "" && req.Language == "" && req.Status == "" && req.Notes == "" {
				return fmt.Errorf("at least one flag must be provided to update metadata")
			}

			traceID := req.TraceID
			return runWithClient(cmd, func(ctx context.Context, state *runtimeState, client *ipc.Client) error {
				resp, err := client.UpdateSource(ctx, alias, req)
				if err != nil {
					return err
				}
				if err := renderSourceMutation(cmd.OutOrStdout(), state.OutputFormat, mutationUpdate, resp); err != nil {
					return err
				}
				appendAuditEntry(state, "source_update", resp.Source.Alias, "success", traceID, "metadata updated")
				return nil
			})
		},
	}

	cmd.Flags().StringVar(&opts.path, "path", "", "New location for the source content")
	cmd.Flags().StringVar(&opts.language, "language", "", "New language code for the source")
	cmd.Flags().StringVar(&opts.status, "status", "", "Updated lifecycle status (pending_validation|active|quarantined|error)")
	cmd.Flags().StringVar(&opts.notes, "notes", "", "Replacement notes for the source")
	return cmd
}

func newSourcesRemoveCommand() *cobra.Command {
	var reason string

	cmd := &cobra.Command{
		Use:   "remove <alias>",
		Short: "Quarantine and remove a source from the active catalog",
		Args:  cobra.ExactArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			alias := strings.TrimSpace(args[0])
			if alias == "" {
				return fmt.Errorf("alias must be provided")
			}
			reason = strings.TrimSpace(reason)
			if reason == "" {
				return fmt.Errorf("reason must be provided")
			}

			req := ipc.SourceRemoveRequest{
				TraceID: ipc.NewTraceID(),
				Reason:  reason,
			}
			traceID := req.TraceID

			return runWithClient(cmd, func(ctx context.Context, state *runtimeState, client *ipc.Client) error {
				resp, err := client.RemoveSource(ctx, alias, req)
				if err != nil {
					return err
				}
				if err := renderSourceMutation(cmd.OutOrStdout(), state.OutputFormat, mutationRemove, resp); err != nil {
					return err
				}
				details := fmt.Sprintf("reason=%s", reason)
				appendAuditEntry(state, "source_remove", resp.Source.Alias, "success", traceID, details)
				return nil
			})
		},
	}

	cmd.Flags().StringVar(&reason, "reason", "", "Reason for removal/quarantine")
	_ = cmd.MarkFlagRequired("reason")
	return cmd
}

func renderSourceList(out io.Writer, format string, resp ipc.SourceListResponse) error {
	if format == "json" {
		data, err := json.MarshalIndent(resp, "", "  ")
		if err != nil {
			return err
		}
		_, err = out.Write(append(data, '\n'))
		return err
	}

	tw := tabwriter.NewWriter(out, 0, 4, 2, ' ', 0)
	if _, err := fmt.Fprintln(tw, "ALIAS\tTYPE\tSTATUS\tLANGUAGE\tSIZE\tLOCATION"); err != nil {
		return err
	}
	for _, src := range resp.Sources {
		if _, err := fmt.Fprintf(
			tw,
			"%s\t%s\t%s\t%s\t%s\t%s\n",
			src.Alias,
			strings.ToLower(src.Type),
			strings.ToLower(src.Status),
			src.Language,
			formatBytes(src.SizeBytes),
			src.Location,
		); err != nil {
			return err
		}
	}
	if err := tw.Flush(); err != nil {
		return err
	}
	_, err := fmt.Fprintf(out, "\nCatalog updated: %s\n", resp.UpdatedAt)
	return err
}

func renderSourceMutation(out io.Writer, format string, kind string, resp ipc.SourceMutationResponse) error {
	if format == "json" {
		data, err := json.MarshalIndent(resp, "", "  ")
		if err != nil {
			return err
		}
		_, err = out.Write(append(data, '\n'))
		return err
	}

	switch kind {
	case mutationAdd:
		if _, err := fmt.Fprintf(
			out,
			"Source %s queued for ingestion (status %s)\n",
			resp.Source.Alias,
			resp.Source.Status,
		); err != nil {
			return err
		}
		if resp.IngestionJob != nil {
			_, err := fmt.Fprintf(
				out,
				"Ingestion job %s (%s) requested at %s\n",
				resp.IngestionJob.JobID,
				resp.IngestionJob.Status,
				resp.IngestionJob.RequestedAt,
			)
			return err
		}
	case mutationUpdate:
		_, err := fmt.Fprintf(
			out,
			"metadata updated for %s (status %s)\n",
			resp.Source.Alias,
			resp.Source.Status,
		)
		return err
	case mutationRemove:
		if _, err := fmt.Fprintf(
			out,
			"Source %s quarantined (status %s)\n",
			resp.Source.Alias,
			resp.Source.Status,
		); err != nil {
			return err
		}
		if resp.Quarantine != nil && resp.Quarantine.Reason != "" {
			_, err := fmt.Fprintf(out, "Reason: %s\n", resp.Quarantine.Reason)
			return err
		}
	}
	return nil
}

func formatBytes(size int64) string {
	const unit = 1024
	if size <= 0 {
		return "0B"
	}
	if size < unit {
		return fmt.Sprintf("%dB", size)
	}
	div, exp := int64(unit), 0
	for n := size / unit; n >= unit; n /= unit {
		div *= unit
		exp++
	}
	value := float64(size) / float64(div)
	return fmt.Sprintf("%.1f%ciB", value, "KMGTPE"[exp])
}

func isValidSourceType(value string) bool {
	switch strings.ToLower(value) {
	case "man", "kiwix", "info":
		return true
	default:
		return false
	}
}

func isValidSourceStatus(value string) bool {
	switch strings.ToLower(value) {
	case "pending_validation", "active", "quarantined", "error":
		return true
	default:
		return false
	}
}

func appendAuditEntry(state *runtimeState, action, target, status, traceID, details string) {
	if state == nil || state.AuditLogger == nil {
		return
	}

	entry := map[string]any{
		"timestamp": time.Now().UTC().Format(time.RFC3339Nano),
		"actor":     "ragadmin",
		"action":    action,
		"target":    target,
		"status":    status,
	}
	if traceID != "" {
		entry["trace_id"] = traceID
	}
	if details != "" {
		entry["details"] = details
	}
	_ = state.AuditLogger.Append(entry)
}
