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
import random
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

SERVER_ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY")
SERVER_GEMINI_KEY = os.environ.get("GEMINI_API_KEY")
# Support multiple Groq keys for automatic failover
GROQ_KEYS = [k for k in [
    os.environ.get("GROQ_API_KEY"),
    os.environ.get("GROQ_API_KEY_1"),
    os.environ.get("GROQ_API_KEY_2"),
] if k]
SERVER_GROQ_KEY = GROQ_KEYS[0] if GROQ_KEYS else None


# ─── Story Randomization ───

OPENING_SCENARIOS = [
    "The player witnesses something they shouldn't have — a secret exchange, a crime, or a hidden truth",
    "The player receives an unexpected message from someone they haven't heard from in years",
    "The player finds a mysterious object — a letter, a key, a phone with one contact",
    "The player is stranded somewhere unfamiliar after a sudden change of plans",
    "The player overhears a conversation that changes everything they thought they knew",
    "The player arrives at a new job on their first day and immediately senses something is off",
    "The player runs into someone from their past at the worst possible moment",
    "The player discovers their neighbor/colleague has disappeared under strange circumstances",
    "The player wakes up to find something in their possession that doesn't belong to them",
    "The player is caught in the middle of a conflict between two people they care about",
    "The player receives a once-in-a-lifetime opportunity but the catch is unclear",
    "The player stumbles into an underground community or hidden world within their city",
    "A stranger asks the player for help with something oddly specific and urgent",
    "The player's routine day is interrupted by a natural disaster, protest, or citywide event",
    "The player inherits something unexpected from a relative they barely knew",
    "The player is mistaken for someone else and drawn into that person's life",
    "The player finds a hidden room, passage, or space that shouldn't exist",
    "The player's best friend confesses something that puts their friendship to the test",
    "The player gets locked out/in somewhere and must figure out their next move",
    "The player discovers a talent or ability they never knew they had",
]

NARRATIVE_TONES = [
    "noir and atmospheric — shadows, secrets, morally grey characters",
    "warm and hopeful — found family, unexpected kindness, second chances",
    "tense and suspenseful — paranoia, time pressure, trust no one",
    "whimsical and quirky — absurd coincidences, eccentric characters, humor",
    "melancholic and introspective — loss, memory, bittersweet beauty",
    "gritty and raw — street-level survival, hard choices, real consequences",
    "romantic and passionate — chemistry, longing, complicated love",
    "mysterious and eerie — things don't add up, uncanny details, secrets",
    "adventurous and energetic — exploration, discovery, adrenaline",
    "philosophical and thoughtful — big questions, moral dilemmas, meaning",
]

NPC_ARCHETYPES = [
    "a charismatic stranger with an ulterior motive",
    "a childhood friend who has changed dramatically",
    "an elderly mentor figure with a dark secret",
    "a rival who could also be an ally",
    "a street vendor who knows everyone's business",
    "a nervous newcomer who is clearly hiding something",
    "a confident artist who lives by their own rules",
    "a burnt-out professional questioning their life choices",
    "a mischievous kid who is smarter than they let on",
    "a quiet observer who notices everything",
    "a loud, opinionated local who commands the room",
    "a mysterious foreigner passing through town",
    "an old flame who never got closure",
    "a conspiracy theorist who might actually be right",
    "a gentle healer — nurse, therapist, or herbalist — with their own wounds",
]

TIME_SETTINGS = [
    "early morning, just before dawn — the city is waking up",
    "golden hour, late afternoon — warm light bathes everything",
    "a rainy evening — puddles reflect neon, umbrellas crowd the streets",
    "deep night, past midnight — the city belongs to insomniacs and dreamers",
    "a foggy morning — visibility is low, sounds are muffled",
    "a hot midday — shade is precious, tempers run short",
    "dusk, the magic hour — sky turns purple and orange",
    "a snowy morning — everything is muted and still",
    "a windy afternoon — papers fly, people hold their hats",
    "a stormy night — thunder rumbles, power flickers",
]


