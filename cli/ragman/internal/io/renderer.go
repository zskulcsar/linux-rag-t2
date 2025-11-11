// Package io renders backend query responses into user-friendly presentations.
package io

import (
	"bytes"
	"encoding/json"
	"fmt"
	"sort"
	"strings"
	"text/template"

	"github.com/linux-rag-t2/cli/shared/ipc"
)

// Format identifies the output presenter used by the CLI.
type Format string

// Supported renderers.
const (
	FormatMarkdown Format = "markdown"
	FormatPlain    Format = "plain"
	FormatJSON     Format = "json"
)

// Options customise the rendering of a query response.
type Options struct {
	ConfidenceThreshold float64
	TraceID             string
	Presenter           Format
}

// Render generates a formatted representation of the backend query response.
func Render(resp ipc.QueryResponse, opts Options) (string, error) {
	switch opts.Presenter {
	case FormatPlain:
		return renderPlain(resp, opts), nil
	case FormatJSON:
		return renderJSON(resp, opts)
	case FormatMarkdown, "":
		return renderMarkdown(resp, opts), nil
	default:
		return "", fmt.Errorf("renderer: unsupported presenter %q", opts.Presenter)
	}
}

func renderJSON(resp ipc.QueryResponse, opts Options) (string, error) {
	payload := map[string]any{
		"summary":              resp.Summary,
		"steps":                resp.Steps,
		"references":           resp.References,
		"citations":            resp.Citations,
		"confidence":           resp.Confidence,
		"confidence_threshold": opts.ConfidenceThreshold,
		"trace_id":             coalesce(resp.TraceID, opts.TraceID),
		"latency_ms":           resp.LatencyMS,
		"no_answer":            resp.NoAnswer,
		"context_truncated":    resp.ContextTruncated,
		"stale_index_detected": resp.StaleIndexDetected,
	}
	if resp.SemanticChunkCount != nil {
		payload["semantic_chunk_count"] = *resp.SemanticChunkCount
	}
	if resp.BackendCorrelationID != "" {
		payload["backend_correlation_id"] = resp.BackendCorrelationID
	}
	if resp.ConfidenceThreshold != nil {
		payload["effective_confidence_threshold"] = *resp.ConfidenceThreshold
	}
	if resp.RetrievalLatencyMS != nil {
		payload["retrieval_latency_ms"] = *resp.RetrievalLatencyMS
	}
	if resp.LLMLatencyMS != nil {
		payload["llm_latency_ms"] = *resp.LLMLatencyMS
	}
	if resp.IndexVersion != nil {
		payload["index_version"] = *resp.IndexVersion
	}
	if resp.Answer != nil {
		payload["answer"] = *resp.Answer
	}

	data, err := json.MarshalIndent(payload, "", "  ")
	if err != nil {
		return "", fmt.Errorf("renderer: encode json: %w", err)
	}
	return string(data), nil
}

var (
	templateFuncs = template.FuncMap{
		"inc": func(i int) int { return i + 1 },
	}

	markdownTemplate = template.Must(template.New("markdown").
				Funcs(templateFuncs).
				Parse(markdownTemplateSrc))

	plainTemplate = template.Must(template.New("plain").
			Funcs(templateFuncs).
			Parse(plainTemplateSrc))
)

const markdownTemplateSrc = `{{.ConfidenceLine}}{{if .HasTruncationWarning}}
{{.TruncationWarning}}{{end}}{{if .Fallback}}

No answer found
---------------
{{.FallbackBody}}{{else}}

Summary
-------
{{.Summary}}{{if .HasSteps}}

Steps
-----
{{range $idx, $step := .Steps}}{{printf "%d. %s\n" (inc $idx) $step}}{{end}}{{end}}{{if .HasReferences}}

References
----------
{{range .References}}[{{.Index}}] {{.Alias}} — {{.DocumentRef}}
{{if .HasExcerpt}}    {{.Excerpt}}
{{end}}{{if .HasURL}}    Link: {{.URL}}
{{end}}{{if .HasNotes}}    Notes: {{.Notes}}
{{end}}
{{end}}{{end}}{{end}}

Trace ID: {{.TraceID}}`

const plainTemplateSrc = `{{.ConfidenceLine}}{{if .HasTruncationWarning}}
{{.TruncationWarning}}{{end}}{{if .Fallback}}

No answer found
---------------
{{.FallbackBody}}{{else}}

SUMMARY:
{{.Summary}}{{if .HasSteps}}

STEPS:
{{range $idx, $step := .Steps}}{{printf "%d) %s\n" (inc $idx) $step}}{{end}}{{end}}{{if .HasReferences}}

REFERENCES:
{{range .References}}[{{.Index}}] {{.Alias}} :: {{.DocumentRef}}
{{if .HasExcerpt}}    {{.Excerpt}}
{{end}}{{if .HasURL}}    LINK: {{.URL}}
{{end}}{{if .HasNotes}}    NOTES: {{.Notes}}
{{end}}
{{end}}{{end}}{{end}}

TRACE ID: {{.TraceID}}`

func renderMarkdown(resp ipc.QueryResponse, opts Options) string {
	view := buildViewModel(resp, opts)
	var buf bytes.Buffer
	_ = markdownTemplate.Execute(&buf, view)
	return strings.TrimSpace(buf.String())
}

