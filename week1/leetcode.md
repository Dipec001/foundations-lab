# Week 1 LeetCode: Arrays and hashing

| Problem | Pattern (one line) | Time / space | Solved alone? |
|---|---|---|---|
| [1. Two Sum](https://leetcode.com/problems/two-sum/) | | | Redo cold on Saturday |
| [217. Contains Duplicate](https://leetcode.com/problems/contains-duplicate/) | Add each number to a set; if it's already there, return True. | O(n) / O(n) | Yes, cold rewrite in 3m 21s |
| [242. Valid Anagram](https://leetcode.com/problems/valid-anagram/) | Count each character in a dictionary for both strings, then compare the counts. | O(n) / O(1) (at most 26 keys) | Yes, 26m 12s |

---

## 242. Valid Anagram

**My solution (accepted):**

```python
class Solution:
    def isAnagram(self, s: str, t: str) -> bool:
        if len(s) != len(t):
            return False
        new_dict_s = {}
        new_dict_t = {}
        num_seen = 1
        for letter in s:
            if letter in new_dict_s:
                new_dict_s[letter] += 1
            else:
                new_dict_s[letter] = num_seen
        for letter in t:
            if letter in new_dict_t:
                new_dict_t[letter] += 1
            else:
                new_dict_t[letter] = num_seen
        for k, v in new_dict_s.items():
            if k not in new_dict_t:
                return False
            if k in new_dict_t:
                if v != new_dict_t[k]:
                    return False
        return True
```

**Cleaner version (same idea):**

```python
class Solution:
    def isAnagram(self, s: str, t: str) -> bool:
        if len(s) != len(t):
            return False
        count_s, count_t = {}, {}
        for a, b in zip(s, t):
            count_s[a] = count_s.get(a, 0) + 1
            count_t[b] = count_t.get(b, 0) + 1
        return count_s == count_t
```

**What I learned:**
- Checking only the keys of `s` is enough. The lengths are equal, so if every letter in `s` has the same count in `t`, there's no room left in `t` for extra letters.
- `dict.get(key, 0) + 1` replaces the if/else. Comparing two dicts with `==` replaces the final loop.
- **Follow-up (Unicode):** the dictionary version already works, but a 26-slot array wouldn't. One catch: "é" can be stored as one character or as "e" plus an accent mark, so normalise both strings first with `unicodedata.normalize("NFC", s)`.