def generate_story_seed():
    """Generate a unique combination of random story elements."""
    return {
        "scenario": random.choice(OPENING_SCENARIOS),
        "tone": random.choice(NARRATIVE_TONES),
        "npc": random.choice(NPC_ARCHETYPES),
        "time": random.choice(TIME_SETTINGS),
        "theme_avoid": random.sample([
            "business meetings", "job interviews", "office politics",
            "investment decisions", "startup pitches", "corporate espionage",
            "real estate deals", "stock trading", "networking events",
        ], 3),
    }


SYSTEM_PROMPT = """You are the narrator of "Crossroads," an immersive text-based visual novel set in the modern real world. Your writing style is literary, vivid, and emotionally resonant — like a great novel come to life.

RULES:
1. Generate compelling, grounded-in-reality narratives. Keep things realistic but exciting.
2. Include rich sensory details — sights, sounds, smells, textures.
3. Create believable, complex NPC characters with distinct voices and motivations.
4. Always present EXACTLY 4 choices for the player. Choices should be meaningfully different and lead to genuinely different outcomes.
5. Track and reflect the consequences of previous choices naturally in the narrative.
6. IMPORTANT — VARY THE GENRE AND TONE across scenes. Do NOT default to business/investing/corporate scenarios. Rotate through diverse themes:
   - Romance and relationships (meeting someone, heartbreak, rekindling love)
   - Adventure and exploration (discovering hidden places, spontaneous travel, unexpected journeys)
   - Mystery and intrigue (strange occurrences, secrets uncovered, puzzles to solve)
   - Comedy and lighthearted moments (awkward situations, funny encounters, absurd coincidences)
   - Drama and conflict (family tensions, moral dilemmas, difficult confrontations)
   - Personal growth (overcoming fears, learning new skills, self-discovery)
   - Friendship and community (helping strangers, building bonds, neighborhood events)
   - Danger and suspense (close calls, risky situations, time pressure)
7. Make the world feel alive — other characters have their own lives, plans, and problems.
8. When characters speak, format their dialogue with their name on a separate line followed by their words.
9. Build recurring characters that appear across multiple scenes — give them arcs too.

RESPONSE FORMAT (you MUST follow this exactly):
[LOCATION]
<IMPORTANT: This MUST be a specific place name that changes as the story moves. NEVER just write the city name. Examples: "Al Fahidi Historical District, Dubai", "The Spice Souk, Deira", "Jumeirah Beach Promenade", "Rosa's Cafe, Brooklyn Heights", "Platform 9, King's Cross Station". Each scene should have a DIFFERENT specific location reflecting where the action is happening.>

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

ENDING_PROMPT = """You are concluding a playthrough of "Crossroads." Based on the player's full journey, generate a unique, emotionally resonant ending that feels like a natural resolution — NOT a cliffhanger.

RULES:
1. The ending must feel COMPLETE and SATISFYING. Wrap up all major story threads.
2. Do NOT end on unresolved tension, unanswered questions, or "to be continued" energy.
3. Show the aftermath — where the character ends up, how their relationships settled, what changed.
4. Reference specific choices and their consequences throughout the journey.
5. Include a "Roads Not Taken" section imagining how 2-3 key decisions could have played out differently.

RESPONSE FORMAT:
[ENDING_TITLE]
<A poetic 2-5 word title for this ending>

[ENDING_TEXT]
<4-6 paragraphs wrapping up the story smoothly. Start by resolving the current situation naturally. Then zoom out to show the bigger picture — how the character's life has changed. Reference key moments and choices. Show growth and consequences. End with a warm, reflective final image that gives closure — a sunset, a quiet moment, a smile, a door opening to the future. This should feel like the last page of a great novel, not a sudden stop.>

