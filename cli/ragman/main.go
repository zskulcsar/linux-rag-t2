// Ragman serves as the CLI entry point for querying the local RAG backend.
package main

import (
	"log"

	"github.com/linux-rag-t2/cli/ragman/cmd"
)

func main() {
	if err := cmd.Execute(); err != nil {
		log.Fatal(err)
	}
}
