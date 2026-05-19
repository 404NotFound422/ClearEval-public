#!/usr/bin/env python3
"""
ClearEval Human-Machine Alignment Combined Figure Generator

Date: 2025-02-27

Features:
  - Sans-serif font (Liberation Sans)
  - 600 DPI resolution
  - Full metric names (no abbreviations)
  - Extended Y-axis for Bland-Altman plot
  - Filtered outliers (3 SD)

Usage:
    python plot_alignment_combined.py
    
Output:
    - fig_alignment_combined.png (600 DPI)
"""

import json, sys, os
import numpy as np
from scipy import stats
import matplotlib.pyplot as plt
import matplotlib
matplotlib.use('Agg')
from matplotlib.lines import Line2D

# ============================================================================
# Configuration
# ============================================================================

plt.rcParams.update({
    'font.family': 'sans-serif',
    'font.sans-serif': ['Liberation Sans', 'DejaVu Sans', 'Arial', 'Helvetica'],
    'axes.unicode_minus': False,
    'font.size': 10,
    'axes.labelsize': 11,
    'axes.titlesize': 12,
    'xtick.labelsize': 9,
    'ytick.labelsize': 9,
    'legend.fontsize': 8,
    'figure.dpi': 600,
    'savefig.dpi': 600,
    'axes.linewidth': 0.8,
})

COLORS = {
    'pearson': '#2166AC',
    'spearman': '#4DAF4A',
    'scatter': '#2166AC',
    'bias': '#B2182B',
    'loa': '#999999',
}

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
INPUT_FILE = 'dataset/Q+AR/score_results/ClearEval_Human_Grading_Results.json'
OUTPUT_PNG = 'results/fig_alignment_combined.png'

# ============================================================================
# Data Loading
# ============================================================================

