package ipc

import (
	"context"
	"errors"
)

var errReindexStreamingUnsupported = errors.New("ipc: reindex streaming not implemented")

// StartReindexStream is a placeholder that will be expanded to stream progress
// updates from the backend. The concrete implementation lands with T059d.
func (c *Client) StartReindexStream(ctx context.Context, req ReindexRequest, onUpdate func(IngestionJob) error) (IngestionJob, error) {
	_ = ctx
	_ = req
	_ = onUpdate
	return IngestionJob{}, errReindexStreamingUnsupported
}