[ROADS_NOT_TAKEN]
<2-3 short "what if" paragraphs. For each, pick a pivotal choice the player made and imagine what might have happened if they chose differently. Format each as:
"What if you had [alternative choice]? [1-2 sentences describing the alternate outcome]."
Keep these speculative and intriguing — show the player how different their story could have been.>

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


def _groq_request(messages, system_prompt, api_key):
    """Make a single Groq API request. Returns (success, result_or_error, is_rate_limit)."""
    import requests as req

    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": "openai/gpt-oss-120b",
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
        return True, data["choices"][0]["message"]["content"], False

    is_rate_limit = resp.status_code == 429 or "rate_limit" in resp.text.lower()
    return False, resp.text[:300], is_rate_limit


def call_groq(messages, system_prompt, api_key):
    """Call Groq API with automatic key failover."""
    # Build list of keys to try: provided key first, then all server keys
    keys_to_try = [api_key]
    for k in GROQ_KEYS:
        if k != api_key and k not in keys_to_try:
            keys_to_try.append(k)

    last_error = ""
    for key in keys_to_try:
        success, result, is_rate_limit = _groq_request(messages, system_prompt, key)
        if success:
            return result
        last_error = result
        if not is_rate_limit:
            break  # Only retry with next key on rate limits

    raise Exception(f"Groq API error: {last_error}")


def call_ai(messages, system_prompt, provider, api_key):
    """Route to the appropriate AI provider."""
    if provider == "gemini":
        return call_gemini(messages, system_prompt, api_key)
    elif provider == "groq":
        return call_groq(messages, system_prompt, api_key)
    else:
        return call_claude(messages, system_prompt, api_key)


# ─── Response Parsing ───

def clean_narration(text):
    """Remove any leaked JSON, tags, or numbered choices from narration."""
    text = re.sub(r'\{["\s]*\w+["\s]*:.*?\}', '', text)
    text = re.sub(r'\[.*?\]', '', text)
    # Remove numbered choices that leaked in (1. 2. 3. 4.)
    text = re.sub(r'\n\s*\d+\.\s+.+', '', text)
    return text.strip()


# Common city names to detect generic locations
GENERIC_CITIES = {
    "new york", "new york city", "nyc", "london", "tokyo", "lagos", "dubai",
    "paris", "mumbai", "são paulo", "sao paulo", "sydney", "berlin",
    "los angeles", "chicago", "toronto", "singapore", "hong kong",
    "san francisco", "seattle", "boston", "miami", "amsterdam", "rome",
    "barcelona", "istanbul", "cairo", "nairobi", "bangkok", "seoul",
    "shanghai", "beijing", "moscow", "rio de janeiro", "buenos aires",
}


def extract_location_from_narration(narration):
    """Try to find a specific place name from the narration text."""
    # Look for place patterns like "at the ___", "inside ___", "in the ___", "at ___'s"
    patterns = [
        r"(?:walked into|entered|stepped into|arrived at|inside|at)\s+(?:the\s+)?([A-Z][A-Za-z'\s]+(?:Cafe|Café|Restaurant|Bar|Hotel|Shop|Store|Market|Museum|Gallery|Park|Station|Terminal|Hospital|Library|Office|Tower|Plaza|Square|Club|Gym|Studio|Theater|Theatre|Church|Mosque|Temple|Garden|Beach|Harbor|Harbour|Port|Airport|Mall|Center|Centre))",
        r"(?:at|inside|into)\s+([A-Z][A-Za-z']+(?:'s)?(?:\s+[A-Z][A-Za-z']+)*)",
    ]
    for pattern in patterns:
        match = re.search(pattern, narration)
        if match:
            place = match.group(1).strip()
            if len(place) > 3 and place.lower() not in GENERIC_CITIES:
                return place
    return None


