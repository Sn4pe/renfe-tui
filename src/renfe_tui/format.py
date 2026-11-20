import re
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from .i18n import lang, t

MADRID = ZoneInfo("Europe/Madrid")


def parse_day(text: str, today: date | None = None) -> str:
    today = today or datetime.now(MADRID).date()
    value = text.strip().lower()
    if value in ("", "hoy", "today"):
        return today.isoformat()
    if value in ("mañana", "manana", "tomorrow"):
        return (today + timedelta(days=1)).isoformat()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return value
    match = re.fullmatch(r"(\d{1,2})[/.-](\d{1,2})(?:[/.-](\d{2}|\d{4}))?", value)
    if not match:
        raise ValueError(text)
    day, month, year = int(match[1]), int(match[2]), match[3]
    year = int(year) + (2000 if len(year) == 2 else 0) if year else today.year
    picked = date(year, month, day)
    if not match[3] and picked < today:
        picked = date(year + 1, month, day)
    return picked.isoformat()


def parse_clock(text: str) -> str:
    value = text.strip()
    if not value:
        return ""
    match = re.fullmatch(r"(\d{1,2})(?::?(\d{2}))?", value)
    if not match or int(match[1]) > 23 or int(match[2] or 0) > 59:
        raise ValueError(text)
    return f"{int(match[1]):02d}:{match[2] or '00'}"


def clock(iso: str | None) -> str:
    if not iso:
        return "--:--"
    return datetime.fromisoformat(iso).strftime("%H:%M")


def duration(minutes: int | None) -> str:
    if minutes is None:
        return ""
    return f"{minutes // 60}h{minutes % 60:02d}"


def price(value: float | None) -> str:
    if value is None:
        return ""
    if lang() == "en":
        return f"€{value:,.2f}"
    return f"{value:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def delay(minutes: int | None) -> str:
    if minutes is None:
        return ""
    if minutes == 0:
        return t("on_time")
    return f"+{minutes} min" if minutes > 0 else f"{minutes} min"


def station(value: dict | None) -> str:
    if not value:
        return ""
    return value.get("name") or value.get("code") or ""


def error_text(error: dict | None) -> str:
    if not error:
        return t("unknown_error")
    kind = error.get("type")
    message = error.get("message") or ""
    prefixes = t("errors")
    prefix = prefixes.get(kind, prefixes[""])
    if kind == "usage":
        return translate(message) or f"{prefix}."
    return f"{prefix}. {translate(message)}" if message and kind != "missing_cli" else f"{prefix}."


def _selected(m: re.Match) -> str:
    method = t("methods").get(m[1], m[1])
    return (f"Pago elegido: {method} ({m[2]}). Revisa el total y las condiciones de Renfe y sigue en el navegador. "
            "Deja la ventana abierta hasta volver del proveedor de pago.")


def _stopped(m: re.Match) -> str:
    since = f" desde las {m[2]}" if m[2] else ""
    return f"Parece detenido en {m[1]}{since}."


TRANSLATIONS = [
    (r"no station matches '([^']*)'; try `renfe stations [^`]*`(?:\. Did you mean (.*?)\?)?",
     lambda m: f"No encuentro la estación «{m[1]}»." + (f" ¿Quizás {m[2]}?" if m[2] else "")),
    (r"'([^']*)' matches several stations: (.*?)\. Use a code or a longer name\.",
     r"«\1» coincide con varias estaciones: \2. Elige una de las sugerencias."),
    (r"--date \S+ is in the past", "Esa fecha ya ha pasado."),
    (r"--date \S+ is more than a year ahead; Renfe doesn't sell that far",
     "Renfe no vende billetes con más de un año de antelación."),
    (r"origin and destination are the same station", "Origen y destino son la misma estación."),
    (r"Renfe reported (\d+) trains but returned (\d+); some may be missing\.",
     r"Renfe indica \1 trenes pero solo ha enviado \2: puede que falte alguno."),
    (r"Renfe stopped answering fare requests; (\d+) train\(s\) have no fares\. Wait before trying again\.",
     r"Renfe ha dejado de dar precios y hay \1 trenes sin tarifa. Espera un poco antes de volver a buscar."),
    (r"(\d+) train\(s\) came back without fares\.", r"\1 trenes han llegado sin tarifa."),
    (r"Renfe's legacy shop \(.*?`shop\.url` opens the full list on Renfe's website\.",
     "La tienda antigua de Renfe no ha respondido, así que la lista puede estar incompleta y sin precios. "
     "En la web de Renfe está completa."),
    (r"No more trains today after (\d\d:\d\d); try --date tomorrow\.",
     r"Hoy no quedan trenes después de las \1. Prueba con mañana."),
    (r"Delays are unknown \(.*?\)\.", "No se han podido consultar los retrasos."),
    (r"(?:Renfe's live map lists no trains right now \(it is empty at night\)\. )?Train (\d+) isn't on Renfe's "
     r"live map.*?Its delay is unknown, not zero\.",
     r"El tren \1 no aparece ahora en circulación. Puede que aún no haya salido, que ya haya llegado o que no "
     r"sea de larga o media distancia."),
    (r"The train is probably stopped at (.+?)(?:, since about (\d\d:\d\d))?(?:, longer than a stop: its delay is "
     r"the last one Renfe recorded)?\.", _stopped),
    (r"Its expected arrival at (.+?) \((\d\d:\d\d)\) has already passed, so the delay is the last one Renfe "
     r"recorded and may be growing\.",
     r"Debía llegar a \1 a las \2 y aún no consta: el retraso puede ser mayor."),
    (r"TRAIN must be one train number such as 03081.*", "Escribe un único número de tren, por ejemplo 03081."),
    (r"Choose your fare, enter the passenger details and review extras in Chrome\.",
     "Elige la tarifa, rellena los datos de los viajeros y revisa los extras en el navegador."),
    (r"Selected (\S+) \((.+?)\)\. Review Renfe's total and terms, then continue in Chrome\..*", _selected),
    (r"Renfe confirmed the booking\..*", "Renfe ha confirmado la compra. Guarda tu billete y cierra el navegador."),
    (r"Renfe returned without a recognizable ticket confirmation\..*",
     "Renfe ha vuelto sin una confirmación clara. Revisa la página antes de volver a intentarlo."),
    (r"Checkout was interrupted\..*",
     "La compra se ha interrumpido. Si llegaste a pagar, mira la confirmación de Renfe antes de reintentar."),
    (r"Checkout needs installed Google Chrome and a graphical desktop\.",
     "Para comprar desde aquí hace falta Google Chrome instalado y un escritorio gráfico."),
]


def translate(text: str | None) -> str:
    if not text:
        return ""
    if lang() != "es":
        return text
    for pattern, replacement in TRANSLATIONS:
        text = re.sub(pattern, replacement, text, flags=re.S)
    return text


def full_date(d: date) -> str:
    return t("full_date", day=d.day, month=t("months")[d.month - 1], year=d.year)


def long_day_human(iso: str) -> str:
    d = date.fromisoformat(iso)
    return t("long_day", weekday=t("weekdays_long")[d.weekday()], day=d.day, month=t("months")[d.month - 1])


def delay_sentence(minutes: int | None) -> str:
    if minutes is None:
        return t("late_unknown")
    if minutes == 0:
        return t("is_on_time")
    if minutes > 0:
        return t("is_late", n=minutes)
    return t("is_early", n=-minutes)
