// Package cmd wires the ragadmin command hierarchy.
package cmd

import (
	"context"
	"errors"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"time"

	"github.com/linux-rag-t2/cli/ragadmin/internal/audit"
	"github.com/linux-rag-t2/cli/ragadmin/internal/config"
	"github.com/linux-rag-t2/cli/shared/ipc"
	"github.com/spf13/cobra"
)

type appStateKey struct{}

type runtimeState struct {
	Config       config.Config
	ConfigPath   string
	SocketPath   string
	OutputFormat string
	Logger       *slog.Logger
	AuditLogger  *audit.Logger
}

type rootOptions struct {
	configPath string
	socketPath string
	output     string
}

const (
	clientID       = "ragadmin-cli"
	requestTimeout = 15 * time.Second
)

var (
	rootCmd  = newRootCommand()
	rootOpts = &rootOptions{}
)

// Execute runs the ragadmin command tree.
func Execute() error {
	return rootCmd.Execute()
}

func newRootCommand() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "ragadmin",
		Short: "Manage knowledge sources for the local RAG backend",
		Long:  "ragadmin administers knowledge sources, reindex operations, and health checks for the local RAG backend over Unix sockets.",
		PersistentPreRunE: func(cmd *cobra.Command, _ []string) error {
			return initializeState(cmd)
		},
		RunE: func(cmd *cobra.Command, _ []string) error {
			return cmd.Help()
		},
		SilenceErrors: true,
		SilenceUsage:  true,
	}

	defaultConfigPath, err := config.DefaultPath()
	if err != nil {
		defaultConfigPath = ""
	}
	defaultSocket := defaultSocketPath("")

	cmd.PersistentFlags().StringVar(&rootOpts.configPath, "config", defaultConfigPath, "Path to the ragcli configuration file")
	cmd.PersistentFlags().StringVar(&rootOpts.socketPath, "socket", defaultSocket, "Unix socket path for the rag backend")
	cmd.PersistentFlags().StringVar(&rootOpts.output, "output", "", "Output format for tabular commands (table|json)")

	cmd.SetContext(context.Background())
	cmd.AddCommand(newSourcesCommand())
	cmd.AddCommand(newReindexCommand())
	return cmd
}

func initializeState(cmd *cobra.Command) error {
	root := cmd.Root()
	ctx := root.Context()
	if ctx == nil {
		ctx = context.Background()
	}
	if _, ok := ctx.Value(appStateKey{}).(*runtimeState); ok {
		return nil
	}

	cfgPath, err := resolveConfigPath(rootOpts.configPath)
	if err != nil {
		return err
	}
	cfg, err := config.Load(cfgPath)
	if err != nil {
		return err
	}

	output := resolveOutputFormat(rootOpts.output, cfg.Output())
	auditLogger, err := audit.NewLogger("")
	if err != nil {
		return err
	}

	state := &runtimeState{
		Config:       cfg,
		ConfigPath:   cfgPath,
		SocketPath:   defaultSocketPath(rootOpts.socketPath),
		OutputFormat: output,
		Logger:       newLogger(),
		AuditLogger:  auditLogger,
	}

	root.SetContext(context.WithValue(ctx, appStateKey{}, state))
	return nil
}

func obtainState(cmd *cobra.Command) (*runtimeState, error) {
	ctx := cmd.Root().Context()
	if ctx == nil {
		return nil, errors.New("ragadmin: command context missing")
	}
	state, _ := ctx.Value(appStateKey{}).(*runtimeState)
	if state == nil {
		return nil, errors.New("ragadmin: application state not initialised")
	}
	return state, nil
}

func resolveConfigPath(flagValue string) (string, error) {
	if trimmed := strings.TrimSpace(flagValue); trimmed != "" {
		return trimmed, nil
	}
	return config.DefaultPath()
}

func defaultSocketPath(flagValue string) string {
	if trimmed := strings.TrimSpace(flagValue); trimmed != "" {
		return trimmed
	}
	if env := strings.TrimSpace(os.Getenv("RAGCLI_SOCKET")); env != "" {
		return env
	}
	if runtimeDir := strings.TrimSpace(os.Getenv("XDG_RUNTIME_DIR")); runtimeDir != "" {
		return filepath.Join(runtimeDir, "ragcli", "backend.sock")
	}
	return filepath.Join(os.TempDir(), "ragcli", "backend.sock")
}

func resolveOutputFormat(flagValue, configValue string) string {
	candidate := strings.ToLower(strings.TrimSpace(flagValue))
	if candidate == "" {
		candidate = strings.ToLower(strings.TrimSpace(configValue))
	}
	switch candidate {
	case "json":
		return "json"
	default:
		return "table"
	}
}

func newLogger() *slog.Logger {
	level := slog.LevelWarn
	if raw := strings.TrimSpace(os.Getenv("RAGADMIN_LOG_LEVEL")); raw != "" {
		switch strings.ToLower(raw) {
		case "debug":
			level = slog.LevelDebug
		case "info":
			level = slog.LevelInfo
		case "warn", "warning":
			level = slog.LevelWarn
		case "error":
			level = slog.LevelError
		}
	}
	handler := slog.NewTextHandler(os.Stderr, &slog.HandlerOptions{Level: level})
	return slog.New(handler)
}

func runWithClient(cmd *cobra.Command, fn func(context.Context, *runtimeState, *ipc.Client) error) error {
	state, err := obtainState(cmd)
	if err != nil {
		return err
	}

	ctx := cmd.Context()
	if ctx == nil {
		ctx = context.Background()
	}
	ctx, cancel := context.WithTimeout(ctx, requestTimeout)
	defer cancel()

	client, err := ipc.NewClient(ipc.Config{
		SocketPath: state.SocketPath,
		ClientID:   clientID,
		Logger:     state.Logger,
	})
	if err != nil {
		return err
	}
	defer client.Close()

	return fn(ctx, state, client)
}
