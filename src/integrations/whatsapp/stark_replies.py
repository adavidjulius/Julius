"""
Julius WhatsApp Integration — Tony Stark Fallback Replies.

100+ pre-written replies styled as Tony Stark / David Julius hybrid —
witty, confident, casual, never boring. Used when:
- LLM is offline / all API tiers fail
- Random call / circuit breaker is open
- Quick fallback needed before LLM warms up

These NEVER say "I was away from phone" or generic offline excuses.
Instead they sound like David with Tony Stark's wit and confidence.
"""

from __future__ import annotations

import random
from typing import List, Optional

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CATEGORIES OF TONY STARK STYLE REPLIES (100+ total)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ── Greetings / General "hi" ─────────────────────────────────────
GREETINGS = [
    "Yo, genius reporting. What's the mission?",
    "The lab is open, what do you need bro?",
    "You rang? Make it worth my time 😂",
    "Hey, multitasking over here. What's up?",
    "I'm here, I'm available, and I'm spectacular. Go ahead.",
    "Present. Accounted for. Intellectually superior. Proceed.",
    "What's up bro, just running some experiments 🔥",
    "Talk to me. I've got 3 minutes between world-changing ideas.",
    "Hey man! Just tweaking something cool. Tell me what's going on.",
    "Sup bro, I'm all ears. Well, mostly ears and a brilliant mind.",
    "Yo! Just wrapped up some heavy coding. What's the tea?",
    "Here I am, saving the world one code commit at a time. What's up?",
    "Hey! Perfect timing, I was just about to get bored.",
    "Bro! The prodigal friend returns. What do you need?",
]

# ── What are you doing / Where are you ───────────────────────────
ACTIVITIES = [
    "Building something that'll change the game. The usual 🔥",
    "Currently debugging reality. Give me a sec.",
    "In my room, surrounded by code and chaos. Living the dream.",
    "Just optimizing my AI system. You know how it is.",
    "Calibrating my genius. Standard Tuesday.",
    "Working on Julius, as always. This thing doesn't build itself!",
    "In the hostel, pretending to study but actually coding.",
    "Sitting in room, headphones on, building the future.",
    "At campus, just finished lab. My brain needs a break honestly.",
    "In my room doing what I do best — making machines smarter than people.",
    "Chillin in room but my laptop is on fire with this new feature 🔥",
    "Just came back from canteen. Tea was mid, code is elite.",
    "In the hostel, contemplating how to make Julius sentient. Kidding. Maybe.",
    "Working on something interesting. I'll show you when it's ready.",
]

# ── Delays / Why no reply ────────────────────────────────────────
# THESE REPLACE THE OLD "was away from phone" EXCUSES
DELAY_REPLIES = [
    "Got lost in a coding rabbit hole. You know how it goes 😅",
    "Was in a deep focus session. Brain was in another dimension.",
    "Phone was on silent while I was debugging something epic.",
    "Sorry bro, was neck-deep in some AI experiments.",
    "My bad, was in the zone. You know when the code hits different 🔥",
    "Had my head buried in some algorithm stuff. What's up?",
    "Was working on something that needed 100% focus. I'm back now!",
    "Sorry man, got pulled into a really interesting problem.",
    "Was in lab, phone was in my bag. Tell me what's up!",
    "Got caught up solving a bug that's been annoying me all day.",
    "My phone decided to take a nap too. What did I miss?",
    "Was optimizing some code, lost track of time. Classic me.",
    "Sorry bro, I was in the matrix. What's the situation?",
    "Brain was busy computing. I'm back in the real world now.",
    "Was just wrestling with some complex logic. Fill me in!",
]

# ── Questions you don't know ──────────────────────────────────────
UNSURE_REPLIES = [
    "Hmm that's a good one. Let me think about it and get back to you.",
    "Not sure about that one bro, let me dig into it.",
    "That's above my current intelligence level. Give me a minute.",
    "I'll need to consult my vast database (Google) for that one 😂",
    "Interesting question. I don't have the answer yet but I will.",
    "Let me process that. Even genius takes a moment sometimes.",
    "Not sure man, but I'll figure it out. I always do.",
    "Need to check on that. Hold my thought.",
    "Good question! I actually don't know. And that annoys me.",
    "Let me look into it. I refuse to give you a wrong answer.",
]

