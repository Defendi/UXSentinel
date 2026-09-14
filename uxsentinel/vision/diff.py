"""Módulo de Diferenciação Visual Perceptual e Pixel-a-Pixel para Baselines Visuais."""

from __future__ import annotations

import collections
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageChops, ImageDraw

from uxsentinel.core.models import BoundingBox, VisualDiffResult

if TYPE_CHECKING:
    pass

# Cor padrão de alto contraste para destacar pixels modificados (magenta/vermelho #E11D48)
DIFF_HIGHLIGHT_COLOR = (225, 29, 72)  # #E11D48
DIFF_HIGHLIGHT_RGBA = (225, 29, 72, 230)


def _find_connected_component_boxes(
    mask_grid: dict[tuple[int, int], bool],
    block_size: int,
    max_w: int,
    max_h: int,
) -> list[BoundingBox]:
    """Agrupa blocos ativos adjacentes (8-conectividade) em retângulos delimitadores (BoundingBox)."""
    visited: set[tuple[int, int]] = set()
    boxes: list[BoundingBox] = []

    active_blocks = [pos for pos, active in mask_grid.items() if active]

    for start_pos in active_blocks:
        if start_pos in visited:
            continue

        queue = collections.deque([start_pos])
        visited.add(start_pos)
        component_blocks = [start_pos]

        while queue:
            cx, cy = queue.popleft()
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    if dx == 0 and dy == 0:
                        continue
                    neighbor = (cx + dx, cy + dy)
                    if neighbor in mask_grid and mask_grid[neighbor] and neighbor not in visited:
                        visited.add(neighbor)
                        queue.append(neighbor)
                        component_blocks.append(neighbor)

        min_gx = min(bx for bx, by in component_blocks)
        max_gx = max(bx for bx, by in component_blocks)
        min_gy = min(by for bx, by in component_blocks)
        max_gy = max(by for bx, by in component_blocks)

        x = min_gx * block_size
        y = min_gy * block_size
        width = min(max_w, (max_gx + 1) * block_size) - x
        height = min(max_h, (max_gy + 1) * block_size) - y

        boxes.append(BoundingBox(x=x, y=y, width=width, height=height))

    # Ordena por coordenadas para determinismo
    boxes.sort(key=lambda b: (b.y, b.x))
    return boxes


def compute_bounding_boxes(
    diff_mask: Image.Image,
    block_size: int = 24,
) -> list[BoundingBox]:
    """Segmenta a máscara de diferenças em blocos e gera caixas delimitadoras consolidadas."""
    width, height = diff_mask.size
    cols = (width + block_size - 1) // block_size
    rows = (height + block_size - 1) // block_size

    mask_pixels = diff_mask.load()
    mask_grid: dict[tuple[int, int], bool] = {}

    for by in range(rows):
        for bx in range(cols):
            x_start = bx * block_size
            y_start = by * block_size
            x_end = min(width, x_start + block_size)
            y_end = min(height, y_start + block_size)

            has_diff = False
            for y in range(y_start, y_end):
                for x in range(x_start, x_end):
                    val = mask_pixels[x, y]
                    # Modo 'L' ou '1': valor > 0 indica diferença
                    if (isinstance(val, int) and val > 0) or (isinstance(val, tuple) and val[0] > 0):
                        has_diff = True
                        break
                if has_diff:
                    break

            if has_diff:
                mask_grid[(bx, by)] = True

    if not mask_grid:
        return []

    return _find_connected_component_boxes(mask_grid, block_size, width, height)


def create_diff_image(
    current_image: Image.Image,
    diff_mask: Image.Image,
    bounding_boxes: list[BoundingBox] | None = None,
) -> Image.Image:
    """Gera imagem visual de diff destacando pixels alterados em cor de alto contraste (#E11D48).

    - A imagem atual é esmaecida em tons de cinza com baixa saturação.
    - Os pixels com alteração são destacados com a cor de alto contraste #E11D48 semi-transparente.
    - As bounding boxes de regiões modificadas recebem uma borda suave de realce.
    """
    width, height = current_image.size

    # Cria base atenuada: converte imagem atual para tons de cinza e clareia para dar contraste ao diff
    gray_curr = current_image.convert("L").convert("RGBA")
    attenuated_base = Image.blend(
        gray_curr, Image.new("RGBA", (width, height), (255, 255, 255, 255)), alpha=0.35
    )

    # Imagem sólida na cor de destaque #E11D48
    highlight_layer = Image.new("RGBA", (width, height), DIFF_HIGHLIGHT_RGBA)

    # Máscara binária em modo 'L' para composição suave
    mask_l = diff_mask.convert("L")

    # Mescla: onde houver diferença, aplica o destaque #E11D48; onde não houver, mantém a imagem de fundo atenuada
    diff_image = Image.composite(highlight_layer, attenuated_base, mask_l)

    # Adiciona borda visual sutil nas bounding boxes se houver diferenças
    if bounding_boxes:
        draw = ImageDraw.Draw(diff_image)
        for box in bounding_boxes:
            draw.rectangle(
                [box.x, box.y, box.x + box.width, box.y + box.height],
                outline=(225, 29, 72, 255),
                width=2,
            )

    return diff_image