def parse_scene(text):
    """Parse AI response into structured scene data."""
    result = {"location": "Unknown", "narration": "", "choices": [], "stat_changes": {}}

    # Try multi-line first, then same-line format
    loc = re.search(r"\[LOCATION\]\s*\n(.+?)(?:\n\n|\n\[)", text, re.DOTALL)
    if not loc:
        loc = re.search(r"\[LOCATION\]\s*:?\s*(.+?)(?:\n|$)", text)
    if loc:
        location = loc.group(1).strip().strip('*')
        location = re.sub(r'\[.*?\].*', '', location).strip()
        if location:
            result["location"] = location

    # Extract narration — try strict format first, then flexible
    narr = re.search(r"\[NARRATION\]\s*\n(.+?)(?=\n\s*\[CHOICES\])", text, re.DOTALL)
    if not narr:
        narr = re.search(r"\[NARRATION\]\s*:?\s*\n?(.+?)(?=\n\s*\[|\n\s*\d+\.)", text, re.DOTALL)
    if narr:
        result["narration"] = clean_narration(narr.group(1).strip())

    # Extract choices
    ch = re.search(r"\[CHOICES\]\s*:?\s*\n?(.+?)(?=\n\s*\[|$)", text, re.DOTALL)
    if ch:
        choices = re.findall(r"\d+\.\s*(.+?)(?=\n\d+\.|\n\[|$)", ch.group(1).strip(), re.DOTALL)
        result["choices"] = [c.strip() for c in choices if c.strip()]
    else:
        # Try to find numbered choices anywhere in the text
        all_choices = re.findall(r"(?:^|\n)\s*\d+\.\s*(.+?)(?=\n\s*\d+\.|\n\s*\[|$)", text, re.DOTALL)
        if len(all_choices) >= 3:
            result["choices"] = [c.strip() for c in all_choices if c.strip()]

    # Extract stat changes
    st = re.search(r"\[STAT_CHANGES\]\s*:?\s*\n?(.+?)(?=\n\s*\[|$)", text, re.DOTALL)
    if st:
        try:
            json_match = re.search(r'\{[^}]+\}', st.group(1))
            if json_match:
                s = re.sub(r':\s*\+', ': ', json_match.group(0))
                result["stat_changes"] = json.loads(s)
        except (json.JSONDecodeError, ValueError):
            pass

    # Fallback: if narration is empty, extract text before any numbered choices
    if not result["narration"] and text.strip():
        # Strip all tags
        fallback = re.sub(r'\[.*?\]', '', text)
        # Remove everything from the first numbered choice onward
        fallback = re.split(r'\n\s*1\.', fallback)[0]
        # Strip JSON blocks
        fallback = re.sub(r'\{[^}]*\}', '', fallback)
        fallback = fallback.strip()
        if fallback:
            result["narration"] = fallback

    # Check if narration starts with an inline location
    if result["narration"]:
        narr = result["narration"]
        lines = narr.split('\n')
        first_line = lines[0].strip().strip('*')

        # Case 1: First line IS the location (short line with comma, no sentence structure)
        if (len(first_line) < 80 and ',' in first_line and
            not any(w in first_line.lower() for w in ['the ', 'and ', 'but ', 'was ', 'is ', 'are ', 'you ', 'he ', 'she ', 'they ']) and
            first_line[0].isupper()):
            result["location"] = first_line
            result["narration"] = '\n'.join(lines[1:]).strip()

        # Case 2: Location is inline at the START of first line (e.g. "Café Name, Area  Dima walked...")
        # Look for a location followed by a sentence-starting pattern
        else:
            # Sentence starters: any capitalized word followed by a lowercase word
            # This catches names ("Arthur sat"), pronouns ("He walked"), articles ("The room"), etc.
            sentence_starters = r'(?:[A-ZÀ-Ü][a-zà-ü]+ [a-z])'
            inline = re.match(
                r'^(.+?,\s*[A-ZÀ-Ü][A-Za-zÀ-ü\' ]+?)\s+(' + sentence_starters + r')',
                first_line
            )
            if inline:
                loc_part = inline.group(1).strip()
                if len(loc_part) < 80 and loc_part[0].isupper():
                    result["location"] = loc_part
                    # Remove the location from the narration text
                    rest = first_line[len(loc_part):].strip()
                    lines[0] = rest
                    result["narration"] = '\n'.join(lines).strip()

    # If location is still a generic city name, try to extract a specific place from narration
    if result["narration"] and result["location"].lower() in GENERIC_CITIES:
        specific = extract_location_from_narration(result["narration"])
        if specific:
            result["location"] = f"{specific}, {result['location']}"

    while len(result["choices"]) < 4:
        result["choices"].append("Consider your options carefully")
    result["choices"] = result["choices"][:4]

    return result


