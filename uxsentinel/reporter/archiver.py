import logging
import os
import re
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


def _sanitize_filename(name: str) -> str:
    """Sanitiza um nome para ser usado de forma segura em arquivos."""
    clean = re.sub(r"[^\w\-.]", "_", name.strip())
    return clean or "cenario"


def archive_previous_reports(
    output_dir: str | Path,
    archive_dir: str | Path | None = None,
    label: str | None = None,
) -> Path | None:
    """Compacta e arquiva os arquivos da análise anterior existentes em `output_dir` em um arquivo .zip.

    Args:
        output_dir: Diretório de saída dos relatórios (ex: 'scenarios/report' ou 'report').
        archive_dir: Diretório de destino dos arquivos .zip (padrão: output_dir / 'archive').
        label: Identificador opcional (ex: scenario.id) para compor o nome do arquivo .zip.

    Returns:
        Path do arquivo .zip gerado, ou None se não houver arquivos a arquivar.
    """
    out_path = Path(output_dir).resolve()
    if not out_path.is_dir():
        return None

    arch_path = Path(archive_dir).resolve() if archive_dir else out_path / "archive"

    # Coleta todos os arquivos e pastas a serem arquivados
    files_to_archive: list[Path] = []
    dirs_to_archive: list[Path] = []

    for root, dirs, files in os.walk(out_path):
        root_path = Path(root).resolve()

        # Ignora o próprio diretório de arquivo e subpastas de archive
        if root_path == arch_path or root_path.is_relative_to(arch_path):
            continue

        for d in list(dirs):
            dir_full = root_path / d
            if dir_full == arch_path or dir_full.is_relative_to(arch_path) or d.startswith("."):
                dirs.remove(d)
                continue
            dirs_to_archive.append(dir_full)

        for f in files:
            file_full = root_path / f
            # Ignora arquivos ocultos, o diretório archive e arquivos .zip já existentes
            if f.startswith(".") or file_full.suffix.lower() == ".zip":
                continue
            if file_full.is_relative_to(arch_path):
                continue
            files_to_archive.append(file_full)

    # Se não houver nenhum arquivo de relatório anterior, nada a fazer
    if not files_to_archive:
        return None

    arch_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_label = _sanitize_filename(label) if label else "report"
    zip_filename = f"{timestamp}_{clean_label}_archive.zip"
    zip_target = arch_path / zip_filename

    # Garante que não haja colisão de nome de arquivo
    counter = 1
    while zip_target.exists():
        zip_filename = f"{timestamp}_{clean_label}_archive_{counter}.zip"
        zip_target = arch_path / zip_filename
        counter += 1

    temp_zip = zip_target.with_suffix(".tmp")

    try:
        with zipfile.ZipFile(temp_zip, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
            for file_path in files_to_archive:
                if file_path.is_file():
                    arcname = file_path.relative_to(out_path)
                    zip_file.write(file_path, arcname=str(arcname))

        # Move o arquivo temporário para o destino final seguro
        temp_zip.replace(zip_target)
        logger.info("Análise anterior arquivada com sucesso em: %s", zip_target)
    except Exception as exc:
        logger.error("Falha ao compactar relatórios anteriores em ZIP: %s", exc)
        if temp_zip.exists():
            temp_zip.unlink(missing_ok=True)
        return None

    # Limpeza dos arquivos originais já empacotados no ZIP
    for file_path in files_to_archive:
        try:
            if file_path.is_file():
                file_path.unlink(missing_ok=True)
        except OSError as err:
            logger.warning("Não foi possível remover arquivo anterior arquivado %s: %s", file_path, err)

    # Limpeza dos diretórios vazios remanescentes (ordenados por profundidade decrescente)
    for dir_path in sorted(dirs_to_archive, key=lambda p: len(p.parts), reverse=True):
        try:
            if (
                dir_path.is_dir()
                and dir_path != arch_path
                and not dir_path.is_relative_to(arch_path)
                and not any(dir_path.iterdir())
            ):
                shutil.rmtree(dir_path, ignore_errors=True)
        except OSError:
            pass

    return zip_target
