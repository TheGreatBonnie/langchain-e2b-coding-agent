"""Local LLM client for summarizing Hacker News stories via Ollama."""

import httpx
import os

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")


async def summarize_story(title: str, url: str | None, score: int, descendants: int) -> str:
    """Generate a summary for a Hacker News story using a local Ollama model.

    Returns a fallback message if Ollama is unavailable.
    """
    context = f"Title: {title}\n"
    if url:
        context += f"URL: {url}\n"
    context += f"Score: {score} points\n"
    context += f"Comments: {descendants}\n"

    prompt = (
        "You are a helpful assistant. Summarize the following Hacker News story "
        "in 2-3 concise sentences. Focus on the key topic and why it's interesting.\n\n"
        f"{context}\n\nSummary:"
    )

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": OLLAMA_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 200,
                    },
                },
            )
            response.raise_for_status()
            result = response.json()
            return result["response"].strip()
    except Exception as e:
        return f"Summary unavailable (LLM error: {type(e).__name__})"
