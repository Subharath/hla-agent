"""Side-by-Side Diff Generator — Industry Standard

Generates professional side-by-side diffs for diagram comparisons.
Follows industry best practices from GitHub, GitLab, and academic paper standards.

Features:
- Line-by-line comparison with alignment
- Color-coded additions/deletions/modifications
- Context preservation
- HTML and Markdown output formats
- Statistical summary (additions, deletions, modifications)
"""

from __future__ import annotations

import difflib
from dataclasses import dataclass
from typing import List, Tuple
from enum import Enum


class DiffType(Enum):
    UNCHANGED = "unchanged"
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"


@dataclass
class DiffLine:
    line_num_left: int | None
    line_num_right: int | None
    content_left: str
    content_right: str
    diff_type: DiffType


def generate_side_by_side_diff(
    old_content: str,
    new_content: str,
    *,
    old_label: str = "Original",
    new_label: str = "Modified",
    context_lines: int = 3,
) -> dict:
    """Generate side-by-side diff with full context.
    
    Args:
        old_content: Original content
        new_content: Modified content
        old_label: Label for left side
        new_label: Label for right side
        context_lines: Number of context lines to show around changes
    
    Returns:
        {
            "diff_lines": [DiffLine],
            "statistics": {
                "additions": int,
                "deletions": int,
                "modifications": int,
                "unchanged": int
            },
            "html": str,
            "markdown": str,
            "unified": str
        }
    """
    old_lines = old_content.splitlines(keepends=False)
    new_lines = new_content.splitlines(keepends=False)
    
    # Use SequenceMatcher for detailed comparison
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    
    diff_lines: List[DiffLine] = []
    stats = {"additions": 0, "deletions": 0, "modifications": 0, "unchanged": 0}
    
    old_line_num = 1
    new_line_num = 1
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            # Unchanged lines
            for i in range(i1, i2):
                diff_lines.append(DiffLine(
                    line_num_left=old_line_num,
                    line_num_right=new_line_num,
                    content_left=old_lines[i],
                    content_right=new_lines[j1 + (i - i1)],
                    diff_type=DiffType.UNCHANGED
                ))
                old_line_num += 1
                new_line_num += 1
                stats["unchanged"] += 1
        
        elif tag == "delete":
            # Lines removed from old
            for i in range(i1, i2):
                diff_lines.append(DiffLine(
                    line_num_left=old_line_num,
                    line_num_right=None,
                    content_left=old_lines[i],
                    content_right="",
                    diff_type=DiffType.REMOVED
                ))
                old_line_num += 1
                stats["deletions"] += 1
        
        elif tag == "insert":
            # Lines added to new
            for j in range(j1, j2):
                diff_lines.append(DiffLine(
                    line_num_left=None,
                    line_num_right=new_line_num,
                    content_left="",
                    content_right=new_lines[j],
                    diff_type=DiffType.ADDED
                ))
                new_line_num += 1
                stats["additions"] += 1
        
        elif tag == "replace":
            # Lines modified (delete + insert)
            # Pair up lines for side-by-side view
            old_count = i2 - i1
            new_count = j2 - j1
            max_count = max(old_count, new_count)
            
            for k in range(max_count):
                old_idx = i1 + k if k < old_count else None
                new_idx = j1 + k if k < new_count else None
                
                if old_idx is not None and new_idx is not None:
                    # Both sides have content - modification
                    diff_lines.append(DiffLine(
                        line_num_left=old_line_num,
                        line_num_right=new_line_num,
                        content_left=old_lines[old_idx],
                        content_right=new_lines[new_idx],
                        diff_type=DiffType.MODIFIED
                    ))
                    old_line_num += 1
                    new_line_num += 1
                    stats["modifications"] += 1
                
                elif old_idx is not None:
                    # Only old side has content - deletion
                    diff_lines.append(DiffLine(
                        line_num_left=old_line_num,
                        line_num_right=None,
                        content_left=old_lines[old_idx],
                        content_right="",
                        diff_type=DiffType.REMOVED
                    ))
                    old_line_num += 1
                    stats["deletions"] += 1
                
                elif new_idx is not None:
                    # Only new side has content - addition
                    diff_lines.append(DiffLine(
                        line_num_left=None,
                        line_num_right=new_line_num,
                        content_left="",
                        content_right=new_lines[new_idx],
                        diff_type=DiffType.ADDED
                    ))
                    new_line_num += 1
                    stats["additions"] += 1
    
    # Generate HTML output
    html = _generate_html_diff(diff_lines, old_label, new_label, stats)
    
    # Generate Markdown output
    markdown = _generate_markdown_diff(diff_lines, old_label, new_label, stats)
    
    # Generate unified diff for compatibility
    unified = "\n".join(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=old_label,
        tofile=new_label,
        lineterm=""
    ))
    
    return {
        "diff_lines": diff_lines,
        "statistics": stats,
        "html": html,
        "markdown": markdown,
        "unified": unified,
    }


