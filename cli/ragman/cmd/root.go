// Package cmd wires together the ragman CLI commands.
package cmd

import (
	"context"
	"errors"
	"log/slog"
	"os"
	"path/filepath"
	"strings"

	"github.com/spf13/cobra"

	"github.com/linux-rag-t2/cli/ragman/internal/config"
)

type appStateKey struct{}

type runtimeState struct {
	Config     config.Config
	ConfigPath string
	SocketPath string
	Logger     *slog.Logger
}

type rootOptions struct {
	configPath string
	socketPath string
}

var (
	rootCmd  = newRootCommand()
	rootOpts = &rootOptions{}
)

// Execute runs the ragman command hierarchy.
func Execute() error {
	return rootCmd.Execute()
}

func newRootCommand() *cobra.Command {
	cmd := &cobra.Command{
		Use:   "ragman",
		Short: "Ask Linux questions backed by the local rag backend",
		Long:  "ragman connects to the local RAG backend over a Unix socket to answer Linux questions with citations.",
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

	cmd.SetContext(context.Background())
	cmd.AddCommand(newQueryCommand())
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

	socket := defaultSocketPath(rootOpts.socketPath)
	state := &runtimeState{
		Config:     cfg,
		ConfigPath: cfgPath,
		SocketPath: socket,
		Logger:     newLogger(),
	}

	root.SetContext(context.WithValue(ctx, appStateKey{}, state))
	return nil
}

func obtainState(cmd *cobra.Command) (*runtimeState, error) {
	ctx := cmd.Root().Context()
	if ctx == nil {
		return nil, errors.New("ragman: command context missing")
	}
	state, _ := ctx.Value(appStateKey{}).(*runtimeState)
	if state == nil {
		return nil, errors.New("ragman: application state not initialised")
	}
	return state, nil
}

// resolveConfigPath selects the configuration path based on flag and environment overrides.
func resolveConfigPath(flagValue string) (string, error) {
	if strings.TrimSpace(flagValue) != "" {
		return flagValue, nil
	}
	return config.DefaultPath()
}

// defaultSocketPath determines the backend socket path, respecting flags and environment overrides.
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

// newLogger constructs the structured logger used by the CLI for telemetry.
func newLogger() *slog.Logger {
	level := slog.LevelWarn
	if raw := strings.TrimSpace(os.Getenv("RAGMAN_LOG_LEVEL")); raw != "" {
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
