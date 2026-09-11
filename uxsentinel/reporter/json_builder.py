import json
from pathlib import Path

from uxsentinel.core.models import TestReport


def save_json_report(report: TestReport, output_dir: str) -> Path:
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    report_file = out_path / f"{report.scenario_id}_report.json"

    # Serialização do Pydantic
    data = report.model_dump(mode="json")
    report_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return report_file
