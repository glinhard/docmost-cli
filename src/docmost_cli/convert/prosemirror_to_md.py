"""ProseMirror JSON → Markdown converter.

Handles all Docmost node types and marks, converting ProseMirror
document trees into GitHub-Flavored Markdown.
"""

from collections.abc import Callable
from typing import Any

__all__ = ["convert_to_markdown"]

_NodeHandler = Callable[[dict[str, Any]], str]


class ProseMirrorConverter:
    """Recursive ProseMirror node walker that produces Markdown output."""

    def __init__(self) -> None:
        self._indent = 0
        self._list_type: list[str] = []  # stack: "bullet", "ordered", "task"
        self._ordered_counter: list[int] = []  # counter per ordered list level

    def convert(self, doc: dict[str, Any]) -> str:
        """Convert a ProseMirror document to Markdown.

        Args:
            doc: ProseMirror document dict (root node with type "doc").

        Returns:
            Markdown string ending with a single newline.
        """
        if not isinstance(doc, dict):
            return ""
        result = self._walk_node(doc)
        return result.rstrip("\n") + "\n"

    # -- Dispatch -----------------------------------------------------------

    def _walk_node(self, node: dict[str, Any]) -> str:
        """Dispatch to the handler for a node's type."""
        node_type = node.get("type", "")
        handler: _NodeHandler | None = getattr(self, f"_node_{node_type}", None)
        if handler:
            return handler(node)
        # Unknown node: try to extract content recursively
        return self._walk_children(node)

    def _walk_children(self, node: dict[str, Any]) -> str:
        """Walk all child nodes and concatenate their output."""
        return "".join(self._walk_node(child) for child in node.get("content", []))

    # -- Block nodes --------------------------------------------------------

    def _node_doc(self, node: dict[str, Any]) -> str:
        return self._walk_children(node)

    def _node_paragraph(self, node: dict[str, Any]) -> str:
        text = self._render_inline(node.get("content", []))
        # Inside a list item, don't add double newline
        if self._indent > 0:
            return text
        return text + "\n\n"

    def _node_heading(self, node: dict[str, Any]) -> str:
        attrs = node.get("attrs")
        raw_level = attrs.get("level", 1) if isinstance(attrs, dict) else 1
        try:
            level = max(1, min(6, int(raw_level)))
        except (TypeError, ValueError):
            level = 1
        text = self._render_inline(node.get("content", []))
        return "#" * level + " " + text + "\n\n"

    def _node_bulletList(self, node: dict[str, Any]) -> str:
        return self._handle_list(node, "bullet")

    def _node_orderedList(self, node: dict[str, Any]) -> str:
        return self._handle_list(node, "ordered")

    def _node_taskList(self, node: dict[str, Any]) -> str:
        return self._handle_list(node, "task")

    def _handle_list(self, node: dict[str, Any], list_type: str) -> str:
        self._list_type.append(list_type)
        self._indent += 1
        if list_type == "ordered":
            self._ordered_counter.append(0)

        result = ""
        for child in node.get("content", []):
            if child.get("type") in ("listItem", "taskItem"):
                result += self._handle_list_item(child)

        self._indent -= 1
        self._list_type.pop()
        if list_type == "ordered":
            self._ordered_counter.pop()

        # Add trailing newline after top-level list
        if self._indent == 0:
            result += "\n"
        return result

    def _node_listItem(self, node: dict[str, Any]) -> str:
        return self._handle_list_item(node)

    def _node_taskItem(self, node: dict[str, Any]) -> str:
        return self._handle_list_item(node)

    def _handle_list_item(self, node: dict[str, Any]) -> str:
        indent = "  " * (self._indent - 1)
        current_type = self._list_type[-1] if self._list_type else "bullet"

        # Determine prefix
        if current_type == "task":
            checked = node.get("attrs", {}).get("checked", False)
            prefix = "- [x] " if checked else "- [ ] "
        elif current_type == "ordered":
            self._ordered_counter[-1] += 1
            prefix = f"{self._ordered_counter[-1]}. "
        else:
            prefix = "- "

        # Separate inline content from nested lists
        text_parts: list[str] = []
        nested_parts: list[str] = []
        for child in node.get("content", []):
            child_type = child.get("type", "")
            if child_type in ("bulletList", "orderedList", "taskList"):
                nested_parts.append(self._walk_node(child))
            elif child_type == "paragraph":
                text_parts.append(self._render_inline(child.get("content", [])))
            else:
                text_parts.append(self._walk_node(child))

        text = " ".join(t.strip() for t in text_parts if t.strip())
        result = indent + prefix + text + "\n"
        result += "".join(nested_parts)
        return result

    def _node_codeBlock(self, node: dict[str, Any]) -> str:
        lang = node.get("attrs", {}).get("language", "")
        code = self._render_inline(node.get("content", []))
        return f"```{lang}\n{code}\n```\n\n"

    def _node_blockquote(self, node: dict[str, Any]) -> str:
        content = self._walk_children(node)
        lines = content.rstrip("\n").split("\n")
        quoted = "\n".join("> " + line for line in lines)
        return quoted + "\n\n"

    def _node_horizontalRule(self, node: dict[str, Any]) -> str:
        return "---\n\n"

    def _node_table(self, node: dict[str, Any]) -> str:
        rows = node.get("content", [])
        if not rows:
            return ""

        output_lines: list[str] = []
        for i, row in enumerate(rows):
            cells = row.get("content", [])
            cell_texts = []
            for cell in cells:
                # Cell content is usually paragraphs
                text = self._walk_children(cell).strip().replace("\n", " ")
                # Escape pipes in cell content
                text = text.replace("|", "\\|")
                cell_texts.append(text)

            output_lines.append("| " + " | ".join(cell_texts) + " |")

            # Separator after header row
            if i == 0:
                output_lines.append("|" + "|".join("---" for _ in cell_texts) + "|")

        return "\n".join(output_lines) + "\n\n"

    def _node_image(self, node: dict[str, Any]) -> str:
        attrs = node.get("attrs", {})
        alt = attrs.get("alt", "")
        src = attrs.get("src", "")
        title = attrs.get("title", "")
        if title:
            return f'![{alt}]({src} "{title}")\n\n'
        return f"![{alt}]({src})\n\n"

    def _node_hardBreak(self, node: dict[str, Any]) -> str:
        return "\n"

    def _node_callout(self, node: dict[str, Any]) -> str:
        callout_type = node.get("attrs", {}).get("type", "info")
        content = self._walk_children(node).strip()
        return f"> **{callout_type}**: {content}\n\n"

    def _node_details(self, node: dict[str, Any]) -> str:
        summary = ""
        body = ""
        for child in node.get("content", []):
            if child.get("type") == "detailsSummary":
                summary = self._render_inline(child.get("content", []))
            elif child.get("type") == "detailsContent":
                body = self._walk_children(child).strip()
        return f"<details>\n<summary>{summary.strip()}</summary>\n\n{body}\n</details>\n\n"

    def _node_detailsSummary(self, node: dict[str, Any]) -> str:
        return self._render_inline(node.get("content", []))

    def _node_detailsContent(self, node: dict[str, Any]) -> str:
        return self._walk_children(node)

    def _node_mathBlock(self, node: dict[str, Any]) -> str:
        content = self._render_inline(node.get("content", []))
        return f"$$\n{content.strip()}\n$$\n\n"

    def _node_embed(self, node: dict[str, Any]) -> str:
        src = node.get("attrs", {}).get("src", "")
        return f"[Embed: {src}]\n\n"

    def _node_drawio(self, node: dict[str, Any]) -> str:
        return "[Diagram: drawio]\n\n"

    def _node_excalidraw(self, node: dict[str, Any]) -> str:
        return "[Diagram: excalidraw]\n\n"

    # -- Inline rendering ---------------------------------------------------

    def _render_inline(self, content: list[dict[str, Any]]) -> str:
        """Render inline nodes (text with marks, hard breaks, etc.)."""
        parts: list[str] = []
        for node in content or []:
            node_type = node.get("type", "")
            if node_type == "text":
                text = node.get("text", "")
                marks = node.get("marks", [])
                parts.append(self._apply_marks(text, marks))
            elif node_type == "hardBreak":
                parts.append("\n")
            elif node_type == "image":
                attrs = node.get("attrs", {})
                alt = attrs.get("alt", "")
                src = attrs.get("src", "")
                parts.append(f"![{alt}]({src})")
            else:
                # Other inline nodes
                parts.append(self._walk_node(node))
        return "".join(parts)

    def _apply_marks(self, text: str, marks: list[dict[str, Any]]) -> str:
        """Wrap text in Markdown mark delimiters."""
        if not marks:
            return text

        # Sort by precedence: outermost wraps first
        precedence = {
            "link": 0,
            "bold": 1,
            "italic": 2,
            "strike": 3,
            "code": 4,
            "highlight": 5,
            "underline": 6,
        }
        sorted_marks = sorted(
            marks,
            key=lambda m: precedence.get(m.get("type", ""), 99),
            reverse=True,
        )

        for mark in sorted_marks:
            text = self._apply_single_mark(text, mark)
        return text

    @staticmethod
    def _apply_single_mark(text: str, mark: dict[str, Any]) -> str:
        """Apply a single mark to text."""
        mark_type = mark.get("type", "")
        attrs = mark.get("attrs", {})

        if mark_type == "bold":
            return f"**{text}**"
        if mark_type == "italic":
            return f"*{text}*"
        if mark_type == "code":
            return f"`{text}`"
        if mark_type == "strike":
            return f"~~{text}~~"
        if mark_type == "link":
            href = attrs.get("href", "")
            return f"[{text}]({href})"
        if mark_type == "highlight":
            return f"=={text}=="
        if mark_type == "underline":
            return f"<u>{text}</u>"
        # Unknown mark: passthrough
        return text


def convert_to_markdown(doc: dict[str, Any]) -> str:
    """Convert a ProseMirror document to Markdown.

    Args:
        doc: ProseMirror document dict.

    Returns:
        Markdown string.
    """
    return ProseMirrorConverter().convert(doc)
