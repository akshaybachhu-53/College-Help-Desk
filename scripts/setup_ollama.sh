#!/usr/bin/env bash
# Pull the models and create "helpdesk-*" variants with an 8K context window.
# Ollama's default context (2K-4K) is too small for tool schemas + retrieved passages:
# the prompt gets silently truncated and the model "forgets" its instructions.
set -e
ollama pull nomic-embed-text
ollama pull qwen3:8b
ollama pull llama3.1:8b
for base in qwen3:8b llama3.1:8b; do
  name="helpdesk-${base}"
  printf 'FROM %s\nPARAMETER num_ctx 8192\nPARAMETER temperature 0.2\n' "$base" > /tmp/Modelfile.helpdesk
  ollama create "$name" -f /tmp/Modelfile.helpdesk
  echo "created $name"
done
ollama list
