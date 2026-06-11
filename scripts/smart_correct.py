#!/usr/bin/env python3
"""
Smart OCR correction engine using character similarity (形近字).
Combines:
1. Trie-based exact pattern matching (fast, for known errors)
2. Character-level similarity lookup (for unknown errors)

Uses fourangle codes + stroke decomposition + component (部首) to find
visually similar characters — the primary source of OCR errors.
"""

import json
import os
import sys
from collections import defaultdict
from pathlib import Path

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
DICT_PATH = os.path.join(os.path.dirname(__file__), "correction_dict.json")
SIMILAR_CACHE_PATH = os.path.join(DATA_DIR, "similar_chars_cache.json")


class CharSimilarity:
    """Compute visual similarity between Chinese characters."""

    def __init__(self):
        self.fourangle = self._load(os.path.join(DATA_DIR, "char_fourangle.json"))
        self.stroke = self._load(os.path.join(DATA_DIR, "char_stroke.json"))
        self.component = self._load(os.path.join(DATA_DIR, "char_component.json"))
        self.struct = self._load(os.path.join(DATA_DIR, "char_struct.json"))
        self._similar_cache = self._load_cache()
        self._fourangle_index = self._build_fourangle_index()

    def _load(self, path):
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _load_cache(self):
        if os.path.exists(SIMILAR_CACHE_PATH):
            with open(SIMILAR_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}

    def _save_cache(self):
        with open(SIMILAR_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(self._similar_cache, f, ensure_ascii=False)

    def _build_fourangle_index(self):
        """Index chars by their first 3 digits of fourangle code for fast lookup."""
        index = defaultdict(list)
        for char, code in self.fourangle.items():
            if len(code) >= 3:
                index[code[:3]].append(char)
        return index

    def similarity(self, char1, char2):
        """Compute visual similarity score between two characters (0-1)."""
        scores = []

        # Fourangle similarity (shape encoding)
        f1 = self.fourangle.get(char1, "")
        f2 = self.fourangle.get(char2, "")
        if f1 and f2:
            same = sum(1 for a, b in zip(f1[:4], f2[:4]) if a == b)
            scores.append(same / 4 * 0.4)

        # Component (部首) similarity
        c1 = self.component.get(char1, "")
        c2 = self.component.get(char2, "")
        if c1 and c2 and c1 == c2:
            scores.append(0.25)
        else:
            scores.append(0)

        # Structure similarity
        s1 = self.struct.get(char1, "")
        s2 = self.struct.get(char2, "")
        if s1 and s2 and s1 == s2:
            scores.append(0.15)
        else:
            scores.append(0)

        # Stroke decomposition similarity
        st1 = self.stroke.get(char1, [])
        st2 = self.stroke.get(char2, [])
        if st1 and st2:
            common = len(set(st1) & set(st2))
            total = max(len(set(st1) | set(st2)), 1)
            scores.append(common / total * 0.2)

        return sum(scores) if scores else 0

    def find_similar(self, char, top_n=5, threshold=0.5):
        """Find top-N visually similar characters."""
        if char in self._similar_cache:
            return self._similar_cache[char][:top_n]

        candidates = []
        code = self.fourangle.get(char, "")
        if code and len(code) >= 3:
            # Only search chars with similar fourangle prefix
            search_chars = set()
            for prefix_len in [3, 2]:
                prefix = code[:prefix_len]
                search_chars.update(self._fourangle_index.get(prefix, []))
                if len(search_chars) > 200:
                    break

            for c in search_chars:
                if c == char:
                    continue
                score = self.similarity(char, c)
                if score >= threshold:
                    candidates.append((c, score))

        candidates.sort(key=lambda x: -x[1])
        result = candidates[:top_n]
        self._similar_cache[char] = result
        return result


class SmartCorrector:
    """
    Two-level correction:
    1. Trie exact match (known patterns)
    2. Character similarity + context (unknown errors)
    """

    def __init__(self):
        self.char_sim = CharSimilarity()
        self.known_corrections = self._load_dict()
        # Common Chinese words for context validation
        self.vocab = self._load_vocab()

    def _load_dict(self):
        if os.path.exists(DICT_PATH):
            with open(DICT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {k: v["correct"] if isinstance(v, dict) else v
                        for k, v in data.items()}
        return {}

    def _load_vocab(self):
        """Load Chinese vocabulary for context checking. Includes single words and bigrams."""
        vocab_path = os.path.join(DATA_DIR, "common_words.json")
        if os.path.exists(vocab_path):
            with open(vocab_path, "r", encoding="utf-8") as f:
                words = json.load(f)
                vocab = set(words)
                # Also add all 2-char substrings of longer words
                for w in words:
                    if len(w) >= 3:
                        for i in range(len(w) - 1):
                            vocab.add(w[i:i+2])
                return vocab
        return set()

    def correct_char(self, char, left_context="", right_context=""):
        """
        Try to correct a single character using similarity + context.
        ONLY replaces if the candidate forms a known word with context.
        Returns (corrected_char, confidence) or (char, 0) if no correction.
        """
        similar = self.char_sim.find_similar(char, top_n=8, threshold=0.4)
        if not similar:
            return char, 0

        best_char = char
        best_score = 0

        for candidate, sim_score in similar:
            context_score = 0
            # MUST form a known word with at least one side of context
            left_word = left_context + candidate if left_context else ""
            right_word = candidate + right_context if right_context else ""

            if left_word in self.vocab:
                context_score += 0.5
            if right_word in self.vocab:
                context_score += 0.5

            # Only accept if it forms a valid word (context_score > 0)
            if context_score == 0:
                continue

            total = sim_score * 0.3 + context_score * 0.7
            if total > best_score:
                best_score = total
                best_char = candidate

        return best_char, best_score

    def correct_text(self, text, confidence_threshold=0.5):
        """
        Correct text using both Trie patterns and char similarity.
        """
        # First pass: Trie exact match (fast, high confidence)
        result = self._trie_correct(text)

        # Second pass: char-level similarity ONLY where context validates
        if self.vocab:
            result = self._similarity_correct(result, confidence_threshold)

        return result

    def _trie_correct(self, text):
        """Apply known Trie corrections (longest match)."""
        # Sort by length descending for longest match
        sorted_patterns = sorted(self.known_corrections.keys(),
                                 key=len, reverse=True)
        result = text
        for pattern in sorted_patterns:
            if pattern in result:
                result = result.replace(pattern, self.known_corrections[pattern])
        return result

    def _similarity_correct(self, text, threshold):
        """Character-by-character similarity correction with context."""
        chars = list(text)
        corrected = []
        for i, ch in enumerate(chars):
            if not ('一' <= ch <= '鿿'):
                corrected.append(ch)
                continue
            left = chars[i-1] if i > 0 else ""
            right = chars[i+1] if i < len(chars)-1 else ""
            new_ch, conf = self.correct_char(ch, left, right)
            if conf > threshold:
                corrected.append(new_ch)
            else:
                corrected.append(ch)
        return "".join(corrected)

    def learn(self, wrong, correct):
        """Add new correction to dictionary."""
        self.known_corrections[wrong] = correct
        # Persist
        if os.path.exists(DICT_PATH):
            with open(DICT_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
        else:
            data = {}
        if wrong in data and isinstance(data[wrong], dict):
            data[wrong]["correct"] = correct
            data[wrong]["freq"] = data[wrong].get("freq", 0) + 1
        else:
            data[wrong] = {"correct": correct, "freq": 1}
        with open(DICT_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Learned: '{wrong}' → '{correct}'")


def build_common_vocab():
    """Generate a common Chinese words list for context validation."""
    # High-frequency 2-3 char words covering common domains
    words = [
        # General
        "数据", "系统", "管理", "监测", "分析", "统计", "报告", "查询",
        "信息", "平台", "服务", "设置", "配置", "用户", "角色", "权限",
        "状态", "时间", "日期", "更新", "删除", "编辑", "保存", "取消",
        "确认", "提交", "导出", "导入", "搜索", "筛选", "排序", "分页",
        # UI elements
        "按钮", "列表", "表格", "图表", "菜单", "标签", "输入", "选择",
        "下拉", "弹窗", "提示", "加载", "刷新", "返回", "首页", "详情",
        # Data terms
        "总览", "趋势", "对比", "均价", "最高", "最低", "环比", "同比",
        "涨幅", "跌幅", "波动", "预警", "异常", "正常", "风险", "安全",
        # Agriculture
        "农产品", "市场", "价格", "批发", "零售", "产地", "蔬菜", "水果",
        "肉类", "禽蛋", "水产", "粮食", "大白菜", "小白菜", "黄瓜", "西红柿",
        "猪肉", "牛肉", "羊肉", "鸡蛋", "苹果", "香蕉", "土豆", "茄子",
        # Tech
        "数据库", "接口", "采集", "爬虫", "运行", "成功", "失败", "超时",
        "响应", "字典", "字段", "类型", "名称", "描述", "备注", "启用",
        "禁用", "监控", "日志", "任务", "调度", "频率", "来源", "目标",
        # Business
        "供应", "需求", "库存", "订单", "客户", "项目", "部门", "通知",
        "审批", "流程", "规则", "策略", "指标", "目标", "完成", "进度",
    ]
    return words


def init_vocab():
    """Initialize common vocabulary file."""
    vocab_path = os.path.join(DATA_DIR, "common_words.json")
    words = build_common_vocab()
    with open(vocab_path, "w", encoding="utf-8") as f:
        json.dump(words, f, ensure_ascii=False, indent=2)
    print(f"Initialized vocabulary with {len(words)} words at {vocab_path}")
    print("Add more domain words to improve correction accuracy.")


def correct_file(results_path):
    """Apply smart correction to OCR results."""
    corrector = SmartCorrector()

    with open(results_path, "r", encoding="utf-8") as f:
        results = json.load(f)

    print("=" * 60)
    print("SMART-CORRECTED OCR OUTPUT (Trie + CharSimilarity)")
    print("=" * 60)

    for region in results:
        print(f"\n--- Region {region['region']} ---")
        for line in region["content"]:
            original = line["text"]
            corrected = corrector.correct_text(original)
            marker = "✓" if line["confidence"] > 0.7 else "~" if line["confidence"] >= 0.4 else "?"
            if corrected != original:
                print(f"  {marker} {corrected}")
                print(f"    [raw: {original}]")
            else:
                print(f"  {marker} {corrected}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("""Usage:
  python3 smart_correct.py correct <results.json>  # Full correction pipeline
  python3 smart_correct.py learn <wrong> <correct> # Learn new pattern
  python3 smart_correct.py similar <char>          # Find similar characters
  python3 smart_correct.py init-vocab              # Initialize vocabulary
  python3 smart_correct.py test <text>             # Test correction on text
""")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "correct" and len(sys.argv) >= 3:
        correct_file(sys.argv[2])
    elif cmd == "learn" and len(sys.argv) >= 4:
        corrector = SmartCorrector()
        corrector.learn(sys.argv[2], sys.argv[3])
    elif cmd == "similar" and len(sys.argv) >= 3:
        cs = CharSimilarity()
        char = sys.argv[2]
        similar = cs.find_similar(char, top_n=10, threshold=0.3)
        print(f"Characters similar to '{char}':")
        for c, score in similar:
            print(f"  {c} (similarity: {score:.3f})")
    elif cmd == "init-vocab":
        init_vocab()
    elif cmd == "test" and len(sys.argv) >= 3:
        corrector = SmartCorrector()
        text = " ".join(sys.argv[2:])
        corrected = corrector.correct_text(text)
        print(f"Input:     {text}")
        print(f"Corrected: {corrected}")
    else:
        print("Invalid command. Run without args for usage.")
