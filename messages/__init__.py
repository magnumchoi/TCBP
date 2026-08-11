"""
[ko]
i18n - 실행 중 출력 문구 카탈로그 (영어/한국어). ko.MESSAGES가 기준 언어이며,
import 시점에 en.MESSAGES와의 키 집합 차이를 warnings.warn으로 즉시 노출한다
(양방향 — 누락/orphan 모두 탐지).

[en]
i18n - runtime message catalog (English/Korean). ko.MESSAGES is the reference
language; at import time, any key-set difference against en.MESSAGES is
surfaced immediately via warnings.warn (both directions — missing and
orphan keys are both detected).
"""
import warnings

from . import en, ko

_CATALOGS: dict[str, dict[str, str]] = {"ko": ko.MESSAGES, "en": en.MESSAGES}

_missing_in_en = set(ko.MESSAGES) - set(en.MESSAGES)
if _missing_in_en:
    warnings.warn(f"messages/en.py is missing keys present in ko.py: {sorted(_missing_in_en)}")

_orphan_in_en = set(en.MESSAGES) - set(ko.MESSAGES)
if _orphan_in_en:
    warnings.warn(f"messages/en.py has keys not present in ko.py: {sorted(_orphan_in_en)}")


class Catalog:
    """[ko] 단일 언어의 메시지 카탈로그를 감싸는 얇은 래퍼. [en] A thin wrapper around a single language's message catalog."""

    def __init__(self, lang: str) -> None:
        self.lang = lang if lang in _CATALOGS else "ko"

    def t(self, key: str, **kwargs) -> str:
        template = _CATALOGS[self.lang].get(key) or _CATALOGS["ko"].get(key, key)
        return template.format(**kwargs) if kwargs else template


_catalog = Catalog("ko")  # [ko] 기본값. --lang 또는 config.toml의 [global].lang으로 재설정됨 / [en] default; overridden by --lang or config.toml's [global].lang


def _t(key: str, **kwargs) -> str:
    return _catalog.t(key, **kwargs)


def _set_lang(lang: str | None) -> None:
    global _catalog
    if lang in _CATALOGS:
        _catalog = Catalog(lang)