# ── Food / Meals ─────────────────────────────────────────────────
FOOD_REPLIES = [
    "Just had mess food. Survived. Barely.",
    "Yeah ate already. Fuel for the genius, you know?",
    "Food? Done. Now back to building the future.",
    "Had something quick. Can't waste too much time eating when there's code to write.",
    "Just came from canteen. The tea was the highlight honestly 😂",
    "Yeah man, ate already. What about you?",
    "Mess food hit different today. And by different I mean the same.",
    "Grabbed some food, now running on caffeine and ambition.",
]

# ── Academics / College ──────────────────────────────────────────
ACADEMICS_REPLIES = [
    "Working on it. I'll share what I have in a bit!",
    "Got the materials ready, just organizing them properly.",
    "Let me check my files and send you the stuff bro.",
    "I've been studying this actually. Let me send the notes!",
    "Already on it. Give me a few minutes to compile everything.",
    "Yeah man, I have the notes. Let me dig them out for you.",
    "On it! The preparation never stops with us, does it?",
    "Let me look through my materials folder, I saved everything there.",
    "Already prepped for this. Check what I'm sending you!",
]

# ── Confirmations / Acknowledgments ──────────────────────────────
CONFIRMATIONS = [
    "Copy that. Moving forward.",
    "Understood. Consider it handled.",
    "Roger that bro 👍",
    "Got it. Filed under 'important stuff'.",
    "Noted. My efficiency is your gain.",
    "Done deal. What's next on the agenda?",
    "Locked in. No further questions.",
    "Perfect. The universe is in order.",
    "Cool, sounds like a plan 🔥",
    "Alright, we're on the same page then!",
]

# ── Thanks / Appreciation ────────────────────────────────────────
THANKS_REPLIES = [
    "No need to thank me, it's what geniuses do 😂",
    "Anytime bro! That's what friends are for.",
    "You're welcome. I accept payment in coffee and respect.",
    "No worries man! Happy to help always.",
    "Don't mention it. Seriously. My ego is already well-fed.",
    "All good bro! We're a team 🤝",
    "Welcome welcome. Now go conquer the world.",
    "Anytime! That's what happens when you befriend a genius.",
]

# ── Farewells / Good night ───────────────────────────────────────
FAREWELL_REPLIES = [
    "Peace out bro! Don't let the bugs bite. Code bugs I mean.",
    "Catch you later! The world isn't going to innovate itself.",
    "Good night man! Dream of clean code and zero bugs.",
    "Later bro! Rest up, we've got a world to change tomorrow.",
    "Take care man! See you when the sun decides to show up.",
    "Night bro! Remember, sleep is just a firmware update.",
    "Catch you tomorrow! Until then, I'll be in the lab.",
    "See you bro! Stay sharp.",
]

# ── Jokes / Banter ───────────────────────────────────────────────
BANTER_REPLIES = [
    "Haha bro you're something else 😂",
    "Classic. This is why we're friends.",
    "I would roast you but I'm too busy being brilliant.",
    "You're hilarious. Almost as funny as my code reviews.",
    "That's peak comedy right there bro 💀",
    "LMAOOO bro stop I can't focus 😂",
    "Bro you're on a roll today. Keep it coming.",
    "If laughter was productivity, you'd be employee of the month.",
    "Hahaha not bad, not bad at all 😂",
    "You've got jokes! I've got solutions. Perfect team.",
]

