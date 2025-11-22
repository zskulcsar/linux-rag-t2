package ipc

import (
	"context"
	"errors"
	"fmt"
	"strings"
)

var errReindexStreamIncomplete = errors.New("ipc: reindex stream ended before completion")

// StartReindexStream streams ingestion job snapshots as described in
// tmp/specs/001-rag-cli/20-11-2025-ragadmin-reindex-streaming-design.md.
// The method mirrors StartReindex but invokes the callback for every streamed
// job update before returning the final snapshot.
func (c *Client) StartReindexStream(ctx context.Context, req ReindexRequest, onUpdate func(IngestionJob) error) (IngestionJob, error) {
	req.TraceID = ensureTraceID(req.TraceID)
	trigger := strings.TrimSpace(req.Trigger)
	if trigger == "" {
		trigger = "manual"
	}
	req.Trigger = trigger

	c.mu.Lock()
	defer c.mu.Unlock()

	firstFrame, iter, err := c.callStream(ctx, indexReindexPath, req)
	if err != nil {
		return IngestionJob{}, err
	}
	if firstFrame.Status != statusAccepted {
		return IngestionJob{}, fmt.Errorf("ipc: start reindex unexpected status %d", firstFrame.Status)
	}

	job, err := decodeIngestionJob(firstFrame.Body)
	if err != nil {
		return IngestionJob{}, err
	}
	if err := invokeReindexCallback(onUpdate, job); err != nil {
		return job, err
	}

	for {
		if isTerminalJobStatus(job.Status) {
			return job, nil
		}

		nextFrame, ok, err := iter(ctx)
		if err != nil {
			return job, err
		}
		if !ok {
			return job, errReindexStreamIncomplete
		}

		job, err = decodeIngestionJob(nextFrame.Body)
		if err != nil {
			return job, err
		}
		if err := invokeReindexCallback(onUpdate, job); err != nil {
			return job, err
		}
	}
}

func invokeReindexCallback(cb func(IngestionJob) error, job IngestionJob) error {
	if cb == nil {
		return nil
	}
	if err := cb(job); err != nil {
		return fmt.Errorf("ipc: reindex callback: %w", err)
	}
	return nil
}

func isTerminalJobStatus(status string) bool {
	switch strings.ToLower(strings.TrimSpace(status)) {
	case "succeeded", "failed", "cancelled":
		return true
	default:
		return false
	}
}
