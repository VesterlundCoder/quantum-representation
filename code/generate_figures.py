#!/usr/bin/env python3
"""Generate the headline figure: variance decomposition across qubit sizes."""
import warnings
warnings.filterwarnings("ignore")
import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

with open("/tmp/scale_observations_v2.json") as f:
    data = json.load(f)
df = pd.DataFrame(data["observations"])

# Compute variance decomposition at each scale
results = []
for n in sorted(df["n_qubits"].unique()):
    df_n = df[(df["n_qubits"] == n) & (df["depth"] > 0)]
    algo_means = df_n.groupby("algorithm")["depth"].mean()
    fw_means = df_n.groupby("framework")["depth"].mean()
    grand = df_n["depth"].mean()
    ss_total = ((df_n["depth"] - grand) ** 2).sum()
    ss_algo = sum(len(df_n[df_n["algorithm"] == a]) * (algo_means[a] - grand) ** 2 for a in df_n["algorithm"].unique())
    ss_fw = sum(len(df_n[df_n["framework"] == f]) * (fw_means[f] - grand) ** 2 for f in df_n["framework"].unique())
    ss_int = 0
    for a in df_n["algorithm"].unique():
        for f in df_n["framework"].unique():
            cell = df_n[(df_n["algorithm"] == a) & (df_n["framework"] == f)]
            if len(cell) > 0:
                ss_int += len(cell) * (cell["depth"].mean() - algo_means[a] - fw_means[f] + grand) ** 2
    ss_res = max(0, ss_total - ss_algo - ss_fw - ss_int)
    results.append({
        "n": n,
        "algorithm": ss_algo / ss_total * 100,
        "framework": ss_fw / ss_total * 100,
        "interaction": ss_int / ss_total * 100,
        "residual": ss_res / ss_total * 100,
    })

# Figure 1: Stacked bar chart of variance decomposition
fig, ax = plt.subplots(figsize=(8, 5))
n_sizes = [r["n"] for r in results]
algo_vals = [r["algorithm"] for r in results]
fw_vals = [r["framework"] for r in results]
int_vals = [r["interaction"] for r in results]
res_vals = [r["residual"] for r in results]

x = np.arange(len(n_sizes))
width = 0.55

bars1 = ax.bar(x, algo_vals, width, label=r"$\eta^2$(algorithm)", color="#2196F3", edgecolor="white", linewidth=0.5)
bars2 = ax.bar(x, fw_vals, width, bottom=algo_vals, label=r"$\eta^2$(framework)", color="#4CAF50", edgecolor="white", linewidth=0.5)
bottom2 = [a + f for a, f in zip(algo_vals, fw_vals)]
bars3 = ax.bar(x, int_vals, width, bottom=bottom2, label=r"$\eta^2$(interaction)", color="#FF9800", edgecolor="white", linewidth=0.5)
bottom3 = [b + i for b, i in zip(bottom2, int_vals)]
bars4 = ax.bar(x, res_vals, width, bottom=bottom3, label=r"$\eta^2$(config/residual)", color="#9E9E9E", edgecolor="white", linewidth=0.5)

# Add interaction labels on bars
for i, (bar, val) in enumerate(zip(bars3, int_vals)):
    ax.text(bar.get_x() + bar.get_width() / 2, bottom2[i] + val / 2,
            f"{val:.0f}%", ha="center", va="center", fontsize=9, fontweight="bold", color="white")

ax.set_xlabel("Number of qubits", fontsize=12)
ax.set_ylabel(r"Variance explained ($\eta^2$, %)", fontsize=12)
ax.set_title("Variance Decomposition of Circuit Depth Across Qubit Sizes", fontsize=13, fontweight="bold")
ax.set_xticks(x)
ax.set_xticklabels([f"{n}q" for n in n_sizes], fontsize=11)
ax.set_ylim(0, 105)
ax.legend(loc="upper right", fontsize=10, framealpha=0.9)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

plt.tight_layout()
plt.savefig("/tmp/fig1_variance_decomposition.png", dpi=300, bbox_inches="tight")
plt.close()
print("Saved fig1_variance_decomposition.png")

# Figure 2: Best depth per framework at 12 qubits (log scale)
fig, ax = plt.subplots(figsize=(9, 5))
df_12 = df[df["n_qubits"] == 12]
algorithms = sorted(df_12["algorithm"].unique())
frameworks = ["pennylane", "pytket", "qiskit", "cirq"]
colors = {"pennylane": "#2196F3", "pytket": "#4CAF50", "qiskit": "#FF9800", "cirq": "#9E9E9E"}
fw_labels = {"pennylane": "PennyLane", "pytket": "PyTKET", "qiskit": "Qiskit", "cirq": "Cirq"}

