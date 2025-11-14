package ipc

import (
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"net/url"
	"path"
	"strings"
)

const (
	sourcesPath      = "/v1/sources"
	indexReindexPath = "/v1/index/reindex"

	statusOK                  = 200
	statusCreated             = 201
	statusAccepted            = 202
)

// SourceRecord mirrors catalog entries returned by the backend.
type SourceRecord struct {
	Alias       string `json:"alias"`
	Type        string `json:"type"`
	Location    string `json:"location"`
	Language    string `json:"language"`
	SizeBytes   int64  `json:"size_bytes"`
	LastUpdated string `json:"last_updated"`
	Status      string `json:"status"`
	Checksum    string `json:"checksum,omitempty"`
	Notes       string `json:"notes,omitempty"`
}

// IngestionJob represents ingestion metadata returned from mutations.
type IngestionJob struct {
	JobID              string   `json:"job_id"`
	SourceAlias        string   `json:"source_alias,omitempty"`
	Status             string   `json:"status"`
	RequestedAt        string   `json:"requested_at"`
	StartedAt          string   `json:"started_at,omitempty"`
	CompletedAt        string   `json:"completed_at,omitempty"`
	DocumentsProcessed int      `json:"documents_processed,omitempty"`
	Stage              string   `json:"stage"`
	PercentComplete    *float64 `json:"percent_complete"`
	ErrorMessage       string   `json:"error_message,omitempty"`
	Trigger            string   `json:"trigger"`
}

// QuarantineInfo describes quarantine state returned by removal operations.
type QuarantineInfo struct {
	Reason    string `json:"reason"`
	Requested string `json:"requested"`
	TraceID   string `json:"trace_id,omitempty"`
	Documents int    `json:"documents,omitempty"`
	NextSteps string `json:"next_steps,omitempty"`
}

// SourceListRequest issues a catalog listing request.
type SourceListRequest struct {
	TraceID string `json:"trace_id"`
}

// SourceCreateRequest registers a new knowledge source.
type SourceCreateRequest struct {
	TraceID  string `json:"trace_id"`
	Alias    string `json:"alias,omitempty"`
	Type     string `json:"type"`
	Location string `json:"location"`
	Language string `json:"language,omitempty"`
	Notes    string `json:"notes,omitempty"`
	Checksum string `json:"checksum,omitempty"`
}

// SourceUpdateRequest mutates metadata for an existing source.
type SourceUpdateRequest struct {
	TraceID  string `json:"trace_id"`
	Location string `json:"location,omitempty"`
	Language string `json:"language,omitempty"`
	Status   string `json:"status,omitempty"`
	Notes    string `json:"notes,omitempty"`
}

// SourceRemoveRequest quarantines an existing source and removes it from the active catalog.
type SourceRemoveRequest struct {
	TraceID string `json:"trace_id"`
	Reason  string `json:"reason"`
}

// ReindexRequest triggers an index rebuild operation.
type ReindexRequest struct {
	TraceID string `json:"trace_id"`
	Trigger string `json:"trigger"`
}

// SourceListResponse captures catalog listing payloads.
type SourceListResponse struct {
	Sources   []SourceRecord `json:"sources"`
	UpdatedAt string         `json:"updated_at"`
	TraceID   string         `json:"trace_id,omitempty"`
}

// SourceMutationResponse wraps the result of add/update/remove mutations.
type SourceMutationResponse struct {
	Source       SourceRecord    `json:"source"`
	IngestionJob *IngestionJob   `json:"ingestion_job,omitempty"`
	Quarantine   *QuarantineInfo `json:"quarantine,omitempty"`
	TraceID      string          `json:"trace_id,omitempty"`
}

// ListSources fetches the catalog snapshot.
func (c *Client) ListSources(ctx context.Context, req SourceListRequest) (SourceListResponse, error) {
	req.TraceID = ensureTraceID(req.TraceID)

	c.mu.Lock()
	defer c.mu.Unlock()

	frame, err := c.call(ctx, sourcesPath, req)
	if err != nil {
		return SourceListResponse{}, err
	}
	if frame.Status != statusOK {
		return SourceListResponse{}, fmt.Errorf("ipc: list sources unexpected status %d", frame.Status)
	}
	return decodeSourceListResponse(frame.Body)
}

