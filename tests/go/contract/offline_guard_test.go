package contract_test

import (
	"errors"
	"io"
	"net/http"
	"strings"
	"testing"

	"github.com/linux-rag-t2/cli/shared/ipc"
)

type roundTripperFunc func(*http.Request) (*http.Response, error)

func (fn roundTripperFunc) RoundTrip(req *http.Request) (*http.Response, error) {
	return fn(req)
}

func TestOfflineGuardBlocksExternalHTTPForRagman(t *testing.T) {
	var calls int
	originalTransport := http.DefaultTransport
	http.DefaultTransport = roundTripperFunc(func(req *http.Request) (*http.Response, error) {
		calls++
		return nil, errors.New("external dial attempted")
	})
	t.Cleanup(func() {
		http.DefaultTransport = originalTransport
	})

	restore := ipc.InstallOfflineHTTPGuard()
	t.Cleanup(restore)

	resp, err := http.Get("https://example.com/api")
	if !errors.Is(err, ipc.ErrExternalNetworkBlocked) {
		t.Fatalf("expected offline guard error, got response=%v err=%v", resp, err)
	}
	if calls != 0 {
		t.Fatalf("expected guard to block before transport, got %d transport call(s)", calls)
	}
}

func TestOfflineGuardAllowsLoopbackForRagadminHealth(t *testing.T) {
	originalTransport := http.DefaultTransport
	var calls int
	http.DefaultTransport = roundTripperFunc(func(req *http.Request) (*http.Response, error) {
		calls++
		body := io.NopCloser(strings.NewReader("ok"))
		return &http.Response{
			StatusCode: http.StatusOK,
			Body:       body,
		}, nil
	})
	t.Cleanup(func() {
		http.DefaultTransport = originalTransport
	})

	restore := ipc.InstallOfflineHTTPGuard()
	t.Cleanup(restore)

	resp, err := http.Get("http://127.0.0.1:11434/api/tags")
	if err != nil {
		t.Fatalf("expected loopback request to succeed, got error: %v", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		t.Fatalf("expected HTTP 200, got %d", resp.StatusCode)
	}
	if calls != 1 {
		t.Fatalf("expected exactly one transport call for loopback request, got %d", calls)
	}
}
