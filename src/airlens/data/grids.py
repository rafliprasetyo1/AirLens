"""Grid gambar untuk pemeriksaan visual (sampel duplikat, sampel yang ditolak, sampel yang lolos)."""

from pathlib import Path

from PIL import Image, ImageDraw

from airlens.data.quality import load_rgb

TILE = 160


def _tile(path: Path | None) -> Image.Image:
    try:
        img = load_rgb(path)
        img.thumbnail((TILE, TILE))
    except Exception:
        img = Image.new("RGB", (TILE, TILE), (90, 0, 0))
    canvas = Image.new("RGB", (TILE, TILE), (255, 255, 255))
    canvas.paste(img, ((TILE - img.width) // 2, (TILE - img.height) // 2))
    return canvas


def save_grid(items: list[tuple[Path, Path | None, str]], out: Path, pairs: bool = False, cols: int = 6) -> None:
    """items: (gambar, gambar_pasangan atau None, label). Pasangan digambar berdampingan."""
    if not items:
        return
    cell_w = TILE * (2 if pairs else 1)
    cols = max(1, cols // (2 if pairs else 1))
    rows = (len(items) + cols - 1) // cols
    grid = Image.new("RGB", (cols * cell_w, rows * (TILE + 16)), (255, 255, 255))
    draw = ImageDraw.Draw(grid)
    for i, (a, b, label) in enumerate(items):
        x, y = (i % cols) * cell_w, (i // cols) * (TILE + 16)
        grid.paste(_tile(a), (x, y))
        if pairs:
            grid.paste(_tile(b), (x + TILE, y))
        draw.text((x + 3, y + TILE + 2), str(label)[:40], fill=(0, 0, 0))
    out.parent.mkdir(parents=True, exist_ok=True)
    grid.save(out, quality=85)
