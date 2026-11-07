"""Tolerant skill matching: plurals/word forms, word order and curated synonyms.

``text_has_skill("Patient Care", "…provide care to patients…")`` is True, so a résumé and a
posting that word the same skill differently still match.
"""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Dict, List

from .skill_catalog import SYNONYMS

_SUFFIXES = ("ations", "ation", "ings", "ing", "ies", "ied", "ers", "er", "ed", "es", "s", "al")
_STOP = {"and", "of", "the", "to", "for", "in", "a", "an", "with", "on"}
_TOKEN = re.compile(r"[a-z0-9+#]+")


@lru_cache(maxsize=65536)
def stem(word: str) -> str:
    w = word.lower()
    if len(w) <= 3:
        return w
    for suf in _SUFFIXES:
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            w = w[: -len(suf)]
            break
    if len(w) > 3 and w[-1] == w[-2] and w[-1] not in "lsz":
        w = w[:-1]  # planning -> plann -> plan
    if w.endswith("y") and len(w) > 4:
        w = w[:-1] + "i"
    return w


def stems(text: str) -> List[str]:
    return [stem(t) for t in _TOKEN.findall((text or "").lower()) if t not in _STOP]


@lru_cache(maxsize=8192)
def cached_stems(text: str) -> tuple:
    """``stems`` for texts re-read on every upload (job descriptions)."""
    return tuple(stems(text))


@lru_cache(maxsize=4096)
def _phrase_regex(phrase: str) -> "re.Pattern[str]":
    words = [w for w in re.split(r"[\s\-/]+", phrase.lower()) if w and w not in _STOP]
    parts = []
    for w in words:
        s = stem(w)
        # Only real word-form endings, so "java" never matches "javascript".
        parts.append(re.escape(s) + r"(?:s|es|ed|ies|ied|y|ing|ings|ion|ions|ation|ations|er|ers|al|ly|ment|ments)?" if len(w) > 3 else re.escape(w))
    if not words:
        return re.compile(r"(?<![a-z0-9])(?![a-z0-9])")
    # Start with the first word's literal text (so the engine can scan for it quickly), then
    # check the character before it - same as a leading (?<![a-z0-9]), much faster.
    first = stem(words[0]) if len(words[0]) > 3 else words[0]
    boundary = r"(?<![a-z0-9][\s\S]{%d})" % len(first)
    head = re.escape(first) + boundary + parts[0][len(re.escape(first)):]
    return re.compile(head + "".join(r"[\s\-/]+(?:(?:and|of|the|for)[\s]+)?" + p for p in parts[1:]) + r"(?![a-z0-9])")


@lru_cache(maxsize=4096)
def _phrase_literals(phrase: str) -> tuple:
    """Substrings every match of ``_phrase_regex(phrase)`` must contain — a cheap prefilter."""
    words = [w for w in re.split(r"[\s\-/]+", phrase.lower()) if w and w not in _STOP]
    return tuple(stem(w) if len(w) > 3 else w for w in words)


_ALNUM_RUN = re.compile(r"[a-z0-9]+")
_IS_ALNUM = re.compile(r"[a-z0-9]+\Z")
_WORD_FORM_SUFFIXES = ("", "s", "es", "ed", "ies", "ied", "y", "ing", "ings", "ion", "ions",
                       "ation", "ations", "er", "ers", "al", "ly", "ment", "ments")


@lru_cache(maxsize=4096)
def _single_word_forms(v: str) -> "frozenset | None":
    """Whole words that ``_phrase_regex(v)`` matches, when ``v`` is one alphanumeric word.

    The regex is bounded by non-alphanumerics on both sides, so for a single alphanumeric
    word it matches exactly when the text contains one of these words. ``None`` otherwise.
    """
    if len(v) <= 3:
        lv = v.lower()
        return frozenset({lv}) if _IS_ALNUM.match(lv) else None
    words = [w for w in re.split(r"[\s\-/]+", v.lower()) if w and w not in _STOP]
    if len(words) != 1 or not _IS_ALNUM.match(words[0]):
        return None
    w = words[0]
    if len(w) <= 3:
        return frozenset({w})
    s = stem(w)
    return frozenset(s + suf for suf in _WORD_FORM_SUFFIXES)


