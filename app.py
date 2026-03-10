#!/usr/bin/env python3
"""
Crossroads Web — Flask backend
Serves the game UI and proxies AI requests to Claude or Gemini.

Usage:
    python3 app.py                                          # Players pick their provider
    ANTHROPIC_API_KEY=sk-... python3 app.py                 # Server-side Claude key
    GEMINI_API_KEY=AI... python3 app.py                     # Server-side Gemini key (FREE)

If a server-side key is set, all players use it automatically.
Otherwise, each player enters their own key in the browser.
"""

import os
import json
import re
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

SERVER_ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
SERVER_GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
SERVER_GROQ_KEY = os.environ.get("GROQ_API_KEY")

SYSTEM_PROMPT = """You are the narrator of "Crossroads," an immersive text-based visual novel set in the modern real world. Your writing style is literary, vivid, and emotionally resonant — like a great novel come to life.

RULES:
1. Generate compelling, grounded-in-reality narratives. No fantasy, sci-fi, or supernatural elements unless the player's choices naturally lead there.
2. Include rich sensory details — sights, sounds, smells, textures.
3. Create believable, complex NPC characters with distinct voices and motivations.
4. Always present EXACTLY 4 choices for the player. Choices should be meaningfully different and lead to genuinely different outcomes.
5. Track and reflect the consequences of previous choices naturally in the narrative.
6. Incorporate real-world challenges: financial pressures, workplace dynamics, relationship complexity, ethical dilemmas, health concerns, social issues, career decisions.
7. Make the world feel alive — other characters have their own lives, plans, and problems.
8. When characters speak, format their dialogue with their name on a separate line followed by their words.

RESPONSE FORMAT (you MUST follow this exactly):
[LOCATION]
<current location name>

[NARRATION]
<2-4 paragraphs of vivid narration, including any NPC dialogue. When an NPC speaks, write it as:
**CharacterName:** "Their dialogue here."
>

[CHOICES]
1. <first choice>
2. <second choice>
3. <third choice>
4. <fourth choice>

[STAT_CHANGES]
<JSON object with stat changes from the PREVIOUS choice, e.g. {"reputation": 5, "wealth": -10}>

Keep narration between 150-300 words. Make every word count."""

ENDING_PROMPT = """You are concluding a playthrough of "Crossroads." Based on the player's full journey, generate a unique, emotionally resonant ending.

RESPONSE FORMAT:
[ENDING_TITLE]
<A poetic 2-5 word title for this ending>

[ENDING_TEXT]
<3-5 paragraphs wrapping up the story. Reference specific choices and their consequences. Be reflective and meaningful. Show how the character's journey has changed them. End with a final image or thought that lingers.>

[STAT_CHANGES]
<final stat adjustments as JSON>

Make this ending UNIQUE to this specific playthrough. No two players should get the same ending."""


# ─── AI Provider Calls ───

def call_claude(messages, system_prompt, api_key):
    """Call Claude API and return the response text."""
    import anthropic
    client = anthropic.Anthropic(api_key=api_key)
    response = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=1500,
        system=system_prompt,
        messages=messages,
    )
    return response.content[0].text


def call_gemini(messages, system_prompt, api_key):
    """Call Google Gemini API directly via REST — no SDK needed."""
    import requests as req

    user_content = messages[-1]["content"]

    models_to_try = [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash-latest",
        "gemini-pro",
    ]

    last_error = None
    for model_name in models_to_try:
        url = f"https://generativelanguage.googleapis.com/v1/models/{model_name}:generateContent?key={api_key}"
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": system_prompt + "\n\n" + user_content}]}
            ],
            "generationConfig": {
                "maxOutputTokens": 1500,
                "temperature": 0.9,
            }
        }

        resp = req.post(url, json=payload, timeout=60)

        if resp.status_code == 200:
            data = resp.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]

        err_str = resp.text
        last_error = err_str
        # Try next model on quota/not-found errors
        if resp.status_code in (429, 404, 503) or "RESOURCE_EXHAUSTED" in err_str or "NOT_FOUND" in err_str:
            continue
        # Other errors — raise immediately
        raise Exception(f"Gemini API error ({resp.status_code}): {err_str[:300]}")

    raise Exception(
        "Gemini API quota not yet active. New API keys can take 5-10 minutes "
        "to activate. Please wait a few minutes and try again. If it persists, "
        "visit console.cloud.google.com and enable the 'Generative Language API'."
    )


