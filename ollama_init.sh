#!/bin/sh
# Start Ollama in the background
/bin/ollama serve &

# Wait for the server to be ready
until ollama list > /dev/null 2>&1; do sleep 1; done

# Pull the model if not already present
ollama pull gemma4:12b

# Pre-load model into GPU VRAM so the first real query isn't cold
ollama run gemma4:12b "" > /dev/null 2>&1 || true

# Keep the container running
wait