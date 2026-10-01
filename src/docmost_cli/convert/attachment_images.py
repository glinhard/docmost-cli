"""Markdown pre-processing that keeps uploaded images visible on share links.

Docmost's public share view rewrites each attachment URL in a page to a
signed `/api/files/public/<id>/<name>?jwt=...` form, but it finds those
attachments by the image node's `attachmentId` attribute, not by its `src`.
The web editor sets that attribute on upload. Markdown image syntax cannot
carry it, so an image written as `![alt](/api/files/<id>/<name>)` stores only
a `src`. A share link then skips it and serves the private URL, which needs a
login and shows a broken image to every anonymous reader.

Docmost's Markdown parser passes inline HTML through, and its image node
reads `attachmentId` from `data-attachment-id`. Rewriting those images to
`<img ... data-attachment-id="<id>">` before sending stores the same node the
editor would have created.
"""

import html
import re

__all__ = ["link_attachment_images"]

_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"

# An inline code span (left untouched) or a Markdown image whose source is a
# Docmost-hosted file. Only relative `/api/files/` and `/files/` sources
# qualify: those are the only forms the share view rewrites, and the
# already-public `/files/public/...` form fails the UUID match by design.
_CODE_OR_IMAGE = re.compile(
    r"(?P<code>(?P<ticks>`+).+?(?P=ticks))"
    r"|(?P<image>!\[(?P<alt>(?:\\.|[^\]\\])*)\]"
    rf"\((?P<src>/(?:api/)?files/(?P<id>{_UUID})/[^\s()]+)"
    r'(?:\s+"(?P<title>(?:\\.|[^"\\])*)")?\))'
)

_FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
_MD_ESCAPE = re.compile(r"\\([!-/:-@\[-`{-~])")


def _unescape(text: str) -> str:
    """Drop Markdown backslash escapes, which mean nothing inside HTML."""
    return _MD_ESCAPE.sub(r"\1", text)


def _to_img_tag(match: re.Match[str]) -> str:
    if match.group("code") is not None:
        return match.group(0)
    attrs = [
        ("src", match.group("src")),
        ("alt", _unescape(match.group("alt"))),
    ]
    title = match.group("title")
    if title:
        attrs.append(("title", _unescape(title)))
    attrs.append(("data-attachment-id", match.group("id")))
    rendered = " ".join(f'{name}="{html.escape(value, quote=True)}"' for name, value in attrs)
    return f"<img {rendered}>"


def link_attachment_images(markdown: str) -> str:
    """Rewrite Docmost-hosted Markdown images to carry their attachment ID.

    Turns `![alt](/api/files/<id>/<name>)` into
    `<img src="/api/files/<id>/<name>" alt="alt" data-attachment-id="<id>">`
    so the stored image node has the `attachmentId` the share view needs.
    Fenced code blocks and inline code spans are left as they are, as is any
    image hosted elsewhere.

    Args:
        markdown: Markdown text about to be sent to Docmost.

    Returns:
        The same Markdown with qualifying images rewritten.
    """
    if "files/" not in markdown:
        return markdown

    out: list[str] = []
    fence: str | None = None
    for line in markdown.splitlines(keepends=True):
        opener = _FENCE.match(line)
        if fence is not None:
            # A fence closes on a run of the same character at least as long.
            if opener and opener.group(1)[0] == fence[0] and len(opener.group(1)) >= len(fence):
                fence = None
            out.append(line)
        elif opener:
            fence = opener.group(1)
            out.append(line)
        else:
            out.append(_CODE_OR_IMAGE.sub(_to_img_tag, line))
    return "".join(out)
