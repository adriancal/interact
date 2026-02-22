#!/usr/bin/env python3
"""Generate custom Reddit comments using LLM based on post content."""

import os
import sys
from openai import OpenAI

# Load API key from environment
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
if not NVIDIA_API_KEY:
    raise ValueError("NVIDIA_API_KEY not found in environment. Check .env file.")

# AI vocabulary to avoid (from humanizer skill)
AI_WORDS_TIER1 = {
    'delve', 'crucial', 'robust', 'seamless', 'multifaceted', 'multifaceted',
    'underscore', 'underscores', 'underscores', 'underscores', 'underscores',
    'testament', 'testaments', 'tapestry', 'intricate', 'realm', 'realms',
    'eloquent', 'eloquently', 'bustling', 'vibrant', 'vibrancy',
    'leverage', 'leveraging', 'synergy', 'synergies', 'holistic', 'holistically',
    'landscape', 'landscapes', 'ecosystem', 'ecosystems',
}

AI_WORDS_TIER2 = {
    'navigate', 'navigation', 'navigating', 'comprehensive', 'comprehensively',
    'meticulous', 'meticulously', 'paramount', 'imperative', 'imperatives',
    'dynamic', 'dynamics', 'inherent', 'inherently', 'notably', 'underscore',
    'underscores', 'pivotal', 'integral', 'integrally', 'foster', 'fosters',
    'fostering', 'cultivate', 'cultivates', 'cultivating', 'cultivation',
}

def check_ai_vocabulary(text: str) -> list[str]:
    """Check for AI-sounding words"""
    words = text.lower().split()
    found = []
    for word in words:
        clean = word.strip('.,!?;:"()[]')
        if clean in AI_WORDS_TIER1:
            found.append(f"TIER1: {clean}")
        elif clean in AI_WORDS_TIER2:
            found.append(f"TIER2: {clean}")
    return found

def generate_comment(title: str, body: str | None, subreddit: str) -> str:
    """Generate a custom Reddit comment based on post content."""
    
    import sys
    print("DEBUG: Starting comment generation...", file=sys.stderr)
    sys.stderr.flush()
    
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=NVIDIA_API_KEY
    )
    print("DEBUG: Client created, calling API...", file=sys.stderr)
    sys.stderr.flush()
    
    # Truncate body if too long
    body_text = (body or "").strip()
    if len(body_text) > 800:
        body_text = body_text[:800] + "..."
    
    # Build prompt with strict rules
    prompt = f"""Write a brief, helpful comment responding to this Reddit post.

Subreddit: r/{subreddit}
Post Title: {title}
Post Body: {body_text if body_text else "[no body text]"}

RULES:
- Keep it to 1-2 sentences, max 50 words
- Write in lowercase only (like natural casual conversation)
- Be specific to THIS post — reference details from the title/body
- Sound personal and human, not generic
- NO AI vocabulary: avoid words like "delve", "crucial", "robust", "seamless", "underscore", "multifaceted", "testament", "tapestry", "realm", "navigate", "comprehensive", "meticulous", "paramount", "pivotal", "foster", "cultivate"
- NO filler phrases like "it's important to note that", "at the end of the day"
- Give ONE concrete piece of advice specific to this situation
- Don't be preachy or judgmental

Respond with ONLY the comment text, nothing else."""

    try:
        completion = client.chat.completions.create(
            model="z-ai/glm5",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            top_p=0.9,
            max_tokens=150,
            extra_body={"chat_template_kwargs": {"enable_thinking": False, "clear_thinking": True}},
            stream=False
        )
        
        comment = completion.choices[0].message.content.strip()
        
        # Post-process
        comment = comment.lower()
        
        # Remove quotes if AI wrapped it
        if comment.startswith('"') and comment.endswith('"'):
            comment = comment[1:-1]
        if comment.startswith("'") and comment.endswith("'"):
            comment = comment[1:-1]
        
        # Check for AI vocabulary
        ai_words = check_ai_vocabulary(comment)
        if ai_words:
            # Regenerate once if AI words found
            return generate_comment_retry(title, body, subreddit, ai_words)
        
        return comment
        
    except Exception as e:
        return f"error generating comment: {str(e)}"

def generate_comment_retry(title: str, body: str | None, subreddit: str, bad_words: list[str]) -> str:
    """Retry with stricter instructions if AI words found."""
    
    client = OpenAI(
        base_url="https://integrate.api.nvidia.com/v1",
        api_key=NVIDIA_API_KEY
    )
    
    body_text = (body or "").strip()
    if len(body_text) > 600:
        body_text = body_text[:600] + "..."
    
    avoided = ", ".join(bad_words[:5])
    
    prompt = f"""Write a brief Reddit comment. AVOID these words: {avoided}

Subreddit: r/{subreddit}
Post Title: {title}
Post Body: {body_text if body_text else "[no body text]"}

RULES:
- 1-2 sentences max
- lowercase only, casual tone
- specific to this post's details
- simple words only, avoid fancy vocabulary
- one concrete tip only

Comment:"""

    try:
        completion = client.chat.completions.create(
            model="z-ai/glm5",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.6,
            max_tokens=100,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            stream=False
        )
        
        comment = completion.choices[0].message.content.strip().lower()
        
        if comment.startswith('"') and comment.endswith('"'):
            comment = comment[1:-1]
        
        return comment
        
    except Exception as e:
        return f"error: {str(e)}"

def main():
    """CLI for testing comment generation."""
    if len(sys.argv) < 2:
        print("Usage: python comment_generator.py 'Post title' [optional body text]")
        print("\nExample:")
        print('  python comment_generator.py "My 3 year old throws tantrums at bedtime" "He screams for an hour every night"')
        sys.exit(1)
    
    title = sys.argv[1]
    body = sys.argv[2] if len(sys.argv) > 2 else None
    subreddit = sys.argv[3] if len(sys.argv) > 3 else "parenting"
    
    print(f"\nPost: {title}")
    if body:
        print(f"Body: {body}")
    print(f"Subreddit: r/{subreddit}")
    print("-" * 50)
    
    comment = generate_comment(title, body, subreddit)
    
    print(f"\nGenerated comment:\n{comment}")
    
    # Check for issues
    ai_words = check_ai_vocabulary(comment)
    if ai_words:
        print(f"\n⚠️  AI vocabulary detected: {ai_words}")

if __name__ == "__main__":
    main()
