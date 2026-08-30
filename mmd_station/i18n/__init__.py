"""Blender-facing localization support for MMD Station."""

from __future__ import annotations

import re

import bpy

from .catalog import DYNAMIC_FRAGMENTS, ENGLISH


DOMAIN = "mmd_station"
CHINESE_LOCALES = frozenset({"zh_HANS", "zh_HANT", "zh_CN", "zh_TW"})
CJK = re.compile(r"[\u3400-\u9fff]")
FALLBACK_FRAGMENTS = tuple(
    sorted(
        (
            source
            for source, translated in ENGLISH.items()
            if len(source.strip()) >= 2
            and not source.startswith(";")
            and translated != source
            and not CJK.search(translated)
        ),
        key=lambda value: (-len(value), value),
    )
)


def is_chinese_locale(locale: str | None = None) -> bool:
    active_locale = locale or bpy.app.translations.locale
    return active_locale in CHINESE_LOCALES


def _locale_catalogs():
    contexts = (
        bpy.app.translations.contexts.default,
        bpy.app.translations.contexts.operator_default,
    )
    messages = {
        (context, source): translated
        for source, translated in ENGLISH.items()
        if translated and translated != source
        for context in contexts
    }
    return {
        locale: messages
        for locale in bpy.app.translations.locales
        if locale not in CHINESE_LOCALES
    }


def register():
    unregister()
    bpy.app.translations.register(DOMAIN, _locale_catalogs())


def unregister():
    try:
        bpy.app.translations.unregister(DOMAIN)
    except RuntimeError:
        pass


def iface(message):
    """Translate runtime-composed UI text using the active Blender language."""
    if not isinstance(message, str) or is_chinese_locale():
        return message
    exact = ENGLISH.get(message)
    if exact:
        return exact
    translated = message
    for fragment in DYNAMIC_FRAGMENTS:
        replacement = ENGLISH.get(fragment)
        if replacement and replacement != fragment and fragment in translated:
            translated = _replace_fragment(translated, fragment, replacement)
    if CJK.search(translated):
        for fragment in FALLBACK_FRAGMENTS:
            if fragment in translated:
                translated = _replace_fragment(
                    translated,
                    fragment,
                    ENGLISH[fragment],
                )
    return translated


def _replace_fragment(message, source, replacement):
    start = 0
    while True:
        index = message.find(source, start)
        if index < 0:
            return message
        end = index + len(source)
        value = replacement
        if (
            index
            and message[index - 1].isalnum()
            and value
            and value[0].isalnum()
        ):
            value = " " + value
        if (
            end < len(message)
            and message[end].isalnum()
            and value
            and value[-1].isalnum()
        ):
            value += " "
        message = message[:index] + value + message[end:]
        start = index + len(value)


def report(operator, levels, message):
    """Send an operator report after localizing its runtime message."""
    return operator.report(levels, iface(message))