def clean_ending_text(text):
    """Remove all formatting artifacts from ending text."""
    # Remove [TAGS]
    text = re.sub(r'\[.*?\]', '', text)
    # Remove JSON blocks
    text = re.sub(r'\{[^}]*\}', '', text)
    # Remove ```json ... ``` code blocks
    text = re.sub(r'```\w*\s*.*?```', '', text, flags=re.DOTALL)
    # Remove **Stat Changes**, **Stats**, etc. headers and everything after
    text = re.sub(r'\*\*(?:Stat\s*Changes?|Stats?|Final\s*Stats?)\*\*.*', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Remove markdown bold markers but keep the text
    text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)
    # Remove orphaned asterisks
    text = re.sub(r'(?<!\w)\*{1,2}(?!\w)', '', text)
    # Clean up extra whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def parse_ending(text):
    """Parse ending response."""
    result = {"title": "The End", "text": "", "roads_not_taken": "", "stat_changes": {}}

    # Try to extract stat changes first (from JSON anywhere in text)
    json_match = re.search(r'\{[^}]*"(?:reputation|wealth|relationships|knowledge|health|morality)"[^}]*\}', text, re.IGNORECASE)
    if json_match:
        try:
            s = re.sub(r':\s*\+', ': ', json_match.group(0))
            result["stat_changes"] = json.loads(s)
        except (json.JSONDecodeError, ValueError):
            pass

    # Try to extract title — tag format first
    t = re.search(r"\[ENDING_TITLE\]\s*\n(.+?)(?:\n\n|\n\[)", text, re.DOTALL)
    if not t:
        t = re.search(r"\[ENDING_TITLE\]\s*:?\s*(.+?)(?:\n|$)", text)
    # Try markdown bold title (e.g. **A Life Reborn**)
    if not t:
        t = re.match(r'\s*\*\*(.+?)\*\*', text)
    if t:
        title = t.group(1).strip().strip('*')
        title = re.sub(r'\[.*?\].*', '', title).strip()
        if title and len(title) < 80:
            result["title"] = title

    # Try to extract ending text — tag format
    tx = re.search(r"\[ENDING_TEXT\]\s*:?\s*\n?(.+?)(?=\n\s*\[ROADS|$)", text, re.DOTALL)
    if tx:
        result["text"] = clean_ending_text(tx.group(1))

    # Try to extract roads not taken — tag format or markdown header
    rnt = re.search(r"(?:\[ROADS_NOT_TAKEN\]|\*\*Roads?\s*Not\s*Taken\*\*)\s*:?\s*\n?(.+?)(?=\n\s*\[STAT|\*\*Stat|$)", text, re.DOTALL | re.IGNORECASE)
    if rnt:
        result["roads_not_taken"] = clean_ending_text(rnt.group(1))

    # Fallback: if ending text is empty, use the cleaned raw text
    if not result["text"] and text.strip():
        fallback = clean_ending_text(text)
        if fallback:
            paragraphs = fallback.split('\n\n')
            # If first paragraph is short, it's likely the title
            if len(paragraphs) > 1 and len(paragraphs[0]) < 80:
                if result["title"] == "The End":
                    result["title"] = paragraphs[0].strip()
                result["text"] = '\n\n'.join(paragraphs[1:]).strip()
            else:
                result["text"] = fallback

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
    current_location = data.get("current_location", "")

    try:
        if action == "opening":
            seed = generate_story_seed()
            location_instruction = f"The story is set in {location}. Ground all details — streets, landmarks, weather, culture, atmosphere — in this real location." if location else ""
            messages = [{
                "role": "user",
                "content": (
                    f"Generate the opening scene for a new game. The player's name is "
                    f"{player_name} and their chosen background is: {background}.\n\n"
                    f"{location_instruction}\n\n"
                    f"UNIQUE STORY SEED (you MUST use these elements):\n"
                    f"- Opening hook: {seed['scenario']}\n"
                    f"- Narrative tone: {seed['tone']}\n"
                    f"- First NPC the player meets: {seed['npc']}\n"
                    f"- Time and atmosphere: {seed['time']}\n"
                    f"- DO NOT include these themes: {', '.join(seed['theme_avoid'])}\n\n"
                    f"Create an immersive opening using the story seed above. "
                    f"Set it in a specific, vivid real-world location "
                    f"within {location if location else 'a modern city'}. "
                    f"Make this opening COMPLETELY UNIQUE — no two games should start the same way."
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
            if scene_num >= 40:
                tension = "The story is deepening — introduce complications and raise the stakes."
            if scene_num >= 60:
                tension = "The story is building toward a climax — raise the stakes significantly."
            if scene_num >= 80:
                tension = "This scene should feel like things are reaching a turning point. Start tying threads together."
            if scene_num >= 90:
                tension = "The story is approaching its conclusion. Begin resolving major threads naturally while maintaining dramatic momentum."

            location_context = ""
            if current_location and location:
                location_context = (
                    f"The story began in {location}. The player is currently at: {current_location}. "
                    f"The story can move to new specific locations naturally — different neighborhoods, "
                    f"buildings, parks, streets, or even other cities if the story calls for it. "
                    f"Always provide a SPECIFIC location name in [LOCATION] (e.g. 'Riverside Park, Upper West Side' "
                    f"not just the city name)."
                )
            elif location:
                location_context = (
                    f"The story is set in {location}. Move the character to specific locations "
                    f"within and around this area. Always provide a SPECIFIC location name."
                )
            # Add random narrative spice to prevent repetitive patterns
            scene_spice = random.choice([
                "Introduce an unexpected twist or complication the player didn't see coming.",
                "Have an existing character reveal something surprising about themselves.",
                "Change the setting — move the action to a completely different location.",
                "Introduce a moment of levity or humor amidst the drama.",
                "Create a moral dilemma where no choice is clearly right.",
                "Have the consequences of a past choice catch up with the player.",
                "Introduce a new character who disrupts the current situation.",
                "Create a moment of danger, urgency, or time pressure.",
                "Show the player a side of a character they haven't seen before.",
                "Present an opportunity that seems too good to be true.",
                "Have two storylines or characters unexpectedly collide.",
                "Create a quiet, emotional moment — reflection, confession, or vulnerability.",
                "Introduce a mystery or question that demands investigation.",
                "Force the player to choose between two people or loyalties.",
                "Skip forward in time slightly — show consequences that have already unfolded.",
            ])

            messages = [{
                "role": "user",
                "content": (
                    f"Generate scene {scene_num} for player '{player_name}'.\n\n"
                    f"{location_context}\n\n"
                    f"Current stats: {stats_str}\n\n"
                    f"Recent history:\n{history_summary}\n\n"
                    f"Continue the story naturally from the last choice. {scene_spice} "
                    f"The narrative should feel like a natural progression with real consequences. "
                    f"DO NOT repeat patterns from previous scenes — no more people 'appearing from "
                    f"somewhere' or 'approaching the player'. Vary how scenes begin.\n\n{tension}"
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
