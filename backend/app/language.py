"""
Supported-language registry (Day 3 evening; extended Day 4 evening).

Per the project plan (section 2.2), language detection/response is
LLM-native rather than a separate NLU pipeline -- there is no separate
classifier here. What this module gives is the single source of truth
for which languages are demoed with real natural-language fluency today
vs. which of the 11-required-language list still fall back to English,
so personas.py, the frontend (via the new GET /languages endpoint in
main.py), the README, and the demo video all stay in sync as more
languages are added without editing prose in three places.

Day 4 evening (project plan section 3, Day 4): "Extend language coverage
to remaining priority languages (Telugu, Marathi, Bengali, or others) as
time allows -- English, Hindi, Tamil already covered from Day 3." This
module is the ONLY place that changes to pick those up -- personas.py's
_LANGUAGE_RULES already reads supported_language_names() dynamically, so
every persona's language rule text updates automatically.

Day 4 also adds LOCALE_BY_LANGUAGE below: the voice channel's
Speech-to-Text (browser Web Speech API, per the plan's "Web Speech API
first, for speed") needs a BCP-47 locale tag (e.g. "hi-IN"), not just the
two-letter code the LLM persona prompts use, so this is exposed alongside
each language rather than hardcoded again on the frontend.
"""

# English plus the languages demoed with real natural-language fluency:
# Hindi + Tamil from Day 3 evening ("add Hindi and Tamil as the first
# additional languages, verified against the 4 core use cases"), and
# Telugu, Marathi, Bengali added Day 4 evening per the roadmap's named
# "remaining priority languages" list.
SUPPORTED_LANGUAGES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "ta": "Tamil",
    "te": "Telugu",
    "mr": "Marathi",
    "bn": "Bengali",
}

# The brief's full 11-language requirement (section 1.2, 1.9) plus
# English. Only the ones in SUPPORTED_LANGUAGES above are demoed with
# real fluency as of Day 4; the rest still fall back to English honestly
# (see personas._LANGUAGE_RULES) -- gujarati/kannada/malayalam/punjabi/
# odia/assamese remain the honestly-scoped remainder per the plan's own
# framing (section 1.7), extendable the same way if more time allows.
ALL_TARGET_LANGUAGES: dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "ta": "Tamil",
    "te": "Telugu",
    "mr": "Marathi",
    "bn": "Bengali",
    "gu": "Gujarati",
    "kn": "Kannada",
    "ml": "Malayalam",
    "pa": "Punjabi",
    "or": "Odia",
    "as": "Assamese",
}

# BCP-47 locale tags for the browser SpeechRecognition API (Day 4
# morning voice channel). Only needed for languages we actually offer
# STT for on the frontend's language picker -- kept as a superset of
# ALL_TARGET_LANGUAGES so an STT-capable browser can still be offered
# recognition in a not-yet-"fluent" language; the persona will just say
# so honestly in its reply if it can't respond fluently in that language
# yet (see personas._LANGUAGE_RULES).
LOCALE_BY_LANGUAGE: dict[str, str] = {
    "en": "en-IN",
    "hi": "hi-IN",
    "ta": "ta-IN",
    "te": "te-IN",
    "mr": "mr-IN",
    "bn": "bn-IN",
    "gu": "gu-IN",
    "kn": "kn-IN",
    "ml": "ml-IN",
    "pa": "pa-IN",
    "or": "or-IN",
    "as": "as-IN",
}


def supported_language_names() -> list[str]:
    """Ordered, human-readable list for use in prompt text / README, e.g.
    ['English', 'Hindi', 'Tamil', 'Telugu', 'Marathi', 'Bengali']."""
    return list(SUPPORTED_LANGUAGES.values())


def language_catalog() -> list[dict]:
    """Full catalog for the GET /languages endpoint (main.py), consumed
    by the frontend's language picker (hooks/useLanguages.js) so the
    supported-vs-fallback distinction and STT locale tags live in this
    one backend module instead of being duplicated in frontend code.

    Each entry: {code, name, locale, fluent}. `fluent` mirrors whether
    the persona can hold a real conversation in that language today
    (SUPPORTED_LANGUAGES) vs. only being offered as an STT input option
    that currently falls back to an honest English reply.
    """
    return [
        {
            "code": code,
            "name": name,
            "locale": LOCALE_BY_LANGUAGE.get(code, "en-IN"),
            "fluent": code in SUPPORTED_LANGUAGES,
        }
        for code, name in ALL_TARGET_LANGUAGES.items()
    ]