x = np.arange(len(algorithms))
width = 0.18
for i, fw in enumerate(frameworks):
    vals = []
    for algo in algorithms:
        cell = df_12[(df_12["algorithm"] == algo) & (df_12["framework"] == fw) & (df_12["depth"] > 0)]
        vals.append(cell["depth"].min() if len(cell) > 0 else 0)
    bars = ax.bar(x + i * width, vals, width, label=fw_labels[fw], color=colors[fw], edgecolor="white", linewidth=0.5)

ax.set_xlabel("Algorithm", fontsize=12)
ax.set_ylabel("Best circuit depth (log scale)", fontsize=12)
ax.set_title("Best Achievable Depth per Framework at 12 Qubits", fontsize=13, fontweight="bold")
ax.set_xticks(x + width * 1.5)
ax.set_xticklabels(algorithms, fontsize=11)
ax.set_yscale("log")
ax.legend(loc="upper left", fontsize=10, framealpha=0.9)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

plt.tight_layout()
plt.savefig("/tmp/fig2_best_depth_12q.png", dpi=300, bbox_inches="tight")
plt.close()
print("Saved fig2_best_depth_12q.png")

# Figure 3: Within-framework config variance growth
fig, ax = plt.subplots(figsize=(8, 5))
frameworks_wf = ["pytket", "qiskit", "pennylane", "cirq"]
colors_wf = {"pytket": "#4CAF50", "qiskit": "#FF9800", "pennylane": "#2196F3", "cirq": "#9E9E9E"}
labels_wf = {"pytket": "PyTKET", "qiskit": "Qiskit", "pennylane": "PennyLane", "cirq": "Cirq"}

for fw in frameworks_wf:
    vals = []
    for n in sorted(df["n_qubits"].unique()):
        d = df[(df["n_qubits"] == n) & (df["framework"] == fw) & (df["depth"] > 0)]
        if len(d) < 10:
            vals.append(0)
            continue
        gm = d["depth"].mean()
        ss_t = ((d["depth"] - gm) ** 2).sum()
        am = d.groupby("algorithm")["depth"].mean()
        ss_a = sum(len(d[d["algorithm"] == a]) * (am[a] - gm) ** 2 for a in d["algorithm"].unique())
        ss_c = max(0, ss_t - ss_a)
        vals.append(ss_c / ss_t * 100)
    ax.plot([6, 8, 10, 12], vals, "o-", label=labels_wf[fw], color=colors_wf[fw], linewidth=2, markersize=7)

ax.set_xlabel("Number of qubits", fontsize=12)
ax.set_ylabel(r"Configuration variance ($\eta^2$, %)", fontsize=12)
ax.set_title("Within-Framework Configuration Variance Grows with Scale", fontsize=13, fontweight="bold")
ax.set_xticks([6, 8, 10, 12])
ax.legend(loc="upper left", fontsize=10, framealpha=0.9)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)
ax.grid(axis="y", alpha=0.3)

plt.tight_layout()
plt.savefig("/tmp/fig3_config_variance_growth.png", dpi=300, bbox_inches="tight")
plt.close()
print("Saved fig3_config_variance_growth.png")

# Figure 4: Search improvement distribution
fig, ax = plt.subplots(figsize=(8, 4.5))
improvements = []
for n in sorted(df["n_qubits"].unique()):
    df_n = df[df["n_qubits"] == n]
    for algo in sorted(df_n["algorithm"].unique()):
        for fw in sorted(df_n["framework"].unique()):
            cell = df_n[(df_n["algorithm"] == algo) & (df_n["framework"] == fw) & (df_n["depth"] > 0)]
            if len(cell) < 5:
                continue
            mean_d = cell["depth"].mean()
            best_d = cell["depth"].min()
            if mean_d > 0:
                improvements.append((1 - best_d / mean_d) * 100)

ax.hist(improvements, bins=20, color="#2196F3", edgecolor="white", linewidth=0.5, alpha=0.85)
ax.axvline(np.median(improvements), color="#FF9800", linewidth=2, linestyle="--", label=f"Median: {np.median(improvements):.0f}%")
ax.axvline(np.mean(improvements), color="#4CAF50", linewidth=2, linestyle="--", label=f"Mean: {np.mean(improvements):.0f}%")
ax.set_xlabel("Depth improvement (best vs. mean config, %)", fontsize=12)
ax.set_ylabel("Number of cells", fontsize=12)
ax.set_title("Distribution of Search Improvements Across All Cells", fontsize=13, fontweight="bold")
ax.legend(fontsize=10, framealpha=0.9)
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

plt.tight_layout()
plt.savefig("/tmp/fig4_search_improvement.png", dpi=300, bbox_inches="tight")
plt.close()
print("Saved fig4_search_improvement.png")

print("\nAll figures generated successfully.")