// CreateSource registers a new knowledge source.
func (c *Client) CreateSource(ctx context.Context, req SourceCreateRequest) (SourceMutationResponse, error) {
	req.TraceID = ensureTraceID(req.TraceID)
	req.Type = strings.TrimSpace(req.Type)
	if req.Type == "" {
		return SourceMutationResponse{}, errors.New("ipc: source type is required")
	}
	req.Location = strings.TrimSpace(req.Location)
	if req.Location == "" {
		return SourceMutationResponse{}, errors.New("ipc: source location is required")
	}
	req.Language = strings.TrimSpace(req.Language)

	c.mu.Lock()
	defer c.mu.Unlock()

	frame, err := c.call(ctx, sourcesPath, req)
	if err != nil {
		return SourceMutationResponse{}, err
	}
	if frame.Status != statusCreated {
		return SourceMutationResponse{}, fmt.Errorf("ipc: create source unexpected status %d", frame.Status)
	}
	return decodeSourceMutationResponse(frame.Body)
}

// UpdateSource mutates metadata for an existing source.
func (c *Client) UpdateSource(ctx context.Context, alias string, req SourceUpdateRequest) (SourceMutationResponse, error) {
	alias = strings.TrimSpace(alias)
	if alias == "" {
		return SourceMutationResponse{}, errors.New("ipc: alias must be provided")
	}
	req.TraceID = ensureTraceID(req.TraceID)

	c.mu.Lock()
	defer c.mu.Unlock()

	frame, err := c.call(ctx, buildSourceAliasPath(alias), req)
	if err != nil {
		return SourceMutationResponse{}, err
	}
	if frame.Status != statusOK {
		return SourceMutationResponse{}, fmt.Errorf("ipc: update source unexpected status %d", frame.Status)
	}
	return decodeSourceMutationResponse(frame.Body)
}

// RemoveSource quarantines a source and removes it from the active catalog.
func (c *Client) RemoveSource(ctx context.Context, alias string, req SourceRemoveRequest) (SourceMutationResponse, error) {
	alias = strings.TrimSpace(alias)
	if alias == "" {
		return SourceMutationResponse{}, errors.New("ipc: alias must be provided")
	}
	req.TraceID = ensureTraceID(req.TraceID)
	req.Reason = strings.TrimSpace(req.Reason)
	if req.Reason == "" {
		return SourceMutationResponse{}, errors.New("ipc: reason must be provided")
	}

	c.mu.Lock()
	defer c.mu.Unlock()

	frame, err := c.call(ctx, buildSourceAliasPath(alias), req)
	if err != nil {
		return SourceMutationResponse{}, err
	}
	if frame.Status != statusAccepted {
		return SourceMutationResponse{}, fmt.Errorf("ipc: remove source unexpected status %d", frame.Status)
	}
	return decodeSourceMutationResponse(frame.Body)
}

// StartReindex triggers an index rebuild and returns the job metadata.
func (c *Client) StartReindex(ctx context.Context, req ReindexRequest) (IngestionJob, error) {
	req.TraceID = ensureTraceID(req.TraceID)
	trigger := strings.TrimSpace(req.Trigger)
	if trigger == "" {
		trigger = "manual"
	}
	req.Trigger = trigger

	c.mu.Lock()
	defer c.mu.Unlock()

	frame, err := c.call(ctx, indexReindexPath, req)
	if err != nil {
		return IngestionJob{}, err
	}
	if frame.Status != 202 {
		return IngestionJob{}, fmt.Errorf("ipc: start reindex unexpected status %d", frame.Status)
	}
	return decodeIngestionJob(frame.Body)
}

func decodeSourceListResponse(payload []byte) (SourceListResponse, error) {
	var resp SourceListResponse
	if err := json.Unmarshal(payload, &resp); err != nil {
		return SourceListResponse{}, fmt.Errorf("ipc: decode list response: %w", err)
	}
	if resp.Sources == nil {
		resp.Sources = []SourceRecord{}
	}
	return resp, nil
}

func decodeSourceMutationResponse(payload []byte) (SourceMutationResponse, error) {
	var resp SourceMutationResponse
	if err := json.Unmarshal(payload, &resp); err != nil {
		return SourceMutationResponse{}, fmt.Errorf("ipc: decode source mutation: %w", err)
	}
	return resp, nil
}

func decodeIngestionJob(payload []byte) (IngestionJob, error) {
	var resp struct {
		Job IngestionJob `json:"job"`
	}
	if err := json.Unmarshal(payload, &resp); err != nil {
		return IngestionJob{}, fmt.Errorf("ipc: decode ingestion job: %w", err)
	}
	return resp.Job, nil
}

func buildSourceAliasPath(alias string) string {
	escaped := url.PathEscape(alias)
	return path.Join(sourcesPath, escaped)
}

func ensureTraceID(traceID string) string {
	if strings.TrimSpace(traceID) == "" {
		return NewTraceID()
	}
	return traceID
}
