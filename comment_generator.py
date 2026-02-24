#!/usr/bin/env python3
"""Generate custom Reddit comments using LLM based on post content."""

import os
import sys
import requests
from openai import OpenAI

# Model identifiers
GEMINI_FLASH = "gemini-3-flash-preview"
GEMINI_PRO = "gemini-2.5-pro"
NVIDIA_MODEL = "z-ai/glm5"

MODEL_ALIASES = {
    "flash": GEMINI_FLASH,
    "pro": GEMINI_PRO,
    "nvidia": NVIDIA_MODEL,
}

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta/models"

# AI vocabulary to avoid
AI_WORDS_TIER1 = {
    'delve', 'crucial', 'robust', 'seamless', 'multifaceted',
    'underscore', 'underscores', 'testament', 'testaments', 'tapestry',
    'intricate', 'realm', 'realms', 'eloquent', 'eloquently', 'bustling',
    'vibrant', 'vibrancy', 'leverage', 'leveraging', 'synergy', 'synergies',
    'holistic', 'holistically', 'landscape', 'landscapes', 'ecosystem', 'ecosystems',
}

AI_WORDS_TIER2 = {
    'navigate', 'navigation', 'navigating', 'comprehensive', 'comprehensively',
    'meticulous', 'meticulously', 'paramount', 'imperative', 'imperatives',
    'dynamic', 'dynamics', 'inherent', 'inherently', 'notably',
    'pivotal', 'integral', 'integrally', 'foster', 'fosters', 'fostering',
    'cultivate', 'cultivates', 'cultivating', 'cultivation',
}


def check_ai_vocabulary(text: str) -> list[str]:
    words = text.lower().split()
    found = []
    for word in words:
        clean = word.strip('.,!?;:"()[]')
        if clean in AI_WORDS_TIER1:
            found.append(f"TIER1: {clean}")
        elif clean in AI_WORDS_TIER2:
            found.append(f"TIER2: {clean}")
    return found


def _build_prompt(title: str, body: str | None, subreddit: str) -> str:
    body_text = (body or "").strip()
    if len(body_text) > 800:
        body_text = body_text[:800] + "..."
    return f"""Write a short Reddit comment reacting to this parenting post. Under 55 words, lowercase only.

Subreddit: r/{subreddit}
Post Title: {title}
Post Body: {body_text if body_text else "[no body text]"}

STRUCTURE: Every comment must include both:
1. A brief empathetic reaction to the specific situation described
2. At least one concrete, actionable suggestion tied to the details in the post — not generic advice, something that directly addresses what they described

TONE: Casual, warm, like a friend texting. Short sentences. The tip should feel offhand, not like a parenting blog recommendation.

Natural openers: "ugh", "oh man", "yeah", "honestly", "that sounds rough", "that phase is brutal"

STRICT RULES — never break these:
- Never claim personal experience: no "been there", "same boat", "we went through this", "my kid did that", "I remember that phase", "know that feeling"
- No first person at all (no I, my, we, our)
- Only say things that are universally true or well-known — never invent a personal story
- Don't use: "absolutely", "truly", "genuinely"
- Don't sound like a parenting blog or sleep consultant
- Don't moralize

Respond with ONLY the comment text."""


def _build_retry_prompt(title: str, body: str | None, subreddit: str, bad_words: list[str]) -> str:
    body_text = (body or "").strip()
    if len(body_text) > 600:
        body_text = body_text[:600] + "..."
    avoided = ", ".join(bad_words[:5])
    return f"""Write a short Reddit comment. AVOID these words: {avoided}

Subreddit: r/{subreddit}
Post Title: {title}
Post Body: {body_text if body_text else "[no body text]"}

Casual, lowercase, under 55 words. React to the specific situation. No first person (no I, my, we). Never claim personal experience ("been there", "same boat", "my kid", "we went through this"). Only say things that are factually true or widely known. Sometimes just empathy, sometimes a tip — vary it.

Comment:"""


