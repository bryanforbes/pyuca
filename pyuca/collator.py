from __future__ import unicode_literals

import os.path
import re
import sys
import unicodedata
from io import open

from .trie import Trie
from .utils import hexstrings2int

try:
    chr = unichr
except NameError:
    pass

COLL_ELEMENT_PATTERN = re.compile(r"""
    \[
    (?:\*|\.)
    ([0-9A-Fa-f]{4})
    \.
    ([0-9A-Fa-f]{4})
    \.
    ([0-9A-Fa-f]{4})
    (?:\.[0-9A-Fa-f]{4,5})?
\]
""", re.X)


class BaseCollator(object):
    CJK_IDEAGRAPHS_EXT_C = True

    def __init__(self, filename=None):
        if filename is None:
            filename = os.path.join(
                os.path.dirname(__file__),
                "allkeys-{0}.txt".format(self.UCA_VERSION))
        self.table = Trie()
        self.implicit_weights = []
        self.load(filename)

    def load(self, filename):
        with open(filename) as keys_file:
            for line in keys_file:
                line = line.split("#", 1)[0].rstrip()

                if not line or line.startswith("@version"):
                    continue

                if line.startswith("@implicitweights"):
                    ch_range, base = line[len("@implicitweights"):].split(";")
                    range_start, range_end = ch_range.split("..")
                    self.implicit_weights.append([
                        int(range_start, 16), int(range_end, 16), int(base, 16)
                    ])
                    continue

                a, b = line.split(";", 1)
                char_list = hexstrings2int(a.split())
                coll_elements = []
                for x in COLL_ELEMENT_PATTERN.finditer(b.strip()):
                    weights = x.groups()
                    coll_elements.append(hexstrings2int(weights))
                self.table.add(char_list, coll_elements)

    def collation_elements(self, normalized_string):
        collation_elements = []

        lookup_key = self.build_lookup_key(normalized_string)
        while lookup_key:
            S, value, lookup_key = self.table.find_prefix(lookup_key)

            # handle non-starters

            last_class = None
            for i, C in enumerate(lookup_key):
                combining_class = unicodedata.combining(chr(C))
                if combining_class == 0 or combining_class == last_class:
                    break
                last_class = combining_class
                # C is a non-starter that is not blocked from S
                x, y, z = self.table.find_prefix(S + [C])
                if z == [] and y is not None:
                    lookup_key = lookup_key[:i] + lookup_key[i + 1:]
                    value = y
                    break  # ???

            if not value:

                codepoint = lookup_key.pop(0)
                value = self.implicit_weight(codepoint)

            collation_elements.extend(value)

        return collation_elements

    def sort_key_from_collation_elements(self, collation_elements):
        sort_key = []

        for level in range(4):
            if level:
                sort_key.append(0)  # level separator
            for element in collation_elements:
                if len(element) > level:
                    ce_l = element[level]
                    if ce_l:
                        sort_key.append(ce_l)

        return tuple(sort_key)

    def sort_key(self, string):
        normalized_string = unicodedata.normalize("NFD", string)
        collation_elements = self.collation_elements(normalized_string)
        return self.sort_key_from_collation_elements(collation_elements)

    def implicit_weight(self, cp):
        if 0x4E00 <= cp <= 0x9FCC or cp in [
                0xFA0E, 0xFA0F, 0xFA11, 0xFA13, 0xFA14, 0xFA1F,
                0xFA21, 0xFA23, 0xFA24, 0xFA27, 0xFA28, 0xFA29]:
            base = 0xFB40
            aaaa = base + (cp >> 15)
            bbbb = (cp & 0x7FFF) | 0x8000
        elif (0x3400 <= cp <= 0x4DB5 or 0x20000 <= cp <= 0x2A6D6 or
                (self.CJK_IDEAGRAPHS_EXT_C and 0x2A700 <= cp <= 0x2B734) or
                0x2B740 <= cp <= 0x2B81D):
            base = 0xFB80
            aaaa = base + (cp >> 15)
            bbbb = (cp & 0x7FFF) | 0x8000
        else:
            aaaa = None
            for (start, end, base) in self.implicit_weights:
                if start <= cp <= end:
                    aaaa = base
                    bbbb = (cp - start) | 0x8000
                    break
            if aaaa is None:
                base = 0xFBC0
                aaaa = base + (cp >> 15)
                bbbb = (cp & 0x7FFF) | 0x8000

        return [[aaaa, 0x0020, 0x002], [bbbb, 0x0000, 0x0000]]

    def build_lookup_key(self, text):
        return [ord(ch) for ch in text]


class Collator_6_3_0(BaseCollator):
    UCA_VERSION = '6.3.0'


class Collator_8_0_0(BaseCollator):
    UCA_VERSION = "8.0.0"


class Collator_9_0_0(BaseCollator):
    UCA_VERSION = "9.0.0"


class Collator_10_0_0(BaseCollator):
    UCA_VERSION = "10.0.0"


class Collator_5_2_0(BaseCollator):
    UCA_VERSION = '5.2.0'
    # Supposedly, extension C *was* introduced in 5.2.0, but the tests show
    # otherwise. Treat the tests as king.
    CJK_IDEAGRAPHS_EXT_C = False

    non_char_code_points = []
    for i in range(17):
        base = i << 16
        non_char_code_points.append(base + 0xFFFE)
        non_char_code_points.append(base + 0xFFFF)
    for i in range(32):
        non_char_code_points.append(0xFDD0 + i)

    def _valid_char(self, ch):
        category = unicodedata.category(ch)
        if category == 'Cs':
            return False
        if category != 'Cn':
            return True
        return ord(ch) not in self.non_char_code_points

    def build_lookup_key(self, text):
        return [ord(ch) for ch in text if self._valid_char(ch)]


if sys.version_info < (3,):
    Collator = Collator_5_2_0
else:
    Collator = Collator_6_3_0
