// Package io renders backend query responses into user-friendly presentations.
package io

import (
	"bytes"
	"encoding/json"
	"fmt"
	"sort"
	"strings"

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

func renderMarkdown(resp ipc.QueryResponse, opts Options) string {
	var buf bytes.Buffer
	buf.WriteString("Summary\n-------\n")
	buf.WriteString(resp.Summary)
	if len(resp.Steps) > 0 {
		buf.WriteString("\n\nSteps\n-----\n")
		for idx, step := range resp.Steps {
			buf.WriteString(fmt.Sprintf("%d. %s\n", idx+1, step))
		}
	}

	citationSet := enumerateCitations(resp)
	if len(citationSet) > 0 {
		buf.WriteString("\nReferences\n----------\n")
		for _, entry := range citationSet {
			buf.WriteString(fmt.Sprintf("[%d] %s — %s\n", entry.Index, entry.Alias, entry.DocumentRef))
			if entry.Excerpt != "" {
				buf.WriteString(fmt.Sprintf("    %s\n", entry.Excerpt))
			}
			if ref := lookupReference(entry.DocumentRef, resp.References); ref != nil {
				if ref.URL != "" {
					buf.WriteString(fmt.Sprintf("    Link: %s\n", ref.URL))
				}
				if ref.Notes != "" {
					buf.WriteString(fmt.Sprintf("    Notes: %s\n", ref.Notes))
				}
			}
		}
	}

	buf.WriteString("\nConfidence\n----------\n")
	buf.WriteString(fmt.Sprintf("Confidence: %s (threshold %s)\n", percentage(resp.Confidence), percentage(opts.ConfidenceThreshold)))
	if opts.TraceID != "" {
		buf.WriteString(fmt.Sprintf("Trace ID: %s\n", opts.TraceID))
	}
	return strings.TrimRight(buf.String(), "\n")
}

func renderPlain(resp ipc.QueryResponse, opts Options) string {
	var buf bytes.Buffer
	buf.WriteString("SUMMARY:\n")
	buf.WriteString(resp.Summary)
	if len(resp.Steps) > 0 {
		buf.WriteString("\n\nSTEPS:\n")
		for idx, step := range resp.Steps {
			buf.WriteString(fmt.Sprintf("%d) %s\n", idx+1, step))
		}
	}

	citationSet := enumerateCitations(resp)
	if len(citationSet) > 0 {
		buf.WriteString("\nREFERENCES:\n")
		for _, entry := range citationSet {
			line := fmt.Sprintf("[%d] %s :: %s", entry.Index, entry.Alias, entry.DocumentRef)
			buf.WriteString(line + "\n")
			if entry.Excerpt != "" {
				buf.WriteString("    " + entry.Excerpt + "\n")
			}
			if ref := lookupReference(entry.DocumentRef, resp.References); ref != nil {
				if ref.URL != "" {
					buf.WriteString("    LINK: " + ref.URL + "\n")
				}
				if ref.Notes != "" {
					buf.WriteString("    NOTES: " + ref.Notes + "\n")
				}
			}
		}
	}

	buf.WriteString("\nCONFIDENCE:\n")
	buf.WriteString(fmt.Sprintf("%s (threshold %s)\n", percentage(resp.Confidence), percentage(opts.ConfidenceThreshold)))
	if opts.TraceID != "" {
		buf.WriteString(fmt.Sprintf("TRACE ID:\n%s\n", opts.TraceID))
	}

	return strings.TrimRight(buf.String(), "\n")
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