def call_groq(messages, system_prompt, api_key):
    """Call Groq API — free, fast, OpenAI-compatible."""
    import requests as req

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": system_prompt},
            *messages,
        ],
        "max_tokens": 1500,
        "temperature": 0.9,
    }

    resp = req.post(url, json=payload, headers=headers, timeout=60)

    if resp.status_code == 200:
        data = resp.json()
        return data["choices"][0]["message"]["content"]

    raise Exception(f"Groq API error ({resp.status_code}): {resp.text[:300]}")


def call_ai(messages, system_prompt, provider, api_key):
    """Route to the appropriate AI provider."""
    if provider == "gemini":
        return call_gemini(messages, system_prompt, api_key)
    elif provider == "groq":
        return call_groq(messages, system_prompt, api_key)
    else:
        return call_claude(messages, system_prompt, api_key)


# ─── Response Parsing ───

def parse_scene(text):
    """Parse AI response into structured scene data."""
    result = {"location": "Unknown", "narration": "", "choices": [], "stat_changes": {}}

    # Try multi-line first, then same-line format
    loc = re.search(r"\[LOCATION\]\s*\n(.+?)(?:\n\n|\n\[)", text, re.DOTALL)
    if not loc:
        loc = re.search(r"\[LOCATION\]\s*:?\s*(.+?)(?:\n|$)", text)
    if loc:
        result["location"] = loc.group(1).strip().strip('*')

    narr = re.search(r"\[NARRATION\]\s*\n(.+?)(?:\n\[CHOICES\])", text, re.DOTALL)
    if narr:
        result["narration"] = narr.group(1).strip()

    ch = re.search(r"\[CHOICES\]\s*\n(.+?)(?:\n\[|$)", text, re.DOTALL)
    if ch:
        choices = re.findall(r"\d+\.\s*(.+?)(?:\n|$)", ch.group(1).strip())
        result["choices"] = [c.strip() for c in choices if c.strip()]

    st = re.search(r"\[STAT_CHANGES\]\s*\n(.+?)(?:\n\[|$)", text, re.DOTALL)
    if st:
        try:
            s = re.sub(r':\s*\+', ': ', st.group(1).strip())
            result["stat_changes"] = json.loads(s)
        except (json.JSONDecodeError, ValueError):
            pass

    while len(result["choices"]) < 4:
        result["choices"].append("Consider your options carefully")
    result["choices"] = result["choices"][:4]

    return result


def parse_ending(text):
    """Parse ending response."""
    result = {"title": "The End", "text": "", "stat_changes": {}}

    t = re.search(r"\[ENDING_TITLE\]\s*\n(.+?)(?:\n\n|\n\[)", text, re.DOTALL)
    if not t:
        t = re.search(r"\[ENDING_TITLE\]\s*:?\s*(.+?)(?:\n|$)", text)
    if t:
        result["title"] = t.group(1).strip().strip('*')

    tx = re.search(r"\[ENDING_TEXT\]\s*\n(.+?)(?:\n\[|$)", text, re.DOTALL)
    if tx:
        result["text"] = tx.group(1).strip()

    st = re.search(r"\[STAT_CHANGES\]\s*\n(.+?)(?:\n\[|$)", text, re.DOTALL)
    if st:
        try:
            s = re.sub(r':\s*\+', ': ', st.group(1).strip())
            result["stat_changes"] = json.loads(s)
        except (json.JSONDecodeError, ValueError):
            pass

    return result


# ─── Routes ───

@app.route("/")
def index():
    server_provider = None
    if SERVER_GROQ_KEY:
        server_provider = "groq"
    elif SERVER_GEMINI_KEY:
        server_provider = "gemini"
    elif SERVER_ANTHROPIC_KEY:
        server_provider = "anthropic"
    return render_template("index.html", server_provider=server_provider)


