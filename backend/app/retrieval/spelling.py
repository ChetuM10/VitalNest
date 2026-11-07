"""Spelling correction against the vocabulary of the health pages.

The vocabulary is every word in the source pages we hold, with topic titles weighted higher so
medical terms win over incidental words. Rules (each has a test):
- a word that is already in the vocabulary is never changed;
- words under 5 letters are never changed;
- a candidate must be within a small edit distance (1 edit for words up to 5 letters, 2 for longer
  ones), where swapping two neighbouring letters counts as one edit ("ashtma" -> "asthma");
- a correction that needs two edits must keep the first letter ("causes" is never turned into "raises");
- plain inflections of known words ("causes" for "cause") are not treated as typos;
- if the closest candidates are about equally common the meaning is uncertain, so nothing is changed.

The chat service decides whether a correction is actually used: it keeps it only when it finds
clearly better sources, and it always tells the person what was changed.
"""
import re
from collections import Counter, defaultdict
from collections.abc import Iterable

_WORD = re.compile(r"[A-Za-z](?:[A-Za-z'’-]*[A-Za-z])?")
_SUFFIXES = ("s", "es", "ed", "ing", "ly", "er", "ers")
AMBIGUITY_RATIO = 3  # the best candidate must be this many times more common than the runner-up


def _key(word: str) -> str:
    """Spelling key: lower case, without apostrophes or hyphens ("Alzheimer's" and "alzheimers" match)."""
    return word.casefold().replace("'", "").replace("’", "").replace("-", "")


def _is_inflection(word: str, candidate: str) -> bool:
    shorter, longer = sorted((word, candidate), key=len)
    return longer.startswith(shorter) and longer[len(shorter):] in _SUFFIXES


def _mask(word: str) -> int:
    """Which letters occur in the word, as bits. Words within a few edits share almost all their letters."""
    bits = 0
    for char in word:
        if "a" <= char <= "z":
            bits |= 1 << (ord(char) - 97)
    return bits


def edit_distance(a: str, b: str, limit: int) -> int:
    """Edit distance where a swap of two neighbouring letters counts as one edit.

    Returns limit + 1 as soon as the distance is known to exceed `limit`.
    """
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    previous2: list[int] | None = None
    previous = list(range(len(b) + 1))
    for i in range(1, len(a) + 1):
        current = [i] + [0] * len(b)
        for j in range(1, len(b) + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            current[j] = min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost)
            if previous2 is not None and i > 1 and j > 1 and a[i - 1] == b[j - 2] and a[i - 2] == b[j - 1]:
                current[j] = min(current[j], previous2[j - 2] + 1)
        if min(current) > limit:
            return limit + 1
        previous2, previous = previous, current
    return previous[-1]


class SpellingCorrector:
    def __init__(
        self,
        texts: Iterable[str],
        priority_texts: Iterable[str] = (),
        min_length: int = 5,
        min_frequency: int = 1,
        priority_weight: int = 5,
    ) -> None:
        forms: dict[str, Counter] = defaultdict(Counter)
        for weight, source in ((1, texts), (priority_weight, priority_texts)):
            for text in source:
                for word in _WORD.findall(text):
                    forms[_key(word)][word.casefold().replace("’", "'")] += weight
        self._known = set(forms)
        self._display = {key: counter.most_common(1)[0][0] for key, counter in forms.items()}
        self._frequency = {key: sum(counter.values()) for key, counter in forms.items()}
        # Only reasonably common words are offered as corrections; every word is still "known".
        self._targets: dict[int, list[tuple[str, int]]] = defaultdict(list)
        for key, count in self._frequency.items():
            if count >= min_frequency:
                self._targets[len(key)].append((key, _mask(key)))
        self._min_length = min_length

    @staticmethod
    def _max_distance(length: int) -> int:
        return 1 if length <= 5 else 2

    def _best_match(self, key: str) -> str | None:
        limit = self._max_distance(len(key))
        mask = _mask(key)
        scored: list[tuple[int, int, str]] = []
        for length in range(len(key) - limit, len(key) + limit + 1):
            for candidate, candidate_mask in self._targets.get(length, ()):
                if bin(mask ^ candidate_mask).count("1") > 2 * limit:
                    continue
                distance = edit_distance(key, candidate, limit)
                if distance == 2 and key[0] != candidate[0]:
                    continue  # two edits including the first letter: too different to be a slip of the fingers
                if distance <= limit and not _is_inflection(key, candidate):
                    scored.append((distance, -self._frequency[candidate], candidate))
        if not scored:
            return None
        scored.sort()
        closest = [s for s in scored if s[0] == scored[0][0]]
        if len(closest) > 1 and -closest[0][1] < AMBIGUITY_RATIO * -closest[1][1]:
            return None  # two plausible words: the meaning is uncertain, so do not guess
        return closest[0][2]

    def _fix_token(self, token: str, changes: list[tuple[str, str]]) -> str:
        match = re.fullmatch(r"([^A-Za-z]*)(.*?)([^A-Za-z]*)", token, re.S)
        before, core, after = match.groups() if match else ("", token, "")
        if not core or not _WORD.fullmatch(core):
            return token
        key = _key(core)
        if len(key) < self._min_length or key in self._known:
            return token
        best = self._best_match(key)
        if best is None:
            return token
        fixed = self._display[best]
        if core[0].isupper():
            fixed = fixed[0].upper() + fixed[1:]
        changes.append((core, fixed))
        return f"{before}{fixed}{after}"

    def correct(self, text: str) -> tuple[str, list[tuple[str, str]]]:
        """Returns (corrected text, [(original word, corrected word), ...])."""
        changes: list[tuple[str, str]] = []
        corrected = "".join(self._fix_token(part, changes) for part in re.split(r"(\s+)", text))
        return corrected, changes
