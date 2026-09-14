"""Utilitário para manipulação de vídeo da sessão e geração de GIF animado."""

from __future__ import annotations

import contextlib
import logging
import shutil
import subprocess
from pathlib import Path

logger = logging.getLogger("uxsentinel.reporter.video_helper")


def is_ffmpeg_available() -> bool:
    """Verifica se o utilitário ffmpeg está instalado e disponível no PATH do sistema."""
    return shutil.which("ffmpeg") is not None


def convert_webm_to_mp4(
    webm_path: str | Path,
    output_path: str | Path | None = None,
    timeout_seconds: int = 60,
) -> Path | None:
    """Converte um arquivo de vídeo .webm para .mp4 usando ffmpeg (se disponível).

    Retorna o Path do arquivo .mp4 se a conversão for bem-sucedida, ou None em caso de falha.
    """
    src = Path(webm_path)
    if not src.is_file() or not is_ffmpeg_available():
        return None

    dest = Path(output_path) if output_path else src.with_suffix(".mp4")
    dest.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(dest),
    ]

    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        if res.returncode == 0 and dest.is_file():
            return dest
        logger.warning(
            "Falha na conversão para MP4 pelo ffmpeg: %s",
            res.stderr.decode("utf-8", errors="ignore")[:300],
        )
        return None
    except Exception as exc:
        logger.warning("Erro ao executar ffmpeg para conversão MP4: %s", exc)
        return None


def generate_gif_from_video(
    video_path: str | Path,
    output_gif: str | Path,
    fps: int = 10,
    width: int = 640,
    timeout_seconds: int = 60,
) -> Path | None:
    """Gera um GIF animado otimizado a partir de um arquivo de vídeo usando ffmpeg e paleta de duas fases."""
    src = Path(video_path)
    dest = Path(output_gif)
    if not src.is_file() or not is_ffmpeg_available():
        return None

    dest.parent.mkdir(parents=True, exist_ok=True)

    filter_complex = (
        f"fps={fps},scale={width}:-1:flags=lanczos,split[s0][s1];"
        "[s0]palettegen=max_colors=128[p];[s1][p]paletteuse=dither=bayer"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(src),
        "-vf",
        filter_complex,
        str(dest),
    ]

    try:
        res = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout_seconds,
            check=False,
        )
        if res.returncode == 0 and dest.is_file():
            return dest
        logger.warning(
            "Falha ao gerar GIF com ffmpeg: %s",
            res.stderr.decode("utf-8", errors="ignore")[:300],
        )
        return None
    except Exception as exc:
        logger.warning("Erro ao executar ffmpeg para gerar GIF: %s", exc)
        return None


def generate_gif_from_images(
    image_paths: list[str | Path],
    output_gif: str | Path,
    duration_ms: int = 1200,
    max_width: int = 800,
) -> Path | None:
    """Gera um GIF animado a partir de uma sequência de imagens/screenshots usando Pillow como fallback inteligente."""
    valid_paths = [Path(p) for p in image_paths if Path(p).is_file()]
    if not valid_paths:
        return None

    try:
        from PIL import Image
    except ImportError:
        logger.warning("Pillow não está disponível para gerar GIF animado a partir de imagens.")
        return None

    dest = Path(output_gif)
    dest.parent.mkdir(parents=True, exist_ok=True)

    loaded_images: list[Image.Image] = []
    try:
        for p in valid_paths:
            img = Image.open(p)
            if img.mode != "RGB":
                img = img.convert("RGB")

            # Redimensiona mantendo aspect ratio se ultrapassar max_width
            if img.width > max_width:
                aspect = img.height / img.width
                new_h = int(max_width * aspect)
                img = img.resize((max_width, new_h), Image.Resampling.LANCZOS)

            # Converte para paleta adaptativa de 128 cores para GIF leve
            p_img = img.convert("P", palette=Image.Palette.ADAPTIVE, colors=128)
            loaded_images.append(p_img)

        if not loaded_images:
            return None

        first_img = loaded_images[0]
        remaining = loaded_images[1:] if len(loaded_images) > 1 else []

        first_img.save(
            dest,
            save_all=True,
            append_images=remaining,
            duration=duration_ms,
            loop=0,
            optimize=True,
        )
        return dest if dest.is_file() else None

    except Exception as exc:
        logger.warning("Erro ao gerar GIF animado com Pillow: %s", exc)
        return None
    finally:
        for img in loaded_images:
            with contextlib.suppress(Exception):
                img.close()


def create_session_gif(
    video_path: str | Path | None = None,
    checkpoint_screenshots: list[str | Path] | None = None,
    output_gif: str | Path | None = None,
) -> Path | None:
    """Gera um GIF representativo da sessão.

    Estratégia:
    1. Se video_path for fornecido e ffmpeg estiver disponível, tenta gerar GIF direto do vídeo.
    2. Se não houver ffmpeg ou a conversão falhar, usa as screenshots dos checkpoints via Pillow.
    """
    if not output_gif:
        return None

    dest = Path(output_gif)

    # 1. Tenta ffmpeg via vídeo
    if video_path and Path(video_path).is_file() and is_ffmpeg_available():
        gif_res = generate_gif_from_video(video_path, dest)
        if gif_res and gif_res.is_file():
            return gif_res

    # 2. Fallback inteligente via Pillow e screenshots dos checkpoints
    if checkpoint_screenshots:
        gif_res = generate_gif_from_images(checkpoint_screenshots, dest)
        if gif_res and gif_res.is_file():
            return gif_res

    return None


def finalize_session_video(
    raw_video_path: str | Path,
    output_dir: str | Path,
    scenario_id: str,
    try_mp4_conversion: bool = False,
) -> Path:
    """Move e renomeia o arquivo temporário gerado pelo Playwright para um nome amigável no diretório de saída.

    Se try_mp4_conversion for True e ffmpeg estiver disponível, tenta converter para MP4 mantendo também
    o arquivo webm como backup.
    """
    raw = Path(raw_video_path)
    out_base = Path(output_dir)
    out_base.mkdir(parents=True, exist_ok=True)

    dest_webm = out_base / f"{scenario_id}_session.webm"

    # Se raw e dest_webm forem o mesmo arquivo, nada a mover
    if raw.resolve() != dest_webm.resolve():
        try:
            if dest_webm.exists():
                dest_webm.unlink()
            shutil.move(str(raw), str(dest_webm))
        except Exception:
            try:
                shutil.copy2(str(raw), str(dest_webm))
            except Exception as copy_err:
                logger.warning("Não foi possível mover/copiar o vídeo da sessão: %s", copy_err)
                return raw

    final_path = dest_webm
    if try_mp4_conversion and is_ffmpeg_available():
        dest_mp4 = out_base / f"{scenario_id}_session.mp4"
        mp4_res = convert_webm_to_mp4(dest_webm, dest_mp4)
        if mp4_res and mp4_res.is_file():
            final_path = mp4_res

    return final_path