def _postprocess(text: str) -> str:
    text = text.strip().lower()
    if text.startswith('"') and text.endswith('"'):
        text = text[1:-1]
    if text.startswith("'") and text.endswith("'"):
        text = text[1:-1]
    return text


def _call_gemini(model: str, prompt: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not set")
    resp = requests.post(
        f"{GEMINI_BASE}/{model}:generateContent",
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=120,
    )
    resp.raise_for_status()
    return resp.json()["candidates"][0]["content"]["parts"][0]["text"]


def _call_nvidia(prompt: str) -> str:
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key:
        raise ValueError("NVIDIA_API_KEY not set")
    client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key)
    completion = client.chat.completions.create(
        model=NVIDIA_MODEL,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.85,
        top_p=0.92,
        max_tokens=150,
        timeout=60,
        extra_body={"chat_template_kwargs": {"enable_thinking": False, "clear_thinking": True}},
        stream=False,
    )
    return completion.choices[0].message.content


def _call_one(model: str, prompt: str) -> str:
    """Call a specific model by name or alias."""
    resolved = MODEL_ALIASES.get(model, model)
    if resolved in (GEMINI_FLASH, GEMINI_PRO) or resolved.startswith("gemini"):
        return _call_gemini(resolved, prompt)
    return _call_nvidia(prompt)


def _call_cascade(prompt: str) -> str:
    """Try flash → pro → nvidia in order. Raises if all fail."""
    errors = []
    for fn in [
        lambda: _call_gemini(GEMINI_FLASH, prompt),
        lambda: _call_gemini(GEMINI_PRO, prompt),
        lambda: _call_nvidia(prompt),
    ]:
        try:
            return fn()
        except Exception as e:
            errors.append(str(e))
    raise RuntimeError(f"All LLM providers failed: {errors}")


def generate_comment(title: str, body: str | None, subreddit: str, model: str | None = None) -> str:
    """Generate a Reddit comment. Raises on failure."""
    prompt = _build_prompt(title, body, subreddit)
    call = (lambda p: _call_one(model, p)) if model else _call_cascade

    comment = _postprocess(call(prompt))

    ai_words = check_ai_vocabulary(comment)
    if ai_words:
        retry_prompt = _build_retry_prompt(title, body, subreddit, ai_words)
        comment = _postprocess(call(retry_prompt))

    return comment


def main():
    """CLI for testing comment generation."""
    import argparse
    ap = argparse.ArgumentParser(description="Generate a Reddit comment using an LLM.")
    ap.add_argument("title", help="Post title")
    ap.add_argument("body", nargs="?", default=None, help="Post body (optional)")
    ap.add_argument("subreddit", nargs="?", default="Parenting", help="Subreddit name (default: Parenting)")
    ap.add_argument(
        "--model",
        default=None,
        metavar="MODEL",
        help=(
            f"Model to use: 'flash' ({GEMINI_FLASH}), 'pro' ({GEMINI_PRO}), "
            f"'nvidia' ({NVIDIA_MODEL}), or a full model name. "
            "Omit to try all three in order."
        ),
    )
    args = ap.parse_args()

    print(f"\nPost: {args.title}")
    if args.body:
        print(f"Body: {args.body}")
    print(f"Subreddit: r/{args.subreddit}")
    if args.model:
        resolved = MODEL_ALIASES.get(args.model, args.model)
        print(f"Model: {resolved}")
    else:
        print(f"Model: cascade ({GEMINI_FLASH} → {GEMINI_PRO} → {NVIDIA_MODEL})")
    print("-" * 50)

    comment = generate_comment(args.title, args.body, args.subreddit, model=args.model)

    print(f"\nGenerated comment:\n{comment}")

    ai_words = check_ai_vocabulary(comment)
    if ai_words:
        print(f"\nAI vocabulary detected: {ai_words}")


if __name__ == "__main__":
    main()