class TextIndex:
    """The words of a lowercased text and all their prefixes, for set-lookup matching.

    Each phrase-regex part starts at a word boundary, so an all-alphanumeric part can only
    match if it is a prefix of some word.
    """

    __slots__ = ("words", "prefixes")

    def __init__(self, lowered: str):
        self.words = frozenset(_ALNUM_RUN.findall(lowered))
        prefixes = set()
        for word in self.words:
            for i in range(1, len(word) + 1):
                prefixes.add(word[:i])
        self.prefixes = frozenset(prefixes)


def word_prefixes(lowered: str) -> TextIndex:
    return TextIndex(lowered)


def _part_possible(part: str, lowered: str, index: "TextIndex | None") -> bool:
    if index is not None and _IS_ALNUM.match(part):
        return part in index.prefixes
    return part in lowered


def _variant_in(v: str, lowered: str, index: "TextIndex | None" = None) -> bool:
    if index is not None:
        forms = _single_word_forms(v)
        if forms is not None:
            return not forms.isdisjoint(index.words)
    if len(v) <= 3:
        lv = v.lower()
        if not _part_possible(lv, lowered, index):
            return False
        return re.search(r"(?<![a-z0-9])" + re.escape(lv) + r"(?![a-z0-9])", lowered) is not None
    if not all(_part_possible(part, lowered, index) for part in _phrase_literals(v)):
        return False
    return _phrase_regex(v).search(lowered) is not None


class SkillIndex:
    """Skills keyed by the first word of each variant, to shortlist candidates for a text.

    A skill can only match if some variant's first part is a word prefix in the text, so
    one set intersection replaces checking every skill against every job description.
    """

    def __init__(self, skills: List[str]):
        self.skills = list(skills)
        self._by_first: Dict[str, set] = {}
        self._always: set = set()
        for skill in self.skills:
            for v in [skill] + SYNONYMS.get(skill.lower(), []):
                parts = (v.lower(),) if len(v) <= 3 else _phrase_literals(v)
                if parts and _IS_ALNUM.match(parts[0]):
                    self._by_first.setdefault(parts[0], set()).add(skill)
                else:
                    self._always.add(skill)

    def find(self, lowered: str) -> List[str]:
        index = TextIndex(lowered)
        candidates = set(self._always)
        for part in index.prefixes & self._by_first.keys():
            candidates |= self._by_first[part]
        return [s for s in self.skills if s in candidates and phrase_in_lowered(s, lowered, index)]


def phrase_in_lowered(skill: str, lowered: str, index: "TextIndex | None" = None) -> bool:
    """Strict (non-loose) ``text_has_skill`` for text the caller has already lowercased.

    Pass ``index=TextIndex(lowered)`` when checking many skills against one text.
    """
    if _variant_in(skill, lowered, index):
        return True
    return any(_variant_in(v, lowered, index) for v in SYNONYMS.get(skill.lower(), ()))


@lru_cache(maxsize=4096)
def _skill_stem_set(skill: str) -> frozenset:
    return frozenset(stems(skill))


def text_has_skill(skill: str, text: str, text_stems: "List[str] | None" = None, loose: bool = True) -> bool:
    """Phrase match with word-form tolerance, synonyms, or all words close together in any order."""
    if not skill or not text:
        return False
    if phrase_in_lowered(skill, text.lower()):
        return True

    if not loose:
        return False
    # Word order may differ ("care of patients" vs "patient care"): all stems within a short window.
    need = _skill_stem_set(skill)
    if len(need) < 2 or len(need) > 3:
        return False
    toks = text_stems if text_stems is not None else stems(text)
    window = len(need) + 3
    for i, t in enumerate(toks):
        if t in need and need <= set(toks[i : i + window]):
            return True
    return False


def expand_synonyms() -> Dict[str, str]:
    """Lowercased synonym phrase -> canonical skill."""
    out: Dict[str, str] = {}
    for canonical, alts in SYNONYMS.items():
        for a in alts:
            out[a.lower()] = canonical
    return out
