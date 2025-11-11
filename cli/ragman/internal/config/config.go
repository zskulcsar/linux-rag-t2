// Package config loads ragcli configuration files and exposes strongly typed helpers.
package config

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

const (
	defaultPresenter           = "markdown"
	defaultConfidenceThreshold = 0.35
)

// Config represents the ragcli configuration file.
type Config struct {
	Ragman RagmanConfig `yaml:"ragman"`
}

// RagmanConfig captures ragman-specific presentation settings.
type RagmanConfig struct {
	ConfidenceThreshold float64 `yaml:"confidence_threshold"`
	PresenterDefault    string  `yaml:"presenter_default"`
}

// Default returns the default configuration used when no file exists.
func Default() Config {
	return Config{
		Ragman: RagmanConfig{
			ConfidenceThreshold: defaultConfidenceThreshold,
			PresenterDefault:    defaultPresenter,
		},
	}
}

// Load reads the configuration from the provided path. When the file does not exist,
// the default configuration is returned without error.
func Load(path string) (Config, error) {
	cfg := Default()
	if strings.TrimSpace(path) == "" {
		return cfg, nil
	}

	data, err := os.ReadFile(path)
	if err != nil {
		if errors.Is(err, os.ErrNotExist) {
			return cfg, nil
		}
		return cfg, fmt.Errorf("config: read file: %w", err)
	}
	if len(data) == 0 {
		return cfg, nil
	}

	var raw Config
	if err := yaml.Unmarshal(data, &raw); err != nil {
		return cfg, fmt.Errorf("config: decode: %w", err)
	}

	cfg.apply(raw)
	cfg.normalize()
	return cfg, nil
}

// DefaultPath returns the preferred configuration path derived from XDG conventions.
func DefaultPath() (string, error) {
	if env := strings.TrimSpace(os.Getenv("RAGCLI_CONFIG")); env != "" {
		return env, nil
	}

	if xdg := strings.TrimSpace(os.Getenv("XDG_CONFIG_HOME")); xdg != "" {
		return filepath.Join(xdg, "ragcli", "config.yaml"), nil
	}

	home, err := os.UserHomeDir()
	if err != nil {
		return "", fmt.Errorf("config: determine home directory: %w", err)
	}
	return filepath.Join(home, ".config", "ragcli", "config.yaml"), nil
}

// Presenter selects the default presenter identifier (markdown/plain/json).
func (c Config) Presenter() string {
	return c.Ragman.PresenterDefault
}

// ConfidenceThreshold returns the configured minimum answer confidence.
func (c Config) ConfidenceThreshold() float64 {
	return c.Ragman.ConfidenceThreshold
}

func (c *Config) apply(raw Config) {
	if raw.Ragman.ConfidenceThreshold != 0 {
		c.Ragman.ConfidenceThreshold = raw.Ragman.ConfidenceThreshold
	}
	if strings.TrimSpace(raw.Ragman.PresenterDefault) != "" {
		c.Ragman.PresenterDefault = raw.Ragman.PresenterDefault
	}
}

func (c *Config) normalize() {
	if c.Ragman.ConfidenceThreshold < 0 {
		c.Ragman.ConfidenceThreshold = 0
	} else if c.Ragman.ConfidenceThreshold > 1 {
		c.Ragman.ConfidenceThreshold = 1
	}

	switch strings.ToLower(strings.TrimSpace(c.Ragman.PresenterDefault)) {
	case "markdown", "plain", "json":
		c.Ragman.PresenterDefault = strings.ToLower(strings.TrimSpace(c.Ragman.PresenterDefault))
	default:
		c.Ragman.PresenterDefault = defaultPresenter
	}
}
