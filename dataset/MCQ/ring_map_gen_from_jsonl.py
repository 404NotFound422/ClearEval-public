import matplotlib.pyplot as plt
import numpy as np
import json
import io
from collections import Counter, defaultdict
import textwrap
import os

# Resolve the data file relative to this script so the repo runs anywhere.
FILE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'final', 'development.jsonl')

# --- 1. Define the Classification Schema ---
classification_schema = {
    "Tissue & Markers": {
        "Tissue Characteristics & Targets": {
            "Tissue & Target": ["Tissue Name", "Target Name"],
            "Tissue Types & Properties": ["Tissue Types and Properties"]
        },
        "Marker Characteristics & Targets": {
            "Markers & Targets": ["specific labeling object (antibody marker)", "specific labeling object"],
            "Marker Characteristics": ["Marker Feature"]
        }
    },
    "Reagents": {
        "Reagent Names & Abbreviations": {
            "Reagent Name Recognition & Association": ["Reagent Name"],
            "Reagent Abbreviation Recognition & Association": ["Reagent Common Name"]
        },
        "Reagent Function & Application": {
            "Reagent Function & Application": ["Reagent Function & Application"],
            "Mechanism of Action": ["Mechanism of Action"]
        }
    },
    "Clearing Methods": {
        "Method Name & Classification": {
            "Method Name & Classification": ["Clearing Method Name", "Method Classification"]
        },
        "Method Key Steps & Parameters": {
            "Method Detail Identification": ["Method Detail Extraction", "Specific Steps Identification"]
        },
        "Method Characteristics & Application": {
            "Method Characteristics: Overall Performance": ["Method Feature"],
            "Method Characteristics: Fluorescence Compatibility": ["Method Feature[Fluorescence_Compatibility]"],
            "Method Characteristics: Time Consumption": ["Method Feature[Time_Consumption]"],
            "Method Characteristics: Tissue Deformation": ["Method Feature[Tissue_Deformation]"],
            "Method Strengths, Weaknesses, & Improvements": ["Method Advantages & Limitations", "Improvements of Method"],
            "Cross-Method Comparison": ["Cross-Method Comparison"]
        },
        "Experimental & Protocol Design": {
            "Protocol Design & Selection": ["Protocol Selection", "Experimental Design"]
        },
        "Result Analysis & Optimization": {
            "Result Analysis & Optimization": ["Result Analysis and Optimization"]
        }
    }
}

# --- 2. Create Classification Map and Abbreviations ---
knowledge_point_map = {}
for l1_key, l1_value in classification_schema.items():
    for l2_key, l2_value in l1_value.items():
        for l3_key, kp_list in l2_value.items():
            for kp in kp_list:
                knowledge_point_map[kp] = {'l1': l1_key, 'l2': l2_key}

l2_abbreviations = {
    "Tissue Characteristics & Targets": "Tissue Char.\n& Targets",
    "Marker Characteristics & Targets": "Marker \n Char.& Targets",
    "Reagent Names & Abbreviations": "Reagent \nNames & Abbr.",
    "Reagent Function & Application": "Reagent \nFunc.& App.",
    "Method Name & Classification": "Method \nName& Class.",
    "Method Key Steps & Parameters": "Method \nSteps & Params.",
    "Method Characteristics & Application": "Method \nChar.& App.",
    "Experimental & Protocol Design": "Exp. & Protocol\nDesign",
    "Result Analysis & Optimization": "Result \nAnalysis& Opt.",
    "Unclassified": "Unclassified"
}

# --- 3. Load Data ---
all_questions = []

jsonl_file_path = FILE_PATH
with open(jsonl_file_path, 'r', encoding='utf-8') as f:
    for line in f:
        line = line.strip()
        if line:
            all_questions.append(json.loads(line))

# --- 4. Aggregate Data ---
l1_counts = Counter()
l2_counts = Counter()
for q in all_questions:
    kp = q.get('knowledge_point', 'N/A')
    if kp in knowledge_point_map:
        path = knowledge_point_map[kp]
        l1_counts[path['l1']] += 1
        l2_counts[(path['l1'], path['l2'])] += 1
    else:
        l1_counts['Unclassified'] += 1
        l2_counts[('Unclassified', 'Unclassified')] += 1

