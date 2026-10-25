"""Grafik evaluasi (PNG statis untuk laporan). Angka lengkap selalu tersedia di CSV, grafik hanya ringkasan visual.

Palet: urutan kategorikal tetap (tervalidasi untuk buta warna pada latar terang). Tiga warna di bawah kontras 3:1,
jadi setiap garis juga dibedakan dengan gaya garis dan diberi label langsung di ujungnya.
"""

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e4e3df"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300")
LINESTYLES = ("-", "--", "-.", ":", (0, (5, 1)), (0, (3, 1, 1, 1)))
BLUES = LinearSegmentedColormap.from_list("blues", ["#f0f5fc", "#9ec5f4", "#3987e5", "#1c5cab", "#0d366b"])


def _style(ax) -> None:
    ax.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(INK_2)
    ax.tick_params(colors=INK_2, labelsize=9)
    ax.grid(color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)


def _figure(w: float, h: float):
    fig, ax = plt.subplots(figsize=(w, h), dpi=130)
    fig.patch.set_facecolor(SURFACE)
    _style(ax)
    return fig, ax


def confusion_matrix_plot(cm: list[list[int]], classes: list[str], title: str, out: Path) -> None:
    cm = np.asarray(cm)
    row = cm.sum(axis=1, keepdims=True)
    frac = np.divide(cm, row, out=np.zeros_like(cm, dtype=float), where=row > 0)
    fig, ax = _figure(5.6, 4.8)
    ax.grid(False)
    ax.imshow(frac, cmap=BLUES, vmin=0, vmax=1)
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            ax.text(j, i, f"{cm[i, j]}\n{frac[i, j]:.0%}", ha="center", va="center", fontsize=8,
                    color="#ffffff" if frac[i, j] > 0.55 else INK)
    ax.set_xticks(range(len(classes)), classes, rotation=30, ha="right")
    ax.set_yticks(range(len(classes)), classes)
    ax.set_xlabel("Prediksi", color=INK_2)
    ax.set_ylabel("Label sebenarnya", color=INK_2)
    ax.set_title(f"{title}\n(angka: jumlah dan porsi per baris)", fontsize=10, color=INK, loc="left")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


def reliability_plot(bins: list[dict], ece: float, title: str, out: Path) -> None:
    fig, ax = _figure(5.0, 4.4)
    filled = [b for b in bins if b["n"]]
    centers = [(b["lo"] + b["hi"]) / 2 for b in filled]
    width = (bins[0]["hi"] - bins[0]["lo"]) * 0.9
    ax.bar(centers, [b["accuracy"] for b in filled], width=width, color=SERIES[0], edgecolor=SURFACE, linewidth=2,
           label="Akurasi per bin")
    ax.plot([0, 1], [0, 1], color=INK_2, linestyle="--", linewidth=1.5, label="Kalibrasi sempurna")
    ax.plot(centers, [b["confidence"] for b in filled], "o", color=SERIES[1], markersize=5, label="Rata-rata keyakinan")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Keyakinan (probabilitas maksimum)", color=INK_2)
    ax.set_ylabel("Akurasi", color=INK_2)
    ax.set_title(f"{title}\nECE = {ece:.3f}", fontsize=10, color=INK, loc="left")
    ax.legend(frameon=False, fontsize=8, loc="upper left")
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)


def risk_coverage_plot(curves: dict[str, tuple[np.ndarray, np.ndarray]], operating: dict[str, tuple[float, float]],
                       title: str, out: Path) -> None:
    """curves: nama -> (cakupan, akurasi). operating: nama -> (cakupan, akurasi) di ambang terpilih."""
    fig, ax = _figure(7.6, 4.4)
    ends = []
    for k, (name, (cov, acc)) in enumerate(curves.items()):
        color, ls = SERIES[k % len(SERIES)], LINESTYLES[k % len(LINESTYLES)]
        ax.plot(cov, acc, color=color, linestyle=ls, linewidth=2, label=name)
        ends.append([float(acc[-1]), name])
        if name in operating:
            ax.plot(*operating[name], "o", color=color, markersize=8, markeredgecolor=SURFACE, markeredgewidth=2)
    # Label langsung di ujung kanan, digeser vertikal agar tidak saling menimpa (jarak minimum 0,05).
    ends.sort()
    for i in range(1, len(ends)):
        ends[i][0] = max(ends[i][0], ends[i - 1][0] + 0.05)
    for y, name in ends:
        ax.annotate(name, (1.0, y), xytext=(6, 0), textcoords="offset points", fontsize=8, color=INK_2, va="center")
    ax.set_xlim(0, 1.0)
    ax.set_ylim(0, 1)
    ax.set_xlabel("Cakupan (porsi prediksi yang tidak berstatus 'belum pasti')", color=INK_2)
    ax.set_ylabel("Akurasi prediksi yang diterima", color=INK_2)
    ax.set_title(f"{title}\n(titik = ambang terpilih di validasi)", fontsize=10, color=INK, loc="left")
    ax.legend(frameon=False, fontsize=8, loc="upper left", bbox_to_anchor=(1.22, 1.0))
    fig.tight_layout()
    out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out, facecolor=SURFACE)
    plt.close(fig)
