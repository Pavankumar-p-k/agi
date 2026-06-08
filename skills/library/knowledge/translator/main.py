from skills.utils import success_response, error_response, fetch_json

LANG_CODES = {
    "en": "English", "es": "Spanish", "fr": "French", "de": "German", "it": "Italian",
    "pt": "Portuguese", "ru": "Russian", "zh": "Chinese", "ja": "Japanese", "ko": "Korean",
    "ar": "Arabic", "hi": "Hindi", "bn": "Bengali", "pa": "Punjabi", "te": "Telugu",
    "tr": "Turkish", "nl": "Dutch", "pl": "Polish", "sv": "Swedish", "da": "Danish",
    "fi": "Finnish", "no": "Norwegian", "cs": "Czech", "hu": "Hungarian", "ro": "Romanian",
    "th": "Thai", "vi": "Vietnamese", "el": "Greek", "he": "Hebrew", "id": "Indonesian",
    "ms": "Malay", "ta": "Tamil", "ur": "Urdu", "fa": "Persian", "uk": "Ukrainian",
}

COMMON_PHRASES = {
    ("hello", "es"): "hola", ("hello", "fr"): "bonjour", ("hello", "de"): "hallo",
    ("hello", "it"): "ciao", ("hello", "pt"): "olá", ("hello", "ru"): "здравствуйте",
    ("thanks", "es"): "gracias", ("thanks", "fr"): "merci", ("thanks", "de"): "danke",
    ("thanks", "it"): "grazie", ("thanks", "pt"): "obrigado", ("thanks", "ru"): "спасибо",
    ("yes", "es"): "sí", ("yes", "fr"): "oui", ("yes", "de"): "ja", ("yes", "it"): "sì",
    ("no", "es"): "no", ("no", "fr"): "non", ("no", "de"): "nein", ("no", "it"): "no",
    ("goodbye", "es"): "adiós", ("goodbye", "fr"): "au revoir", ("goodbye", "de"): "auf Wiedersehen",
    ("please", "es"): "por favor", ("please", "fr"): "s'il vous plaît", ("please", "de"): "bitte",
    ("sorry", "es"): "lo siento", ("sorry", "fr"): "désolé", ("sorry", "de"): "Entschuldigung",
    ("help", "es"): "ayuda", ("help", "fr"): "aide", ("help", "de"): "Hilfe",
    ("water", "es"): "agua", ("water", "fr"): "eau", ("water", "de"): "Wasser",
    ("food", "es"): "comida", ("food", "fr"): "nourriture", ("food", "de"): "Essen",
    ("friend", "es"): "amigo", ("friend", "fr"): "ami", ("friend", "de"): "Freund",
    ("love", "es"): "amor", ("love", "fr"): "amour", ("love", "de"): "Liebe",
    ("good", "es"): "bueno", ("good", "fr"): "bon", ("good", "de"): "gut",
    ("bad", "es"): "malo", ("bad", "fr"): "mauvais", ("bad", "de"): "schlecht",
    ("big", "es"): "grande", ("big", "fr"): "grand", ("big", "de"): "groß",
    ("small", "es"): "pequeño", ("small", "fr"): "petit", ("small", "de"): "klein",
    ("today", "es"): "hoy", ("today", "fr"): "aujourd'hui", ("today", "de"): "heute",
    ("tomorrow", "es"): "mañana", ("tomorrow", "fr"): "demain", ("tomorrow", "de"): "morgen",
    ("how are you", "es"): "cómo estás", ("how are you", "fr"): "comment allez-vous",
    ("how are you", "de"): "wie geht es dir", ("how are you", "it"): "come stai",
}

def detect_language(text: str) -> str:
    text_lower = text.strip().lower()
    for (phrase, lang), _ in COMMON_PHRASES:
        if phrase == text_lower:
            return "en"
    return "en"

def lookup_translate(text: str, target: str) -> str:
    text_lower = text.strip().lower()
    result = COMMON_PHRASES.get((text_lower, target))
    if result:
        return result
    if target == "en":
        for (phrase, lang), translation in COMMON_PHRASES.items():
            if translation.lower() == text_lower:
                return phrase
    return None

async def translator(params: dict) -> dict:
    text = params.get("text", "").strip()
    source = params.get("source", "auto")
    target = params.get("target", "en")

    if not text:
        return error_response("Please provide 'text' to translate.")

    if target not in LANG_CODES:
        return error_response(f"Unsupported target language '{target}'.")

    detected = detect_language(text) if source == "auto" else source

    simple = lookup_translate(text, target)
    if simple:
        return success_response({
            "translated_text": simple,
            "detected_source": detected,
            "target": target
        })

    api_url = f"https://lingva.ml/api/v1/{source}/{target}/{text}"
    data = await fetch_json(api_url)
    if data and "translation" in data:
        return success_response({
            "translated_text": data["translation"],
            "detected_source": data.get("source-language", detected),
            "target": target
        })

    return success_response({
        "translated_text": text,
        "detected_source": detected,
        "target": target,
        "note": "Translation API unavailable; returned original text."
    })

class Skill:
    def __init__(self, manifest):
        self.manifest = manifest
    async def on_load(self):
        pass
