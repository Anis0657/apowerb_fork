"""Un avertissement de console ne doit pas faire l'empreinte d'un signalement.

Vécu le 14/09/2026 : deux signalements sans rapport — un PDF qui ne
s'indexe pas (bloquant) et un aperçu des anciennes conversations jugé
peu pratique (mineur) — ont reçu la même empreinte. Aucun appel en échec,
même route `/chat`, et pour signature d'erreur la dernière ligne de
console : un avertissement de Recharts sur la taille d'un graphique,
émis sur toutes les pages. Le second a été rangé comme occurrence du
premier, et versé en commentaire sous l'issue du PDF.

Un avertissement ne dit pas ce qui a cassé ; seule une erreur le dit.
"""

from apowerb.bug_reports.service import _error_signature

RECHARTS = "The width(-1) and height(-1) of chart should be greater than 0"


def test_a_failing_call_names_the_defect_first():
    signature = _error_signature(
        {"error": "HTTP 500"},
        [{"level": "error", "message": "TypeError: x is undefined"}],
        "rien ne marche",
    )

    assert signature == "HTTP 500"


def test_the_last_console_error_is_used_when_no_call_failed():
    signature = _error_signature(
        {},
        [
            {"level": "error", "message": "TypeError: x is undefined"},
            {"level": "warn", "message": RECHARTS},
        ],
        "rien ne marche",
    )

    assert signature == "TypeError: x is undefined"


def test_warnings_alone_do_not_become_the_signature():
    console = [{"level": "warn", "message": RECHARTS}] * 15

    pdf = _error_signature({}, console, "j'ai essayé de charger un PDF")
    apercu = _error_signature({}, console, "un aperçu des anciens chats")

    assert pdf != apercu
    assert RECHARTS not in (pdf or "")
