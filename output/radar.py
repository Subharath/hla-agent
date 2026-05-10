"""
HLA Agent — Radar Chart Generator
Publication-quality radar chart comparing candidates across 5 metrics.
"""

import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import matplotlib.colors as mcolors


# Color palette for models
MODEL_COLORS = {
    "llama3.1": "#00C9A7",   # Teal
    "mistral":  "#845EC2",   # Purple
    "qwen3":  "#FF6F00",   # Orange
}

FALLBACK_COLORS = ["#00C9A7", "#845EC2", "#FF6F00", "#E84393", "#0984E3", "#FDCB6E"]


def generate_radar_chart(candidates: list, output_path: str,
                         title: str = "Architecture Evaluation — Radar Chart"):
    """
    Generate a radar chart comparing candidates across 5 metrics.

    Args:
        candidates: List of dicts with 'model', 'candidate_num', 'scores'
        output_path: File path to save PNG
        title: Chart title
    """
    # Dynamically extract NFR axes from the first candidate
    nfr_metrics = []
    if candidates and "details" in candidates[0].get("scores", {}):
        alignment_map = candidates[0]["scores"]["details"].get("nas", {}).get("alignment_map", {})
        nfr_metrics = list(alignment_map.keys())

    if not nfr_metrics:
        # Fallback if no NFRs found
        nfr_metrics = ["Performance", "Scalability", "Security", "Availability", "Maintainability"]
        
    num_metrics = len(nfr_metrics)
    if num_metrics < 3:
        # Pad with dummy metrics if fewer than 3, just so radar chart draws
        nfr_metrics.extend([f"NFR_{i}" for i in range(num_metrics, 3)])
        num_metrics = len(nfr_metrics)

    angles = np.linspace(0, 2 * np.pi, num_metrics, endpoint=False).tolist()
    angles += angles[:1]  # Close the polygon

    fig, ax = plt.subplots(figsize=(10, 10), subplot_kw=dict(polar=True))
    fig.patch.set_facecolor('#1a1a2e')
    ax.set_facecolor('#16213e')

    # Draw threshold circle
    threshold_vals = [0.75] * num_metrics
    threshold_vals += threshold_vals[:1]
    ax.plot(angles, threshold_vals, 'w--', linewidth=1.5, alpha=0.4, label='Threshold (0.75)')
    ax.fill(angles, threshold_vals, alpha=0.05, color='white')

    # Plot each candidate
    for i, candidate in enumerate(candidates):
        model = candidate.get("model", f"Model {i+1}")
        cnum = candidate.get("candidate_num", 1)
        scores = candidate.get("scores", {})
        details = scores.get("details", {})
        
        alignment_map = details.get("nas", {}).get("alignment_map", {})
        
        values = []
        for nfr in nfr_metrics:
            if nfr in alignment_map:
                values.append(alignment_map[nfr].get("score", 0.0))
            else:
                values.append(0.0)
                
        values += values[:1]  # Close polygon

        color = MODEL_COLORS.get(model, FALLBACK_COLORS[i % len(FALLBACK_COLORS)])
        label = f"{model} #{cnum} (Phase1 CAS={scores.get('CAS', 0):.3f})"

        ax.plot(angles, values, 'o-', linewidth=2.5, markersize=8,
                color=color, label=label, alpha=0.85)
        ax.fill(angles, values, alpha=0.15, color=color)

    # Styling
    ax.set_xticks(angles[:-1])
    # Capitalize the NFR names for better display
    display_metrics = [m.capitalize() for m in nfr_metrics]
    ax.set_xticklabels(display_metrics, fontsize=14, fontweight='bold', color='white')

    ax.set_ylim(0, 1.05)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(['0.2', '0.4', '0.6', '0.8', '1.0'],
                       fontsize=10, color='#aaa')
    ax.yaxis.grid(True, color='#333', linewidth=0.5)
    ax.xaxis.grid(True, color='#444', linewidth=0.5)

    ax.set_title(title, fontsize=18, fontweight='bold', color='white',
                 pad=30, y=1.08)

    legend = ax.legend(loc='upper right', bbox_to_anchor=(1.35, 1.15),
                       fontsize=11, framealpha=0.3, facecolor='#1a1a2e',
                       edgecolor='#444', labelcolor='white')

    plt.tight_layout()
    plt.savefig(output_path, dpi=200, bbox_inches='tight',
                facecolor=fig.get_facecolor(), edgecolor='none')
    plt.close(fig)

    return output_path
