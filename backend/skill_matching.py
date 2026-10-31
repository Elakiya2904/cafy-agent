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


@lru_cache(maxsize=4096)
def _phrase_regex(phrase: str) -> "re.Pattern[str]":
    words = [w for w in re.split(r"[\s\-/]+", phrase.lower()) if w and w not in _STOP]
    parts = []
    for w in words:
        s = stem(w)
        # Only real word-form endings, so "java" never matches "javascript".
        parts.append(re.escape(s) + r"(?:s|es|ed|ies|ied|y|ing|ings|ion|ions|ation|ations|er|ers|al|ly|ment|ments)?" if len(w) > 3 else re.escape(w))
    return re.compile(r"(?<![a-z0-9])" + r"[\s\-/]+(?:(?:and|of|the|for)[\s]+)?".join(parts) + r"(?![a-z0-9])")


@lru_cache(maxsize=4096)
def _skill_stem_set(skill: str) -> frozenset:
    return frozenset(stems(skill))


def text_has_skill(skill: str, text: str, text_stems: "List[str] | None" = None, loose: bool = True) -> bool:
    """Phrase match with word-form tolerance, synonyms, or all words close together in any order."""
    if not skill or not text:
        return False
    lowered = text.lower()
    variants = [skill] + SYNONYMS.get(skill.lower(), [])
    for v in variants:
        if len(v) <= 3:
            if re.search(r"(?<![a-z0-9])" + re.escape(v.lower()) + r"(?![a-z0-9])", lowered):
                return True
        elif _phrase_regex(v).search(lowered):
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