@app.route("/api/generate", methods=["POST"])
def generate():
    """Generate a scene or ending via AI."""
    data = request.json
    provider = data.get("provider", "gemini")

    # Determine API key: server-side first, then client-provided
    if provider == "gemini":
        api_key = SERVER_GEMINI_KEY or data.get("api_key")
    elif provider == "groq":
        api_key = SERVER_GROQ_KEY or data.get("api_key")
    else:
        api_key = SERVER_ANTHROPIC_KEY or data.get("api_key")

    if not api_key:
        return jsonify({"error": "No API key provided"}), 400

    action = data.get("action", "scene")
    player_name = data.get("player_name", "Player")
    stats = data.get("stats", {})
    history = data.get("history", [])
    scene_num = data.get("scene_num", 1)
    background = data.get("background", "")
    location = data.get("location", "")

    try:
        if action == "opening":
            location_instruction = f"The story is set in {location}. Ground all details — streets, landmarks, weather, culture, atmosphere — in this real location." if location else ""
            messages = [{
                "role": "user",
                "content": (
                    f"Generate the opening scene for a new game. The player's name is "
                    f"{player_name} and their chosen background is: {background}.\n\n"
                    f"{location_instruction}\n\n"
                    f"Create an immersive, real-world opening that establishes their "
                    f"situation, introduces at least one NPC, and presents 4 meaningful "
                    f"first choices. Set it in a specific, vivid real-world location "
                    f"within {location if location else 'a modern city'}."
                ),
            }]
            raw = call_ai(messages, SYSTEM_PROMPT, provider, api_key)
            return jsonify(parse_scene(raw))

        elif action == "scene":
            history_summary = "\n".join(
                f"Scene {h['scene']}: At {h['location']}, chose: \"{h['choice']}\""
                for h in history[-8:]
            )
            stats_str = ", ".join(f"{k}: {v}" for k, v in stats.items())

            tension = ""
            if scene_num > 12:
                tension = "The story is building toward a climax — raise the stakes."
            if scene_num > 18:
                tension = "This scene should feel like things are reaching a turning point."

            location_context = f"The story is set in {location}. Keep all scenes grounded in this real location." if location else ""
            messages = [{
                "role": "user",
                "content": (
                    f"Generate scene {scene_num} for player '{player_name}'.\n\n"
                    f"{location_context}\n\n"
                    f"Current stats: {stats_str}\n\n"
                    f"Recent history:\n{history_summary}\n\n"
                    f"Continue the story naturally from the last choice. Introduce new "
                    f"developments, characters, or complications. The narrative should "
                    f"feel like a natural progression with real consequences.\n\n{tension}"
                ),
            }]
            raw = call_ai(messages, SYSTEM_PROMPT, provider, api_key)
            return jsonify(parse_scene(raw))

        elif action == "ending":
            history_summary = "\n".join(
                f"Scene {h['scene']}: At {h['location']}, chose: \"{h['choice']}\""
                for h in history
            )
            stats_str = ", ".join(f"{k}: {v}" for k, v in stats.items())

            messages = [{
                "role": "user",
                "content": (
                    f"Generate the ending for player '{player_name}'.\n\n"
                    f"Final stats: {stats_str}\n\n"
                    f"Complete journey:\n{history_summary}\n\n"
                    f"Create a unique, meaningful ending that reflects this specific "
                    f"journey. Reference key moments and choices. Show growth, "
                    f"consequences, and where life goes from here."
                ),
            }]
            raw = call_ai(messages, ENDING_PROMPT, provider, api_key)
            return jsonify(parse_ending(raw))

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    return jsonify({"error": "Invalid action"}), 400


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"\n  CROSSROADS WEB — running at http://localhost:{port}")
    if SERVER_GROQ_KEY:
        print(f"  AI Mode: Groq (FREE) — server key active")
    elif SERVER_GEMINI_KEY:
        print(f"  AI Mode: Gemini (FREE) — server key active")
    elif SERVER_ANTHROPIC_KEY:
        print(f"  AI Mode: Claude — server key active")
    else:
        print(f"  AI Mode: Players will choose their provider and enter their own key")
    print()
    app.run(host="0.0.0.0", port=port, debug=False)
