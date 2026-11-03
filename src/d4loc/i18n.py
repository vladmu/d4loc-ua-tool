"""Interface language: Ukrainian or English (follows the system language; any other language gets English).

The key is the Ukrainian text: _("Огляд…") returns it as is for uk, and for other languages the translation from strings_en.py.
The language can be forced with the environment variable D4LOC_LANG=uk|en.
"""
import locale
import os

SUPPORTED = ("uk", "en")


def detect():
    forced = (os.environ.get("D4LOC_LANG") or "").lower()[:2]
    if forced in SUPPORTED:
        return forced
    try:
        import ctypes
        lid = ctypes.windll.kernel32.GetUserDefaultUILanguage()
        if lid & 0x3FF == 0x22:      # LANG_UKRAINIAN
            return "uk"
        return "en"
    except (AttributeError, OSError, ImportError):
        pass
    try:
        code = (locale.getlocale()[0] or os.environ.get("LANG", "")).lower()
    except ValueError:
        code = ""
    return "uk" if code.startswith(("uk", "ukr")) else "en"


LANG = detect()


def set_language(lang):
    global LANG
    LANG = lang if lang in SUPPORTED else "en"


def _(text):
    if LANG == "uk":
        return text
    from .strings_en import EN
    return EN.get(text, text)
