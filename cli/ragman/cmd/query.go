package cmd

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"errors"
	"fmt"
	"io"
	"log/slog"
	"strings"
	"time"

	"github.com/spf13/cobra"

	renderio "github.com/linux-rag-t2/cli/ragman/internal/io"
	"github.com/linux-rag-t2/cli/shared/ipc"
)

// newQueryCommand constructs the `query` subcommand responsible for invoking the backend.
func newQueryCommand() *cobra.Command {
	var (
		usePlain         bool
		useJSON          bool
		conversationID   string
		maxContextTokens int
		queryTimeoutSecs = 30
	)

	cmd := &cobra.Command{
		Use:   "query [question]",
		Short: "Query the local RAG backend for Linux guidance",
		Long:  "query sends the provided question to the local RAG backend and prints the structured answer with citations.",
		Args: func(cmd *cobra.Command, args []string) error {
			if len(args) == 0 {
				return errors.New("ragman: question must be provided")
			}
			return nil
		},
		RunE: func(cmd *cobra.Command, args []string) error {
			if usePlain && useJSON {
				return errors.New("ragman: --plain and --json cannot be used together")
			}

			state, err := obtainState(cmd)
			if err != nil {
				return err
			}

			format := resolveFormat(usePlain, useJSON, state.Config.Presenter())
			question := strings.TrimSpace(strings.Join(args, " "))
			traceID := newTraceID()
			logger := state.Logger.With(
				slog.String("command", "query"),
				slog.String("trace_id", traceID),
			)
			logger.Info(
				"ragman query started",
				slog.String("presenter", string(format)),
				slog.String("conversation_id", strings.TrimSpace(conversationID)),
				slog.Int("context_tokens", maxContextTokens),
			)

			ctx, cancel := context.WithTimeout(cmd.Context(), time.Duration(queryTimeoutSecs)*time.Second)
			defer cancel()

			client, err := ipc.NewClient(ipc.Config{
				SocketPath: state.SocketPath,
				ClientID:   "ragman-cli",
				Logger:     silentLogger(),
			})
			if err != nil {
				logger.Error("ragman query connection failed", slog.String("error", err.Error()))
				return fmt.Errorf("ragman: connect backend: %w", err)
			}
			defer client.Close()

			request := ipc.QueryRequest{
				Question:         question,
				ConversationID:   strings.TrimSpace(conversationID),
				MaxContextTokens: maxContextTokens,
				TraceID:          traceID,
			}

			response, err := client.Query(ctx, request)
			if err != nil {
				logger.Error("ragman query failed", slog.String("error", err.Error()))
				return fmt.Errorf("ragman: query backend: %w", err)
			}

			output, err := renderio.Render(response, renderio.Options{
				ConfidenceThreshold: state.Config.ConfidenceThreshold(),
				TraceID:             coalesce(response.TraceID, traceID),
				Presenter:           format,
			})
			if err != nil {
				logger.Error("ragman render failed", slog.String("error", err.Error()))
				return err
			}

			fmt.Fprintln(cmd.OutOrStdout(), output)
			logger.Info(
				"ragman query completed",
				slog.Float64("confidence", response.Confidence),
				slog.Bool("no_answer", response.NoAnswer),
				slog.Int("latency_ms", response.LatencyMS),
			)
			return nil
		},
	}

	cmd.Flags().BoolVar(&usePlain, "plain", false, "Render plain text output (no headings)")
	cmd.Flags().BoolVar(&useJSON, "json", false, "Emit JSON payload instead of human-readable text")
	cmd.Flags().StringVar(&conversationID, "conversation", "", "Conversation identifier to maintain context")
	cmd.Flags().IntVar(&maxContextTokens, "context-tokens", 0, "Override maximum context tokens sent to the backend")
	cmd.Flags().IntVar(&queryTimeoutSecs, "timeout-seconds", 30, "Timeout in seconds for backend queries")

	return cmd
}

// resolveFormat determines the output presenter from flag and configuration inputs.
func resolveFormat(plain, json bool, configured string) renderio.Format {
	switch {
	case json:
		return renderio.FormatJSON
	case plain:
		return renderio.FormatPlain
	default:
		switch strings.ToLower(configured) {
		case string(renderio.FormatPlain):
			return renderio.FormatPlain
		case string(renderio.FormatJSON):
			return renderio.FormatJSON
		default:
			return renderio.FormatMarkdown
		}
	}
}

// newTraceID creates a correlation identifier for CLI↔backend requests.
func newTraceID() string {
	var buf [16]byte
	if _, err := rand.Read(buf[:]); err == nil {
		return hex.EncodeToString(buf[:])
	}
	return fmt.Sprintf("trace-%d", time.Now().UnixNano())
}

// silentLogger suppresses IPC client logs to keep CLI output focused on results.
func silentLogger() *slog.Logger {
	handler := slog.NewTextHandler(io.Discard, &slog.HandlerOptions{})
	return slog.New(handler)
}

// coalesce returns the first non-empty string from the provided arguments.
func coalesce(values ...string) string {
	for _, value := range values {
		if strings.TrimSpace(value) != "" {
			return value
		}
	}
	return ""
}
