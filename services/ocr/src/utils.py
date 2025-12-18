import re
from dataclasses import dataclass
from typing import List, Optional, Tuple


_REF_RE = re.compile(r"<\|ref\|>(?P<ref>[^<]+)<\|/ref\|>")
_DET_RE = re.compile(r"<\|det\|>\s*\[\[(?P<bbox>[0-9,\s]+)\]\]\s*<\|/det\|>")


@dataclass(frozen=True)
class ParsedBlock:
    ref: str                      # e.g. "text", "title", "image", "image_caption"
    bbox: Optional[Tuple[int,int,int,int]]
    text: str


def _parse_bbox(bbox_str: str) -> Optional[Tuple[int, int, int, int]]:
    parts = [p.strip() for p in bbox_str.split(",")]
    if len(parts) != 4:
        return None
    try:
        x1, y1, x2, y2 = (int(p) for p in parts)
        return (x1, y1, x2, y2)
    except ValueError:
        return None


def parse_deepseek_grounded_output(s: str) -> List[ParsedBlock]:
    """
    Parses DeepSeek-OCR grounded output string into blocks.

    Expected pattern per block:
      <|ref|>TYPE<|/ref|><|det|>[[x1, y1, x2, y2]]<|/det|>
      TEXT...

    Text runs until the next <|ref|>... or end of string.
    """
    blocks: List[ParsedBlock] = []
    i = 0
    n = len(s)

    while i < n:
        m_ref = _REF_RE.search(s, i)
        if not m_ref:
            break

        ref = m_ref.group("ref").strip()
        j = m_ref.end()

        m_det = _DET_RE.search(s, j)
        bbox = None
        if m_det and m_det.start() == j:
            bbox = _parse_bbox(m_det.group("bbox"))
            j = m_det.end()

        # text starts after tag line; consume up to next <|ref|> or end
        m_next = _REF_RE.search(s, j)
        text_chunk = s[j : (m_next.start() if m_next else n)].strip()

        # Remove any stray det tags inside (rare)
        text_chunk = _DET_RE.sub("", text_chunk).strip()

        blocks.append(ParsedBlock(ref=ref, bbox=bbox, text=text_chunk))
        i = m_next.start() if m_next else n

    return blocks


def blocks_to_markdown(blocks: List[ParsedBlock]) -> str:
    """
    Converts parsed blocks to markdown-ish text.
    You can tune this, e.g. treat title blocks as headings.
    """
    out: List[str] = []
    for b in blocks:
        t = (b.text or "").strip()
        if not t:
            continue

        if b.ref == "title":
            # ensure a heading
            if not t.lstrip().startswith("#"):
                out.append(f"# {t}")
            else:
                out.append(t)
        elif b.ref == "image_caption":
            out.append(t)
        elif b.ref == "text":
            out.append(t)
        else:
            # include other types conservatively
            out.append(t)

    return "\n\n".join(out).strip() + ("\n" if out else "")
