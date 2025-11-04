package ipc

import (
	"encoding/json"
	"errors"
	"fmt"
	"strings"
)

// ErrInvalidQueryRequest indicates that a request builder received invalid input.
var ErrInvalidQueryRequest = errors.New("ipc: invalid query request")

// ErrInvalidQueryResponse indicates that a decoder received malformed payload data.
var ErrInvalidQueryResponse = errors.New("ipc: invalid query response payload")

// QueryRequest mirrors the backend contract for issuing query operations.
type QueryRequest struct {
	Question         string `json:"question"`
	ConversationID   string `json:"conversation_id,omitempty"`
	MaxContextTokens int    `json:"max_context_tokens"`
	TraceID          string `json:"trace_id,omitempty"`
}

// QueryReference captures a single reference entry returned by the backend.
type QueryReference struct {
	Label string `json:"label"`
	URL   string `json:"url,omitempty"`
	Notes string `json:"notes,omitempty"`
}

// QueryCitation captures inline citation metadata provided by the backend.
type QueryCitation struct {
	Alias       string `json:"alias"`
	DocumentRef string `json:"document_ref"`
	Excerpt     string `json:"excerpt,omitempty"`
}

// QueryResponse represents the structured answer returned by the backend query endpoint.
type QueryResponse struct {
	Summary            string           `json:"summary"`
	Steps              []string         `json:"steps"`
	References         []QueryReference `json:"references"`
	Citations          []QueryCitation  `json:"citations"`
	Confidence         float64          `json:"confidence"`
	TraceID            string           `json:"trace_id"`
	LatencyMS          int              `json:"latency_ms"`
	RetrievalLatencyMS *int             `json:"retrieval_latency_ms,omitempty"`
	LLMLatencyMS       *int             `json:"llm_latency_ms,omitempty"`
	IndexVersion       *string          `json:"index_version,omitempty"`
	Answer             *string          `json:"answer,omitempty"`
	NoAnswer           bool             `json:"no_answer,omitempty"`
}

// QueryRequestInput captures user-provided fields used to build JSON transport requests.
type QueryRequestInput struct {
	Question         string
	ConversationID   string
	MaxContextTokens int
	TraceID          string
}

// RequestEnvelope represents a transport request path and body pairing.
type RequestEnvelope struct {
	Path string
	Body any
}

// BuildQueryRequest normalizes user input and returns a transport envelope for /v1/query.
func BuildQueryRequest(input QueryRequestInput) (RequestEnvelope, error) {
	question := strings.TrimSpace(input.Question)
	if question == "" {
		return RequestEnvelope{}, fmt.Errorf("%w: question must not be empty", ErrInvalidQueryRequest)
	}

	conversationID := strings.TrimSpace(input.ConversationID)
	traceID := strings.TrimSpace(input.TraceID)

	maxTokens := input.MaxContextTokens
	if maxTokens <= 0 {
		maxTokens = defaultMaxContextTokens
	}

	request := QueryRequest{
		Question:         question,
		MaxContextTokens: maxTokens,
		TraceID:          traceID,
	}
	if conversationID != "" {
		request.ConversationID = conversationID
	}

	return RequestEnvelope{
		Path: queryPath,
		Body: request,
	}, nil
}

// DecodeQueryResponse converts a raw JSON payload into a structured QueryResponse.
func DecodeQueryResponse(payload []byte) (QueryResponse, error) {
	var resp QueryResponse
	if err := json.Unmarshal(payload, &resp); err != nil {
		return QueryResponse{}, fmt.Errorf("%w: %v", ErrInvalidQueryResponse, err)
	}

	if strings.TrimSpace(resp.Summary) == "" {
		return QueryResponse{}, fmt.Errorf("%w: summary is required", ErrInvalidQueryResponse)
	}

	ensureQueryResponseDefaults(&resp)
	return resp, nil
}

// ensureQueryResponseDefaults backfills nil slices to keep marshaling predictable.
func ensureQueryResponseDefaults(resp *QueryResponse) {
	if resp.Steps == nil {
		resp.Steps = []string{}
	}
	if resp.References == nil {
		resp.References = []QueryReference{}
	}
	if resp.Citations == nil {
		resp.Citations = []QueryCitation{}
	}
}