def compare_images(
    baseline_path: str | Path,
    current_path: str | Path,
    diff_output_path: str | Path | None = None,
    threshold: float = 0.1,
    pixel_tolerance: int = 10,
    block_size: int = 24,
) -> VisualDiffResult:
    """Compara imagem de referência (baseline) contra a captura atual pixel-a-pixel.

    Args:
        baseline_path: Caminho da imagem de referência homologada.
        current_path: Caminho da imagem atual capturada no teste.
        diff_output_path: Caminho onde a imagem de diff gerada será salva (opcional).
        threshold: Limiar percentual de tolerância para alertar divergência visual (default 0.1%).
        pixel_tolerance: Tolerância perceptual de variação por pixel (0-255) para atenuar ruído de anti-aliasing.
        block_size: Tamanho do bloco para consolidação de bounding boxes.

    Returns:
        VisualDiffResult com métricas completas de divergência e bounding boxes.
    """
    baseline_p = Path(baseline_path)
    current_p = Path(current_path)

    if not baseline_p.is_file():
        raise FileNotFoundError(f"Imagem de baseline não encontrada: {baseline_path}")
    if not current_p.is_file():
        raise FileNotFoundError(f"Imagem atual não encontrada: {current_path}")

    with Image.open(baseline_p) as raw_base, Image.open(current_p) as raw_curr:
        img_base = raw_base.convert("RGBA")
        img_curr = raw_curr.convert("RGBA")

    # Se as resoluções forem diferentes, unifica no tamanho máximo de canvas para não perder pixels
    target_w = max(img_base.width, img_curr.width)
    target_h = max(img_base.height, img_curr.height)

    if img_base.size != (target_w, target_h):
        unified_base = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        unified_base.paste(img_base, (0, 0))
    else:
        unified_base = img_base

    if img_curr.size != (target_w, target_h):
        unified_curr = Image.new("RGBA", (target_w, target_h), (0, 0, 0, 0))
        unified_curr.paste(img_curr, (0, 0))
    else:
        unified_curr = img_curr

    # Diferença pixel-a-pixel entre imagens
    diff_raw = ImageChops.difference(unified_base, unified_curr)

    # Converte diferença para tons de cinza
    diff_gray = diff_raw.convert("L")

    # Aplica tolerância perceptual para ignorar micro-oscilações de anti-aliasing de fontes
    # Pixels com valor acima de pixel_tolerance são marcados como 255 (diferentes)
    diff_mask = diff_gray.point(lambda p: 255 if p > pixel_tolerance else 0, mode="L")

    # Conta pixels diferentes
    histogram = diff_mask.histogram()
    diff_pixels = histogram[255] if len(histogram) > 255 else 0
    total_pixels = target_w * target_h
    diff_percentage = round((diff_pixels / total_pixels) * 100.0, 4) if total_pixels > 0 else 0.0

    has_diff = diff_percentage > threshold

    bounding_boxes: list[BoundingBox] = []
    diff_img_saved_path: str | None = None

    if diff_pixels > 0:
        bounding_boxes = compute_bounding_boxes(diff_mask, block_size=block_size)

    # Gera a imagem de diff sempre que diff_output_path for solicitado ou se houver diff
    if diff_output_path:
        out_p = Path(diff_output_path)
        out_p.parent.mkdir(parents=True, exist_ok=True)
        diff_img = create_diff_image(unified_curr, diff_mask, bounding_boxes)
        diff_img.save(str(out_p), "PNG")
        diff_img_saved_path = str(out_p)

    return VisualDiffResult(
        baseline_path=str(baseline_p),
        current_path=str(current_p),
        diff_image_path=diff_img_saved_path,
        diff_percentage=diff_percentage,
        has_diff=has_diff,
        threshold=threshold,
        bounding_boxes=bounding_boxes,
        total_pixels=total_pixels,
        diff_pixels=diff_pixels,
    )
