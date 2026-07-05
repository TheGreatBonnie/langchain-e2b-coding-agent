"""Local LLM summarizer using Ollama."""

import ollama

MODEL = "llama3.2"
SYSTEM_PROMPT = "You are a concise tech news summarizer. Given a Hacker News story title and URL, write a 2-3 sentence summary explaining what it is and why it matters."


def summarize_story(title: str, url: str | None = None) -> str:
    """Summarize a single HN story using the local Ollama model."""
    user_prompt = f"Title: {title}\nURL: {url or 'N/A'}\n\nSummarize this story in 2-3 sentences."

    response = ollama.chat(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        options={"temperature": 0.4, "num_predict": 150},
    )
    return response["message"]["content"]


def summarize_stories(stories: list[dict]) -> list[dict]:
    """Add a `summary` field to each story dict. Modifies in place and returns."""
    for story in stories:
        try:
            story["summary"] = summarize_story(story["title"], story.get("url"))
        except Exception as e:
            story["summary"] = f"[summary failed: {e}]"
    return stories
