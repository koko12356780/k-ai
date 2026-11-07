"""Cloud voice identifiers, independent of the network and chat engines."""
ENGLISH_MODEL = "canopylabs/orpheus-v1-english"
ARABIC_MODEL = "canopylabs/orpheus-arabic-saudi"
CLOUD_VOICES = tuple(
    (f"Groq · {name.title()} · {language}", f"groq|{model}|{name}")
    for model, language, names in (
        (ENGLISH_MODEL, "English", ("troy", "autumn", "diana", "hannah", "austin", "daniel")),
        (ARABIC_MODEL, "Arabic Saudi", ("abdullah", "fahad", "sultan", "lulwa", "noura", "aisha")))
    for name in names)
DEFAULT_CLOUD_VOICE = CLOUD_VOICES[0][1]
