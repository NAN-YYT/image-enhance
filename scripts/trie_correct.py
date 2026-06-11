#!/usr/bin/env python3
"""
Trie-based OCR correction engine.
- Stores short domain terms in a Trie for fast prefix matching
- Segments OCR output and matches against the Trie
- Auto-learns new corrections from user feedback
- Persists dictionary to JSON for incremental updates
"""

import json
import os
import sys
from pathlib import Path

DICT_PATH = os.path.join(os.path.dirname(__file__), "correction_dict.json")


class TrieNode:
    __slots__ = ("children", "correction", "frequency")

    def __init__(self):
        self.children = {}
        self.correction = None
        self.frequency = 0


class CorrectionTrie:
    def __init__(self):
        self.root = TrieNode()

    def insert(self, wrong: str, correct: str, frequency: int = 1):
        node = self.root
        for ch in wrong:
            if ch not in node.children:
                node.children[ch] = TrieNode()
            node = node.children[ch]
        node.correction = correct
        node.frequency = frequency

    def search(self, text: str, start: int):
        """
        From position `start` in text, find the longest matching wrong pattern.
        Returns (matched_length, correction) or (0, None) if no match.
        """
        node = self.root
        last_match = (0, None)

        for i in range(start, len(text)):
            ch = text[i]
            if ch not in node.children:
                break
            node = node.children[ch]
            if node.correction is not None:
                last_match = (i - start + 1, node.correction)

        return last_match

    def correct_text(self, text: str) -> str:
        """
        Scan text left-to-right, greedily replacing longest Trie matches.
        """
        result = []
        i = 0
        while i < len(text):
            match_len, correction = self.search(text, i)
            if match_len > 0:
                result.append(correction)
                i += match_len
            else:
                result.append(text[i])
                i += 1
        return "".join(result)

    def to_dict(self) -> dict:
        """Export all entries as {wrong: {correct, frequency}}."""
        entries = {}
        self._collect(self.root, [], entries)
        return entries

    def _collect(self, node, path, entries):
        if node.correction is not None:
            key = "".join(path)
            entries[key] = {"correct": node.correction, "freq": node.frequency}
        for ch, child in node.children.items():
            path.append(ch)
            self._collect(child, path, entries)
            path.pop()

    @classmethod
    def from_dict(cls, data: dict) -> "CorrectionTrie":
        trie = cls()
        for wrong, info in data.items():
            if isinstance(info, str):
                trie.insert(wrong, info)
            else:
                trie.insert(wrong, info["correct"], info.get("freq", 1))
        return trie


def load_dictionary() -> dict:
    """Load persistent dictionary from JSON."""
    if os.path.exists(DICT_PATH):
        with open(DICT_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_dictionary(data: dict):
    """Save dictionary to JSON."""
    with open(DICT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def build_trie() -> CorrectionTrie:
    """Build Trie from persisted dictionary."""
    data = load_dictionary()
    return CorrectionTrie.from_dict(data)


def learn(wrong: str, correct: str):
    """Add a new correction pair and persist."""
    data = load_dictionary()
    if wrong in data:
        if isinstance(data[wrong], str):
            data[wrong] = {"correct": correct, "freq": 2}
        else:
            data[wrong]["correct"] = correct
            data[wrong]["freq"] = data[wrong].get("freq", 1) + 1
    else:
        data[wrong] = {"correct": correct, "freq": 1}
    save_dictionary(data)
    print(f"Learned: '{wrong}' → '{correct}'")


def correct_file(results_path: str):
    """Load OCR results JSON and apply Trie-based correction."""
    trie = build_trie()

    with open(results_path, "r", encoding="utf-8") as f:
        results = json.load(f)

    print("=" * 60)
    print("TRIE-CORRECTED OCR OUTPUT")
    print("=" * 60)

    for region in results:
        print(f"\n--- Region {region['region']} ---")
        for line in region["content"]:
            original = line["text"]
            corrected = trie.correct_text(original)
            marker = "✓" if line["confidence"] > 0.7 else "~" if line["confidence"] >= 0.4 else "?"
            if corrected != original:
                print(f"  {marker} {corrected}")
                print(f"    [raw: {original}]")
            else:
                print(f"  {marker} {corrected}")


def init_from_legacy():
    """Import corrections from the old context_correct.py CORRECTIONS dict."""
    legacy_path = os.path.join(os.path.dirname(__file__), "context_correct.py")
    if not os.path.exists(legacy_path):
        print("No legacy context_correct.py found.")
        return

    import importlib.util
    spec = importlib.util.spec_from_file_location("legacy", legacy_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    if hasattr(mod, "CORRECTIONS"):
        data = {}
        for wrong, correct in mod.CORRECTIONS.items():
            data[wrong] = {"correct": correct, "freq": 1}
        save_dictionary(data)
        print(f"Imported {len(data)} entries from legacy CORRECTIONS dict.")
    else:
        print("No CORRECTIONS dict found in legacy script.")


def print_usage():
    print("""Usage:
  python3 trie_correct.py correct <results.json>   # Apply corrections to OCR results
  python3 trie_correct.py learn <wrong> <correct>  # Add new correction pair
  python3 trie_correct.py import                   # Import from legacy context_correct.py
  python3 trie_correct.py stats                    # Show dictionary statistics
  python3 trie_correct.py search <text>            # Test correction on arbitrary text
""")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "correct" and len(sys.argv) >= 3:
        correct_file(sys.argv[2])
    elif cmd == "learn" and len(sys.argv) >= 4:
        learn(sys.argv[2], sys.argv[3])
    elif cmd == "import":
        init_from_legacy()
    elif cmd == "stats":
        data = load_dictionary()
        print(f"Dictionary entries: {len(data)}")
        by_freq = sorted(data.items(), key=lambda x: x[1].get("freq", 1) if isinstance(x[1], dict) else 1, reverse=True)
        print("Top 10 most used:")
        for wrong, info in by_freq[:10]:
            correct = info["correct"] if isinstance(info, dict) else info
            freq = info.get("freq", 1) if isinstance(info, dict) else 1
            print(f"  '{wrong}' → '{correct}' (used {freq}x)")
    elif cmd == "search" and len(sys.argv) >= 3:
        trie = build_trie()
        text = " ".join(sys.argv[2:])
        corrected = trie.correct_text(text)
        print(f"Input:     {text}")
        print(f"Corrected: {corrected}")
    else:
        print_usage()
