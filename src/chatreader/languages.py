"""Everything that differs per language, in one place. Add a language by adding one entry."""
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Language:
    code: str
    name: str  # the language's own name, shown in the settings page
    kokoro: str  # Kokoro/espeak language code
    voice_prefixes: str  # first letters of this language's Kokoro voice ids
    default_voice: str
    says: str  # "<user> says: <text>"
    laugh: str  # what LUL / kkkk is read as
    events: dict[str, Callable[[str], str]]  # event kind -> phrase from its detail
    beta: bool = False  # wording not yet proofread by a native speaker


def _plural(one: str, many: str) -> Callable[[str], str]:
    return lambda n: one if n == "1" else many


_PT = {
    "bits": lambda n: f"doou {n} bit" + ("" if n == "1" else "s"),
    "subs": lambda n: "se inscreveu" if not n else f"renovou a inscrição, {n} meses",
    "gifts": lambda n: f"deu {n} " + ("inscrição" if n == "1" else "inscrições"),
    "raids": lambda n: f"fez uma raid com {n} pessoas",
    "superchat": lambda n: f"enviou {n}",
    "members": lambda n: "virou membro",
}
_EN = {
    "bits": lambda n: f"cheered {n} bit" + ("" if n == "1" else "s"),
    "subs": lambda n: "subscribed" if not n else f"resubscribed for {n} months",
    "gifts": lambda n: f"gifted {n} sub" + ("" if n == "1" else "s"),
    "raids": lambda n: f"is raiding with {n} viewers",
    "superchat": lambda n: f"sent {n}",
    "members": lambda n: "became a member",
}
_ES = {
    "bits": lambda n: f"donó {n} bit" + ("" if n == "1" else "s"),
    "subs": lambda n: "se suscribió" if not n else f"renovó su suscripción, {n} meses",
    "gifts": lambda n: f"regaló {n} " + _plural("suscripción", "suscripciones")(n),
    "raids": lambda n: f"hizo una raid con {n} personas",
    "superchat": lambda n: f"envió {n}",
    "members": lambda n: "se hizo miembro",
}
_FR = {
    "bits": lambda n: f"a envoyé {n} bit" + ("" if n == "1" else "s"),
    "subs": lambda n: "s'est abonné" if not n else f"s'est réabonné, {n} mois",
    "gifts": lambda n: f"a offert {n} " + _plural("abonnement", "abonnements")(n),
    "raids": lambda n: f"arrive en raid avec {n} personnes",
    "superchat": lambda n: f"a envoyé {n}",
    "members": lambda n: "est devenu membre",
}
_IT = {
    "bits": lambda n: f"ha donato {n} bit",
    "subs": lambda n: "si è iscritto" if not n else f"ha rinnovato l'iscrizione, {n} mesi",
    "gifts": lambda n: f"ha regalato {n} " + _plural("iscrizione", "iscrizioni")(n),
    "raids": lambda n: f"fa un raid con {n} persone",
    "superchat": lambda n: f"ha inviato {n}",
    "members": lambda n: "è diventato membro",
}

LANGUAGES: dict[str, Language] = {
    lang.code: lang
    for lang in (
        Language("pt", "Português", "pt-br", "p", "pf_dora", "disse", "há há", _PT),
        Language("en", "English", "en-us", "ab", "af_heart", "says", "ha ha", _EN),
        Language("es", "Español", "es", "e", "ef_dora", "dijo", "ja ja", _ES, beta=True),
        Language("fr", "Français", "fr-fr", "f", "ff_siwis", "dit", "ha ha", _FR, beta=True),
        Language("it", "Italiano", "it", "i", "if_sara", "ha detto", "ah ah", _IT, beta=True),
    )
}
DEFAULT_LANGUAGES = ["pt", "en"]
