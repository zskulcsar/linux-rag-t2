// Package config loads ragadmin configuration files.
package config

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
	"strings"

	"gopkg.in/yaml.v3"
)

const defaultOutput = "table"

// Config represents the ragadmin configuration schema.
type Config struct {
	Ragadmin RagadminConfig `yaml:"ragadmin"`
}

// RagadminConfig captures CLI-specific default settings.
type RagadminConfig struct {
	OutputDefault string `yaml:"output_default"`
}

// Default returns the baseline configuration used when no file exists.
func Default() Config {
	return Config{
		Ragadmin: RagadminConfig{
			OutputDefault: defaultOutput,
		},
	}
}

// Load reads configuration from the provided path. Missing files result in defaults.
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

// DefaultPath returns the XDG-compliant configuration path.
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

// Output returns the configured default output format (table|json).
func (c Config) Output() string {
	return c.Ragadmin.OutputDefault
}

func (c *Config) apply(raw Config) {
	if strings.TrimSpace(raw.Ragadmin.OutputDefault) != "" {
		c.Ragadmin.OutputDefault = raw.Ragadmin.OutputDefault
	}
}

func (c *Config) normalize() {
	switch strings.ToLower(strings.TrimSpace(c.Ragadmin.OutputDefault)) {
	case "json":
		c.Ragadmin.OutputDefault = "json"
	default:
		c.Ragadmin.OutputDefault = defaultOutput
	}
}
