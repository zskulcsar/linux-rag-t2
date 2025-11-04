package ipc_test

import (
	"encoding/json"
	"errors"
	"testing"

	"github.com/linux-rag-t2/cli/shared/ipc"
)

func TestBuildQueryRequestTrimsAndDefaults(t *testing.T) {
	t.Parallel()

	envelope, err := ipc.BuildQueryRequest(ipc.QueryRequestInput{
		Question:         "  How do I change file permissions?  ",
		ConversationID:   "   session-123   ",
		MaxContextTokens: 0,
		TraceID:          "trace-abc",
	})
	if err != nil {
		t.Fatalf("BuildQueryRequest returned error: %v", err)
	}

	if envelope.Path != "/v1/query" {
		t.Fatalf("expected /v1/query path, got %q", envelope.Path)
	}

	body := marshalEnvelopeBody(t, envelope)
	if got := body["question"]; got != "How do I change file permissions?" {
		t.Fatalf("expected trimmed question, got %v", got)
	}
	if got := body["conversation_id"]; got != "session-123" {
		t.Fatalf("expected trimmed conversation_id, got %v", got)
	}
	if got := body["max_context_tokens"]; got != float64(4096) { // JSON numbers decode to float64
		t.Fatalf("expected default max_context_tokens 4096, got %v", got)
	}
	if got := body["trace_id"]; got != "trace-abc" {
		t.Fatalf("expected trace_id propagation, got %v", got)
	}
}

func TestBuildQueryRequestOmitsEmptyConversation(t *testing.T) {
	t.Parallel()

	envelope, err := ipc.BuildQueryRequest(ipc.QueryRequestInput{
		Question:         "List all sources",
		MaxContextTokens: 1024,
	})
	if err != nil {
		t.Fatalf("BuildQueryRequest returned error: %v", err)
	}

	body := marshalEnvelopeBody(t, envelope)
	if _, ok := body["conversation_id"]; ok {
		t.Fatalf("expected no conversation_id key when input empty, got body: %v", body)
	}
	if got := body["max_context_tokens"]; got != float64(1024) {
		t.Fatalf("expected explicit max_context_tokens 1024, got %v", got)
	}
}

func TestBuildQueryRequestRejectsEmptyQuestion(t *testing.T) {
	t.Parallel()

	_, err := ipc.BuildQueryRequest(ipc.QueryRequestInput{
		Question:         "   ",
		MaxContextTokens: 4096,
	})
	if err == nil {
		t.Fatal("expected error for empty question, got nil")
	}
	if !errors.Is(err, ipc.ErrInvalidQueryRequest) {
		t.Fatalf("expected ErrInvalidQueryRequest, got %v", err)
	}
}

func TestDecodeQueryResponseParsesStructuredPayload(t *testing.T) {
	t.Parallel()

	raw := []byte(`{
		"summary": "Use chmod to adjust permissions.",
		"steps": ["Run chmod with desired mode", "Verify permissions with ls -l"],
		"references": [
			{"label": "chmod(1)", "url": "man:chmod", "notes": "POSIX manual"}
		],
		"citations": [
			{"alias": "man-pages", "document_ref": "chmod(1)", "excerpt": "chmod changes file mode bits."}
		],
		"confidence": 0.82,
		"trace_id": "trace-123",
		"latency_ms": 420,
		"retrieval_latency_ms": 120,
		"llm_latency_ms": 260,
		"index_version": "idx-2024-10-31",
		"answer": "Detailed markdown answer",
		"no_answer": false
	}`)

	resp, err := ipc.DecodeQueryResponse(raw)
	if err != nil {
		t.Fatalf("DecodeQueryResponse returned error: %v", err)
	}

	if resp.Summary != "Use chmod to adjust permissions." {
		t.Fatalf("unexpected summary: %q", resp.Summary)
	}
	if len(resp.Steps) != 2 {
		t.Fatalf("expected two procedural steps, got %d", len(resp.Steps))
	}
	if len(resp.References) != 1 || resp.References[0].Label != "chmod(1)" {
		t.Fatalf("unexpected references: %#v", resp.References)
	}
	if len(resp.Citations) != 1 || resp.Citations[0].Alias != "man-pages" {
		t.Fatalf("unexpected citations: %#v", resp.Citations)
	}
	if resp.Confidence != 0.82 {
		t.Fatalf("unexpected confidence: %v", resp.Confidence)
	}
	if resp.TraceID != "trace-123" {
		t.Fatalf("unexpected trace id: %q", resp.TraceID)
	}
	if resp.LatencyMS != 420 {
		t.Fatalf("unexpected latency: %d", resp.LatencyMS)
	}
	if resp.RetrievalLatencyMS == nil || *resp.RetrievalLatencyMS != 120 {
		t.Fatalf("expected retrieval latency 120, got %v", resp.RetrievalLatencyMS)
	}
	if resp.LLMLatencyMS == nil || *resp.LLMLatencyMS != 260 {
		t.Fatalf("expected LLM latency 260, got %v", resp.LLMLatencyMS)
	}
	if resp.IndexVersion == nil || *resp.IndexVersion != "idx-2024-10-31" {
		t.Fatalf("expected index version field, got %v", resp.IndexVersion)
	}
	if resp.Answer == nil || *resp.Answer != "Detailed markdown answer" {
		t.Fatalf("expected answer field, got %v", resp.Answer)
	}
	if resp.NoAnswer {
		t.Fatal("expected no_answer false")
	}
}

func TestDecodeQueryResponseValidatesRequiredFields(t *testing.T) {
	t.Parallel()

	raw := []byte(`{"steps": ["missing summary field"]}`)
	_, err := ipc.DecodeQueryResponse(raw)
	if err == nil {
		t.Fatal("expected validation error for incomplete payload")
	}
	if !errors.Is(err, ipc.ErrInvalidQueryResponse) {
		t.Fatalf("expected ErrInvalidQueryResponse, got %v", err)
	}
}

func marshalEnvelopeBody(t *testing.T, envelope ipc.RequestEnvelope) map[string]any {
	t.Helper()

	raw, err := json.Marshal(envelope.Body)
	if err != nil {
		t.Fatalf("failed to marshal envelope body: %v", err)
	}

	var body map[string]any
	if err := json.Unmarshal(raw, &body); err != nil {
		t.Fatalf("failed to decode envelope body: %v", err)
	}
	return body
}
