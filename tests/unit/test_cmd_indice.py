import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from fiat_lux.cli import cmd_indice


def _preparar(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, codigo: int, stderr: str
) -> list[list[str]]:
    import shutil

    from fiat_lux import config

    s = SimpleNamespace(
        caminhos=SimpleNamespace(biblia_db=tmp_path / "processed" / "biblia.sqlite")
    )
    monkeypatch.setattr(config, "obter_settings", lambda: s)
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/bin/gh")
    chamadas: list[list[str]] = []

    def rodar(args: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        chamadas.append(args)
        return subprocess.CompletedProcess(args, codigo, "", stderr)

    monkeypatch.setattr(subprocess, "run", rodar)
    return chamadas


def test_baixar_release_inexistente_explica_o_construir_indice(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    chamadas = _preparar(monkeypatch, tmp_path, 1, "release not found\n")
    with pytest.raises(SystemExit) as e:
        cmd_indice.baixar_release(repo="dono/repo", tag="indice-latest")
    assert e.value.code == 1
    assert chamadas and chamadas[0][:4] == ["gh", "release", "download", "indice-latest"]
    saida = " ".join(capsys.readouterr().err.split())
    assert "ainda não existe" in saida and "construir-indice" in saida
    assert "Traceback" not in saida


def test_baixar_release_outro_erro_mostra_o_detalhe(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _preparar(monkeypatch, tmp_path, 1, "HTTP 401: Bad credentials\n")
    with pytest.raises(SystemExit):
        cmd_indice.baixar_release(repo="dono/repo", tag="indice-latest")
    assert "Bad credentials" in " ".join(capsys.readouterr().err.split())


def test_baixar_release_ok(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    chamadas = _preparar(monkeypatch, tmp_path, 0, "")
    cmd_indice.baixar_release(repo="dono/repo", tag="indice-latest")
    assert len(chamadas) == 1
