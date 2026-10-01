"""Tests for tagging Docmost-hosted Markdown images with their attachment ID."""

from docmost_cli.convert.attachment_images import link_attachment_images

ID = "01a0f7be-78a3-71d8-8f23-6a0024546f12"
SRC = f"/api/files/{ID}/find-queue.png"


def test_rewrites_hosted_image() -> None:
    assert link_attachment_images(f"![Queue]({SRC})\n") == (
        f'<img src="{SRC}" alt="Queue" data-attachment-id="{ID}">\n'
    )


def test_empty_alt_and_legacy_files_prefix() -> None:
    src = f"/files/{ID}/a.png"
    assert link_attachment_images(f"![]({src})") == (
        f'<img src="{src}" alt="" data-attachment-id="{ID}">'
    )


def test_title_and_escapes_are_carried_into_html() -> None:
    result = link_attachment_images(f'![a \\[b\\] & "c"]({SRC} "the \\"title\\"")')
    assert result == (
        f'<img src="{SRC}" alt="a [b] &amp; &quot;c&quot;" '
        f'title="the &quot;title&quot;" data-attachment-id="{ID}">'
    )


def test_inline_image_keeps_surrounding_text() -> None:
    result = link_attachment_images(f"See ![x]({SRC}) here and ![y](https://x.org/y.png).")
    assert result == (
        f'See <img src="{SRC}" alt="x" data-attachment-id="{ID}"> here '
        "and ![y](https://x.org/y.png)."
    )


def test_leaves_external_public_and_non_uuid_sources_alone() -> None:
    md = (
        "![a](https://example.com/a.png)\n"
        f"![b](/api/files/public/{ID}/b.png?jwt=t)\n"
        "![c](/api/files/not-a-uuid/c.png)\n"
        f"[file](/api/files/{ID}/doc.pdf)\n"
    )
    assert link_attachment_images(md) == md


def test_leaves_code_alone() -> None:
    md = f"```md\n![x]({SRC})\n```\n`![x]({SRC})`\n~~~~\n![x]({SRC})\n~~~~\n"
    assert link_attachment_images(md) == md


def test_rewrites_after_a_closed_fence() -> None:
    md = f"```\ncode\n```\n![x]({SRC})\n"
    assert link_attachment_images(md).endswith(f'data-attachment-id="{ID}">\n')