func renderPlain(resp ipc.QueryResponse, opts Options) string {
	view := buildViewModel(resp, opts)
	var buf bytes.Buffer
	_ = plainTemplate.Execute(&buf, view)
	return strings.TrimSpace(buf.String())
}

func buildViewModel(resp ipc.QueryResponse, opts Options) rendererViewModel {
	traceID := coalesce(resp.TraceID, opts.TraceID)
	fallback := resp.NoAnswer || resp.Confidence < opts.ConfidenceThreshold

	var fallbackBody string
	defaultFallback := "Answer is below the confidence threshold. Please rephrase your query or refresh sources via ragadmin."
	if fallback {
		fallbackBody = strings.TrimSpace(resp.Summary)
		lowered := strings.ToLower(fallbackBody)
		if fallbackBody == "" {
			fallbackBody = defaultFallback
		} else if !strings.Contains(lowered, "rephrase your query") {
			fallbackBody = fallbackBody + "\n\n" + defaultFallback
		}
	}

	truncationWarning := ""
	if resp.ContextTruncated {
		message := strings.TrimSpace(resp.Summary)
		if message == "" {
			message = "The retrieved context exceeded the token budget and was truncated. Please adjust your question or the --context-tokens limit."
		}
		truncationWarning = fmt.Sprintf("Context truncated: %s", message)
	}

	citations := enumerateCitations(resp)
	references := buildReferenceViews(citations, resp.References)

	cleanSteps := make([]string, 0, len(resp.Steps))
	for _, step := range resp.Steps {
		step = strings.TrimSpace(step)
		if step == "" {
			continue
		}
		cleanSteps = append(cleanSteps, step)
	}

	view := rendererViewModel{
		ConfidenceLine:       fmt.Sprintf("Confidence %s (threshold %s)", percentage(resp.Confidence), percentage(opts.ConfidenceThreshold)),
		TraceID:              traceID,
		Fallback:             fallback,
		FallbackBody:         fallbackBody,
		Summary:              strings.TrimSpace(resp.Summary),
		Steps:                cleanSteps,
		HasSteps:             len(cleanSteps) > 0 && !fallback,
		References:           references,
		HasReferences:        len(references) > 0 && !fallback,
		HasTruncationWarning: resp.ContextTruncated,
		TruncationWarning:    truncationWarning,
	}

	if fallback {
		view.HasSteps = false
		view.HasReferences = false
	}

	return view
}

type rendererViewModel struct {
	ConfidenceLine       string
	TraceID              string
	Fallback             bool
	FallbackBody         string
	Summary              string
	Steps                []string
	HasSteps             bool
	References           []referenceView
	HasReferences        bool
	HasTruncationWarning bool
	TruncationWarning    string
}

type referenceView struct {
	Index       int
	Alias       string
	DocumentRef string
	Excerpt     string
	URL         string
	Notes       string
	HasExcerpt  bool
	HasURL      bool
	HasNotes    bool
}

func buildReferenceViews(entries []citationEntry, refs []ipc.QueryReference) []referenceView {
	var results []referenceView
	for _, entry := range entries {
		ref := lookupReference(entry.DocumentRef, refs)
		excerpt := strings.TrimSpace(entry.Excerpt)
		view := referenceView{
			Index:       entry.Index,
			Alias:       entry.Alias,
			DocumentRef: entry.DocumentRef,
			Excerpt:     excerpt,
			HasExcerpt:  excerpt != "",
		}
		if ref != nil {
			view.URL = strings.TrimSpace(ref.URL)
			view.Notes = strings.TrimSpace(ref.Notes)
			view.HasURL = view.URL != ""
			view.HasNotes = view.Notes != ""
		}
		results = append(results, view)
	}
	return results
}

type citationEntry struct {
	Index       int
	Alias       string
	DocumentRef string
	Excerpt     string
}

func enumerateCitations(resp ipc.QueryResponse) []citationEntry {
	type key struct {
		Alias string
		Doc   string
	}
	seen := map[key]citationEntry{}
	var keys []key

	for _, citation := range resp.Citations {
		k := key{
			Alias: strings.TrimSpace(citation.Alias),
			Doc:   strings.TrimSpace(citation.DocumentRef),
		}
		if k.Alias == "" || k.Doc == "" {
			continue
		}
		if _, exists := seen[k]; exists {
			continue
		}
		entry := citationEntry{
			Alias:       k.Alias,
			DocumentRef: k.Doc,
			Excerpt:     strings.TrimSpace(citation.Excerpt),
		}
		seen[k] = entry
		keys = append(keys, k)
	}

	sort.Slice(keys, func(i, j int) bool {
		if keys[i].Alias == keys[j].Alias {
			return keys[i].Doc < keys[j].Doc
		}
		return keys[i].Alias < keys[j].Alias
	})

	results := make([]citationEntry, 0, len(keys))
	for idx, k := range keys {
		entry := seen[k]
		entry.Index = idx + 1
		results = append(results, entry)
	}
	return results
}

func lookupReference(document string, references []ipc.QueryReference) *ipc.QueryReference {
	for idx := range references {
		if strings.EqualFold(strings.TrimSpace(references[idx].Label), strings.TrimSpace(document)) {
			return &references[idx]
		}
	}
	return nil
}

func percentage(value float64) string {
	return fmt.Sprintf("%.0f%%", value*100)
}

func coalesce(values ...string) string {
	for _, v := range values {
		if strings.TrimSpace(v) != "" {
			return v
		}
	}
	return ""
}