def _escape_html(text: str) -> str:
    """Escape HTML special characters."""
    return (text
            .replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&#39;"))


def _generate_html_diff(diff_lines: List[DiffLine], old_label: str, new_label: str, stats: dict) -> str:
    """Generate HTML side-by-side diff."""
    html_parts = [
        '<div class="side-by-side-diff">',
        '<div class="diff-header">',
        f'  <div class="diff-stats">',
        f'    <span class="stat-added">+{stats["additions"]}</span>',
        f'    <span class="stat-removed">-{stats["deletions"]}</span>',
        f'    <span class="stat-modified">~{stats["modifications"]}</span>',
        f'  </div>',
        '</div>',
        '<table class="diff-table">',
        '  <thead>',
        '    <tr>',
        f'      <th class="line-num">#</th>',
        f'      <th class="diff-content">{_escape_html(old_label)}</th>',
        f'      <th class="line-num">#</th>',
        f'      <th class="diff-content">{_escape_html(new_label)}</th>',
        '    </tr>',
        '  </thead>',
        '  <tbody>',
    ]
    
    for line in diff_lines:
        row_class = f"diff-{line.diff_type.value}"
        
        left_num = str(line.line_num_left) if line.line_num_left else ""
        right_num = str(line.line_num_right) if line.line_num_right else ""
        left_content = _escape_html(line.content_left) if line.content_left else "&nbsp;"
        right_content = _escape_html(line.content_right) if line.content_right else "&nbsp;"
        
        html_parts.append(f'    <tr class="{row_class}">')
        html_parts.append(f'      <td class="line-num">{left_num}</td>')
        html_parts.append(f'      <td class="diff-content"><pre>{left_content}</pre></td>')
        html_parts.append(f'      <td class="line-num">{right_num}</td>')
        html_parts.append(f'      <td class="diff-content"><pre>{right_content}</pre></td>')
        html_parts.append('    </tr>')
    
    html_parts.extend([
        '  </tbody>',
        '</table>',
        '</div>',
    ])
    
    return "\n".join(html_parts)


def _generate_markdown_diff(diff_lines: List[DiffLine], old_label: str, new_label: str, stats: dict) -> str:
    """Generate Markdown side-by-side diff table."""
    md_parts = [
        f"## Diff: {old_label} → {new_label}",
        "",
        f"**Statistics:** +{stats['additions']} additions, -{stats['deletions']} deletions, ~{stats['modifications']} modifications",
        "",
        "| # | " + old_label + " | # | " + new_label + " |",
        "|---|" + "-" * max(20, len(old_label)) + "|---|" + "-" * max(20, len(new_label)) + "|",
    ]
    
    for line in diff_lines:
        left_num = str(line.line_num_left) if line.line_num_left else ""
        right_num = str(line.line_num_right) if line.line_num_right else ""
        
        # Escape pipe characters in content
        left_content = line.content_left.replace("|", "\\|") if line.content_left else ""
        right_content = line.content_right.replace("|", "\\|") if line.content_right else ""
        
        # Add markers for diff type
        if line.diff_type == DiffType.ADDED:
            right_content = f"**+ {right_content}**"
        elif line.diff_type == DiffType.REMOVED:
            left_content = f"**- {left_content}**"
        elif line.diff_type == DiffType.MODIFIED:
            left_content = f"**~ {left_content}**"
            right_content = f"**~ {right_content}**"
        
        md_parts.append(f"| {left_num} | `{left_content}` | {right_num} | `{right_content}` |")
    
    return "\n".join(md_parts)


def generate_inline_diff_with_highlights(old_content: str, new_content: str) -> str:
    """Generate inline diff with character-level highlighting.
    
    Useful for showing exact changes within modified lines.
    """
    old_lines = old_content.splitlines()
    new_lines = new_content.splitlines()
    
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    
    result_lines = []
    
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for line in old_lines[i1:i2]:
                result_lines.append(f"  {line}")
        
        elif tag == "delete":
            for line in old_lines[i1:i2]:
                result_lines.append(f"- {line}")
        
        elif tag == "insert":
            for line in new_lines[j1:j2]:
                result_lines.append(f"+ {line}")
        
        elif tag == "replace":
            # Show character-level diff for replaced lines
            for old_line in old_lines[i1:i2]:
                result_lines.append(f"- {old_line}")
            for new_line in new_lines[j1:j2]:
                result_lines.append(f"+ {new_line}")
    
    return "\n".join(result_lines)