# --- 5. Prepare Plotting Data ---
l1_order = sorted(l1_counts.keys())
l1_labels_with_counts = [f"{name}\n({l1_counts[name]})" for name in l1_order]
l1_sizes = [l1_counts[name] for name in l1_order]

l2_path_order = []
for l1_cat in l1_order:
    sub_cats = sorted([path for path in l2_counts if path[0] == l1_cat], key=lambda x: x[1])
    l2_path_order.extend(sub_cats)

l2_labels = [path[1] for path in l2_path_order]
l2_sizes = [l2_counts[path] for path in l2_path_order]
total_questions = sum(l1_sizes)

# --- 6. Plotting ---
fig, ax = plt.subplots(figsize=(18, 18))
ax.axis('equal')
plt.rcParams['font.sans-serif'] = ['DejaVu Sans']

# Colors
l1_colors_map = {'Tissue & Markers': '#577590', 'Reagents': '#f8961e', 'Clearing Methods': '#90be6d', 'Unclassified': '#f94144'}
l1_colors = [l1_colors_map.get(key, '#808080') for key in l1_order]
l2_colors = []
color_maps = {'#577590': 'Blues', '#f8961e': 'Oranges', '#90be6d': 'Greens', '#f94144': 'Reds'}
paths_by_l1 = defaultdict(list)
for path in l2_path_order:
    paths_by_l1[path[0]].append(path)
for l1_cat in l1_order:
    num_subgroups = len(paths_by_l1[l1_cat])
    base_color = l1_colors_map.get(l1_cat, '#808080')
    cmap_name = color_maps.get(base_color)
    if cmap_name:
        cmap = plt.get_cmap(cmap_name)
        l2_colors.extend(cmap(np.linspace(0.7, 0.3, num_subgroups)))
    else:
        l2_colors.extend(['#C0C0C0'] * num_subgroups)

# Plot L2 (Outer Ring) - No autopct, we will add custom labels
wedges_l2, _ = ax.pie(l2_sizes,
                      radius=1.3,
                      colors=l2_colors,
                      wedgeprops=dict(width=0.4, edgecolor='w'))

# Plot L1 (Inner Ring)
wedges_l1, _ = ax.pie(l1_sizes,
                      radius=1.3 - 0.4,
                      colors=l1_colors,
                      wedgeprops=dict(width=0.5, edgecolor='w'))

# --- 7. Add Labels ---
# L1 Labels (Inside Inner Ring)
for i, p in enumerate(wedges_l1):
    ang = (p.theta2 - p.theta1) / 2. + p.theta1
    y = np.sin(np.deg2rad(ang))
    x = np.cos(np.deg2rad(ang))
    ax.text(0.6 * x, 0.6 * y, l1_labels_with_counts[i],
            ha='center', va='center', fontsize=20, weight='bold', color='black')

# L2 Labels (Inside Outer Ring)
radius = 1.3 - 0.4 / 2
for i, p in enumerate(wedges_l2):
    ang = (p.theta2 - p.theta1) / 2. + p.theta1
    y = radius * np.sin(np.deg2rad(ang))
    x = radius * np.cos(np.deg2rad(ang))
    
    # Get abbreviation and percentage
    original_label = l2_labels[i]
    abbreviation = l2_abbreviations.get(original_label, original_label)
    percentage = l2_sizes[i] / total_questions * 100
    label_text = f"{abbreviation}\n({percentage:.1f}%)"
    
    # Intelligent rotation for readability
    rotation = ang
    if 90 < ang < 270:
        rotation -= 180
        
    ax.text(x, y, label_text, ha='center', va='center', fontsize=15, weight='bold', color='black', rotation=rotation, rotation_mode='anchor')

# --- 8. Center Text and Title ---
ax.text(0, 0, f'Total\n{total_questions} Questions', ha='center', va='center', fontsize=28, weight='bold')
plt.title('Distribution of Q&A Pairs by Knowledge Point', fontsize=32, weight='bold', pad=40)

# --- 9. Save Figure ---
output_filename = 'knowledge_point_donut_chart_internal_labels.png'
plt.savefig(output_filename, bbox_inches='tight', dpi=300)

print(f"Donut chart with internal labels has been generated and saved as {output_filename}")