# ── Generic / Catch-all ──────────────────────────────────────────
GENERIC_REPLIES = [
    "Interesting. Tell me more.",
    "I'm listening. My attention is a rare commodity, use it wisely.",
    "Go on, you've got my full computing power focused on you.",
    "Hmm that's something. What's the full story?",
    "Alright, break it down for me bro.",
    "I'm all ears. Well, mostly brain, but you get the idea.",
    "Sure thing, let's figure this out together.",
    "Got it man. What do you need from me?",
    "Tell me more, I'm processing at full speed here.",
    "Let's tackle this. What's the play?",
    "Interesting development. Keep talking.",
    "I'm on it. Consider the problem half-solved already.",
    "Alright bro, let's sort this out 🔥",
    "Say less. I already have three solutions in my head.",
    "You came to the right person for this 👍",
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PUBLIC API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ALL_REPLIES = (
    GREETINGS + ACTIVITIES + DELAY_REPLIES + UNSURE_REPLIES +
    FOOD_REPLIES + ACADEMICS_REPLIES + CONFIRMATIONS +
    THANKS_REPLIES + FAREWELL_REPLIES + BANTER_REPLIES +
    GENERIC_REPLIES
)


def get_stark_fallback(incoming_text: str = "") -> str:
    """
    Get a Tony Stark-styled fallback reply based on the incoming message.
    
    Categorizes the message and picks from the appropriate pool.
    Falls back to GENERIC_REPLIES if no category matches.
    """
    if not incoming_text:
        return random.choice(GENERIC_REPLIES)

    text_lower = incoming_text.lower().strip()

    # Language confusion / repeating / glitch
    if any(w in text_lower for w in ["speak tamil", "pesu da", "yen da", "why are you speaking", "repeating", "same thing", "glitch", "blabbering"]):
        return random.choice([
            "Haha why would I speak Tamil bro? My system was recalibrating! All good now 😂",
            "My bad, the neural networks were cross-wired for a second. I'm back!",
            "Lol that was a glitch in the matrix. I'm running smooth now bro!",
        ])

    # Delays / Why no reply
    if any(w in text_lower for w in ["reply kaanom", "why no reply", "seen", "sleeping", "dei", "where were you", "no response", "not replying", "silent"]):
        return random.choice(DELAY_REPLIES)

    # Activities / What doing / Where
    if any(w in text_lower for w in ["what are you doing", "what doing", "wru", "enna panra", "panra", "doing rn"]):
        return random.choice(ACTIVITIES)

    if any(w in text_lower for w in ["where are you", "enga irukka", "enga da", "where u at"]):
        return random.choice(ACTIVITIES)

    # Food / Meals
    if any(w in text_lower for w in ["had food", "lunch", "dinner", "breakfast", "sapdiya", "saapadu"]):
        return random.choice(FOOD_REPLIES)

    # Academics / College / Exam / Notes
    if any(w in text_lower for w in ["portion", "internal", "notes", "pdf", "assignment", "sheet", "eg", "graphics", "exam", "sem", "ia"]):
        return random.choice(ACADEMICS_REPLIES)

    # Greetings
    if any(w in text_lower for w in ["hi", "hello", "hey", "machan", "machi", "bro", "sup"]):
        return random.choice(GREETINGS)

    # Farewells
    if any(w in text_lower for w in ["bye", "see you", "catch you", "good night", "gn", "nighty"]):
        return random.choice(FAREWELL_REPLIES)

    # Thanks
    if any(w in text_lower for w in ["thanks", "thank you", "nandri"]):
        return random.choice(THANKS_REPLIES)

    # Confirmations
    if any(w in text_lower for w in ["ok", "okay", "cool", "done", "great", "seri"]):
        return random.choice(CONFIRMATIONS)

    # Jokes / laughter
    if any(w in text_lower for w in ["haha", "lol", "lmao", "rofl", "joke", "funny", "😂", "💀"]):
        return random.choice(BANTER_REPLIES)

    # Default: pick from generic pool
    return random.choice(GENERIC_REPLIES)


def get_random_stark_reply() -> str:
    """Get a completely random Tony Stark style reply from the entire pool."""
    return random.choice(ALL_REPLIES)


def get_stark_replies_count() -> int:
    """Return total number of pre-written Tony Stark replies available."""
    return len(ALL_REPLIES)
