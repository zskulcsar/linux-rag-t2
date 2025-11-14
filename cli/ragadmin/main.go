// Ragadmin exposes administrative workflows for managing knowledge sources.
package main

import (
	"log"

	"github.com/linux-rag-t2/cli/ragadmin/cmd"
)

func main() {
	if err := cmd.Execute(); err != nil {
		log.Fatal(err)
	}
}