def load_data(filepath):
    """Load and extract human and machine scores from JSON file."""
    with open(filepath, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    human_scores = []
    machine_scores = []
    
    for record in data:
        he = record['human_evaluation']
        me = record.get('machine_evaluation', {}).get('scores', None)
        
        if me is None:
            continue
        
        h_comp = he['completeness']['total_score']
        h_corr = he['correctness']['total_score']
        h_eff = he['effectiveness'].get('total_score', 0)
        if h_eff is None:
            h_eff = 0
        
        m_comp = me['completeness']['total_completeness_score']
        m_corr = me['correctness']['total_correctness_score']
        m_eff = me['effectiveness']['total_weighted_score']
        
        human_scores.append({
            'completeness': h_comp,
            'correctness': h_corr,
            'effectiveness': h_eff,
            'total': h_comp + h_corr + h_eff
        })
        machine_scores.append({
            'completeness': m_comp,
            'correctness': m_corr,
            'effectiveness': m_eff,
            'total': m_comp + m_corr + m_eff
        })
    
    return human_scores, machine_scores

# ============================================================================
# Statistics Functions
# ============================================================================

def calc_correlation_stats(h, m):
    """Calculate Pearson r and Spearman rho with 95% CI."""
    h, m = np.array(h), np.array(m)
    n = len(h)
    
    r, _ = stats.pearsonr(h, m)
    z = 0.5 * np.log((1 + r) / (1 - r))
    se = 1 / np.sqrt(n - 3)
    r_lower = (np.exp(2*(z - 1.96*se)) - 1) / (np.exp(2*(z - 1.96*se)) + 1)
    r_upper = (np.exp(2*(z + 1.96*se)) - 1) / (np.exp(2*(z + 1.96*se)) + 1)
    
    rho, _ = stats.spearmanr(h, m)
    z_s = 0.5 * np.log((1 + rho) / (1 - rho))
    rho_lower = (np.exp(2*(z_s - 1.96*se)) - 1) / (np.exp(2*(z_s - 1.96*se)) + 1)
    rho_upper = (np.exp(2*(z_s + 1.96*se)) - 1) / (np.exp(2*(z_s + 1.96*se)) + 1)
    
    return {
        'r': r, 'r_ci': (r_lower, r_upper),
        'rho': rho, 'rho_ci': (rho_lower, rho_upper),
        'n': n
    }

def calc_bland_altman(h, m):
    """Calculate Bland-Altman statistics."""
    h, m = np.array(h), np.array(m)
    mean = (h + m) / 2
    diff = h - m
    bias = np.mean(diff)
    sd = np.std(diff, ddof=1)
    return {
        'mean': mean, 'diff': diff, 'bias': bias, 'sd': sd,
        'loa_upper': bias + 1.96 * sd,
        'loa_lower': bias - 1.96 * sd
    }

# ============================================================================
# Main Figure Generation
# ============================================================================

def generate_combined_figure():
    """Generate the combined alignment figure."""
    print("Loading data...")
    human_scores, machine_scores = load_data(INPUT_FILE)
    print(f"Loaded {len(human_scores)} records")
    
    # Calculate statistics
    print("Calculating statistics...")
    all_stats = {}
    for metric in ['completeness', 'correctness', 'effectiveness', 'total']:
        all_stats[metric] = calc_correlation_stats(
            [s[metric] for s in human_scores],
            [s[metric] for s in machine_scores]
        )
    
    h_total = np.array([s['total'] for s in human_scores])
    m_total = np.array([s['total'] for s in machine_scores])
    ba_total = calc_bland_altman(h_total, m_total)
    
    # Filter outliers for Bland-Altman (beyond 3 SD)
    diff = ba_total['diff']
    mean_vals = ba_total['mean']
    mask = np.abs(diff - ba_total['bias']) < 3 * ba_total['sd']
    filtered_mean = mean_vals[mask]
    filtered_diff = diff[mask]
    print(f"Filtered {len(diff) - len(filtered_diff)} outliers from Bland-Altman")
    
    # ========================================================================
    # Create Figure
    # ========================================================================
    
    print("Generating figure (600 DPI)...")
    fig = plt.figure(figsize=(9.0, 4.0))
    
    ax1 = fig.add_axes([0.10, 0.18, 0.38, 0.68])
    ax2 = fig.add_axes([0.58, 0.18, 0.38, 0.68])
    
    # ========================================================================
    # (a) Grouped Bar Chart - Full Names
    # ========================================================================
    
    # Full names instead of abbreviations
    metrics_names = ['Completeness', 'Correctness', 'Effectiveness', 'Total']
    x = np.arange(len(metrics_names))
    width = 0.28
    
    pearson_r = [all_stats[m]['r'] for m in ['completeness', 'correctness', 'effectiveness', 'total']]
    pearson_err = [[r - all_stats[m]['r_ci'][0], all_stats[m]['r_ci'][1] - r] 
                   for r, m in zip(pearson_r, ['completeness', 'correctness', 'effectiveness', 'total'])]
    
    bars1 = ax1.bar(x - width/2, pearson_r, width, color=COLORS['pearson'], 
                    edgecolor='black', linewidth=0.6, label='Pearson r',
                    yerr=[[e[0] for e in pearson_err], [e[1] for e in pearson_err]], 
                    capsize=3, error_kw={'linewidth': 0.8})
    
    spearman_rho = [all_stats[m]['rho'] for m in ['completeness', 'correctness', 'effectiveness', 'total']]
    spearman_err = [[rho - all_stats[m]['rho_ci'][0], all_stats[m]['rho_ci'][1] - rho] 
                    for rho, m in zip(spearman_rho, ['completeness', 'correctness', 'effectiveness', 'total'])]
    
    bars2 = ax1.bar(x + width/2, spearman_rho, width, color=COLORS['spearman'], 
                    edgecolor='black', linewidth=0.6, label='Spearman rho',
                    yerr=[[e[0] for e in spearman_err], [e[1] for e in spearman_err]], 
                    capsize=3, error_kw={'linewidth': 0.8})
    
    # Reference line at 0.80
    ax1.axhline(y=0.80, color='gray', linestyle='--', linewidth=1.0, alpha=0.6)
    
    ax1.set_ylabel('Correlation Coefficient')
    ax1.set_xticks(x)
    ax1.set_xticklabels(metrics_names, fontsize=8)  # Smaller font for longer names
    ax1.set_ylim([0, 1.12])
    ax1.legend(loc='upper left', framealpha=0.9, edgecolor='gray', fontsize=8)
    ax1.grid(True, alpha=0.3, axis='y', linewidth=0.5)
    
    # Add xlabel for (a)
    ax1.set_xlabel('Evaluation Metrics', fontsize=10)
    
    # Value labels
    for i, bar in enumerate(bars1):
        height = bar.get_height()
        err_upper = pearson_err[i][1]
        ax1.text(bar.get_x() + bar.get_width()/2, height + err_upper + 0.02, f'{height:.2f}',
                 ha='center', va='bottom', fontsize=8, fontweight='bold', color=COLORS['pearson'])
    
    for i, bar in enumerate(bars2):
        height = bar.get_height()
        err_upper = spearman_err[i][1]
        ax1.text(bar.get_x() + bar.get_width()/2, height + err_upper + 0.02, f'{height:.2f}',
                 ha='center', va='bottom', fontsize=8, fontweight='bold', color=COLORS['spearman'])
    
    # ========================================================================
    # (b) Bland-Altman Plot
    # ========================================================================
    
    ax2.scatter(filtered_mean, filtered_diff, s=10, c=COLORS['scatter'], 
                alpha=0.35, edgecolors='none', zorder=2)
    
    ax2.axhline(y=ba_total['bias'], color=COLORS['bias'], linewidth=1.5, 
                linestyle='-', zorder=3)
    ax2.axhline(y=ba_total['loa_upper'], color=COLORS['loa'], linewidth=1.0, 
                linestyle='--', zorder=3)
    ax2.axhline(y=ba_total['loa_lower'], color=COLORS['loa'], linewidth=1.0, 
                linestyle='--', zorder=3)
    ax2.axhline(y=0, color='black', linewidth=0.5, linestyle='-', alpha=0.5, zorder=1)
    
    # Extended y-axis limits
    y_min = min(filtered_diff.min(), ba_total['loa_lower']) - 2
    y_max = max(filtered_diff.max(), ba_total['loa_upper']) + 2
    ax2.set_ylim([y_min, y_max])
    
    legend_elements = [
        Line2D([0], [0], color=COLORS['bias'], linewidth=1.5, linestyle='-', 
               label=f'Bias = {ba_total["bias"]:.2f}'),
        Line2D([0], [0], color=COLORS['loa'], linewidth=1.0, linestyle='--', 
               label=f'LoA [{ba_total["loa_lower"]:.2f}, {ba_total["loa_upper"]:.2f}]')
    ]
    ax2.legend(handles=legend_elements, loc='upper left', fontsize=8, 
               framealpha=0.9, edgecolor='gray')
    
    ax2.set_xlabel('Mean of Human and Automated Scores')
    ax2.set_ylabel('Difference (Human - Automated)')
    ax2.grid(True, alpha=0.3, linewidth=0.5, zorder=0)
    
    # ========================================================================
    # Save
    # ========================================================================
    
    print(f"Saving to {OUTPUT_PNG} (600 DPI)...")
    plt.savefig(OUTPUT_PNG, bbox_inches='tight', facecolor='white', edgecolor='none', dpi=600)
    
    
    # Print statistics
    print("\n" + "=" * 70)
    print("Statistics Summary")
    print("=" * 70)
    print(f"\n{'Metric':<12} {'Pearson r':<12} {'Spearman rho':<12}")
    print("-" * 70)
    for m in ['completeness', 'correctness', 'effectiveness', 'total']:
        print(f"{m.capitalize():<12} {all_stats[m]['r']:.3f}        {all_stats[m]['rho']:.3f}")
    print("-" * 70)
    print(f"\nBland-Altman (Total): Bias = {ba_total['bias']:.2f}, LoA = [{ba_total['loa_lower']:.2f}, {ba_total['loa_upper']:.2f}]")
    
    print("\n" + "=" * 70)
    print("Figure generation complete!")
    print(f"  PNG: {OUTPUT_PNG} (600 DPI)")

if __name__ == '__main__':
    generate_combined_figure()
