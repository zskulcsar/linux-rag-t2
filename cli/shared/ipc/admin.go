package ipc

import (
	"context"
	"encoding/json"
	"fmt"
)

const (
	adminInitPath   = "/v1/admin/init"
	adminHealthPath = "/v1/admin/health"
)

// InitRequest triggers backend initialization workflows.
type InitRequest struct {
	TraceID string `json:"trace_id"`
}

// InitResponse captures the initialization summary payload.
type InitResponse struct {
	CatalogVersion     int               `json:"catalog_version"`
	CreatedDirectories []string          `json:"created_directories"`
	SeededSources      []SourceRecord    `json:"seeded_sources"`
	DependencyChecks   []DependencyCheck `json:"dependency_checks,omitempty"`
	TraceID            string            `json:"trace_id,omitempty"`
}

// DependencyCheck mirrors dependency readiness responses from the backend.
type DependencyCheck struct {
	Component   string `json:"component"`
	Status      string `json:"status"`
	Message     string `json:"message"`
	Remediation string `json:"remediation,omitempty"`
}

// HealthRequest fetches the backend health summary.
type HealthRequest struct {
	TraceID string `json:"trace_id"`
}

// HealthSummary aggregates health component results.
type HealthSummary struct {
	OverallStatus string         `json:"overall_status"`
	TraceID       string         `json:"trace_id"`
	Results       []HealthResult `json:"results"`
}

// HealthResult represents an individual component check.
type HealthResult struct {
	Component   string             `json:"component"`
	Status      string             `json:"status"`
	Message     string             `json:"message"`
	Remediation string             `json:"remediation,omitempty"`
	Metrics     map[string]float64 `json:"metrics,omitempty"`
}

// InitSystem executes `/v1/admin/init` and returns the backend summary.
func (c *Client) InitSystem(ctx context.Context, req InitRequest) (InitResponse, error) {
	req.TraceID = ensureTraceID(req.TraceID)

	c.mu.Lock()
	defer c.mu.Unlock()

	frame, err := c.call(ctx, adminInitPath, req)
	if err != nil {
		return InitResponse{}, err
	}
	if frame.Status != statusOK {
		return InitResponse{}, fmt.Errorf("ipc: admin init unexpected status %d", frame.Status)
	}
	resp, err := decodeInitResponse(frame.Body)
	if err != nil {
		return InitResponse{}, err
	}
	if resp.TraceID == "" {
		resp.TraceID = req.TraceID
	}
	return resp, nil
}

// HealthCheck aggregates component health via `/v1/admin/health`.
func (c *Client) HealthCheck(ctx context.Context, req HealthRequest) (HealthSummary, error) {
	req.TraceID = ensureTraceID(req.TraceID)

	c.mu.Lock()
	defer c.mu.Unlock()

	frame, err := c.call(ctx, adminHealthPath, req)
	if err != nil {
		return HealthSummary{}, err
	}
	if frame.Status != statusOK {
		return HealthSummary{}, fmt.Errorf("ipc: admin health unexpected status %d", frame.Status)
	}
	summary, err := decodeHealthSummary(frame.Body)
	if err != nil {
		return HealthSummary{}, err
	}
	if summary.TraceID == "" {
		summary.TraceID = req.TraceID
	}
	return summary, nil
}

func decodeInitResponse(payload []byte) (InitResponse, error) {
	var resp InitResponse
	if err := json.Unmarshal(payload, &resp); err != nil {
		return InitResponse{}, fmt.Errorf("ipc: decode init response: %w", err)
	}
	if resp.CreatedDirectories == nil {
		resp.CreatedDirectories = []string{}
	}
	if resp.SeededSources == nil {
		resp.SeededSources = []SourceRecord{}
	}
	if resp.DependencyChecks == nil {
		resp.DependencyChecks = []DependencyCheck{}
	}
	return resp, nil
}

func decodeHealthSummary(payload []byte) (HealthSummary, error) {
	var resp HealthSummary
	if err := json.Unmarshal(payload, &resp); err != nil {
		return HealthSummary{}, fmt.Errorf("ipc: decode health summary: %w", err)
	}
	if resp.Results == nil {
		resp.Results = []HealthResult{}
	}
	return resp, nil
}
