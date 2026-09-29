from unittest.mock import patch

import pytest

from uxsentinel import __version__ as core_version
from uxsentinel_studio import __version__ as studio_version
from uxsentinel_studio.cli import main, parse_args


def test_parse_args_version(capsys):
    with pytest.raises(SystemExit) as excinfo:
        parse_args(["--version"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert studio_version in captured.out
    assert core_version in captured.out

    with pytest.raises(SystemExit) as excinfo:
        parse_args(["-v"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert studio_version in captured.out
    assert core_version in captured.out


def test_parse_args_help(capsys):
    with pytest.raises(SystemExit) as excinfo:
        parse_args(["--help"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "--info" in captured.out
    assert "--list-providers" in captured.out
    assert "--port" in captured.out
    assert "--no-browser" in captured.out

    with pytest.raises(SystemExit) as excinfo:
        parse_args(["-h"])
    assert excinfo.value.code == 0
    captured = capsys.readouterr()
    assert "--list-projects" in captured.out


@patch("uxsentinel_studio.cli.uvicorn.run")
@patch("uxsentinel_studio.cli.show_studio_info")
def test_main_info_and_status(mock_info, mock_run, tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        main(["--info", "-d", str(tmp_path)])
    assert excinfo.value.code == 0
    mock_info.assert_called_once()
    mock_run.assert_not_called()

    mock_info.reset_mock()
    with pytest.raises(SystemExit) as excinfo:
        main(["status", "-d", str(tmp_path)])
    assert excinfo.value.code == 0
    mock_info.assert_called_once()
    mock_run.assert_not_called()


@patch("uxsentinel_studio.cli.uvicorn.run")
@patch("uxsentinel.cli.list_supported_providers")
def test_main_list_providers(mock_list, mock_run):
    with pytest.raises(SystemExit) as excinfo:
        main(["--list-providers"])
    assert excinfo.value.code == 0
    mock_list.assert_called_once()
    mock_run.assert_not_called()


@patch("uxsentinel_studio.cli.uvicorn.run")
@patch("uxsentinel.cli.list_registered_projects_cli")
def test_main_list_projects(mock_list, mock_run):
    with pytest.raises(SystemExit) as excinfo:
        main(["--list-projects"])
    assert excinfo.value.code == 0
    mock_list.assert_called_once()
    mock_run.assert_not_called()


@patch("uxsentinel_studio.cli.uvicorn.run")
@patch("uxsentinel.cli.list_available_scenarios")
def test_main_list_scenarios(mock_list, mock_run, tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        main(["--list-scenarios", "-d", str(tmp_path)])
    assert excinfo.value.code == 0
    mock_list.assert_called_once()
    mock_run.assert_not_called()


def test_parse_args_all_attributes():
    args = parse_args(["-p", "9090", "-d", "/tmp/proj", "--no-browser", "--log-level", "info"])
    assert args.port == 9090
    assert args.project_dir == "/tmp/proj"
    assert args.no_browser is True
    assert args.log_level == "info"


@patch("uxsentinel_studio.cli.uvicorn.run")
@patch("uxsentinel_studio.cli.webbrowser.open")
def test_main_security_host_override(mock_browser, mock_run):
    main(["--host", "0.0.0.0", "--no-browser"])
    mock_run.assert_called_once()
    kwargs = mock_run.call_args.kwargs
    assert kwargs["host"] == "127.0.0.1"
