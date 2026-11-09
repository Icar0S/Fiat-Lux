"""Coleta a liturgia de todos os dias de um ano civil na API v2 (uso: corpus do parser).

Só biblioteca padrão, para poder rodar antes do ambiente estar pronto.
Retomável: dias já baixados são pulados. Grava em data/raw/liturgia/AAAA-MM-DD.json.

    python scripts/coletar_liturgia_ano.py 2026 [--pausa 1.5]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

URL = "https://liturgia.up.railway.app/v2/?dia={d}&mes={m}&ano={a}"
UA = "fiat-lux/0.1 (+https://github.com/Icar0S/Fiat-Lux)"


def baixar(data: dt.date, tentativas: int = 4) -> dict | None:
    url = URL.format(d=data.day, m=data.month, a=data.year)
    for i in range(tentativas):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            time.sleep(2 ** (i + 1))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            time.sleep(2 ** (i + 1))
    raise RuntimeError(f"falha ao baixar {data}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("ano", type=int)
    ap.add_argument("--pausa", type=float, default=1.5)
    ap.add_argument("--saida", default="data/raw/liturgia")
    args = ap.parse_args()
    saida = Path(args.saida)
    saida.mkdir(parents=True, exist_ok=True)
    dia = dt.date(args.ano, 1, 1)
    fim = dt.date(args.ano, 12, 31)
    baixados = faltando = 0
    while dia <= fim:
        alvo = saida / f"{dia.isoformat()}.json"
        if not alvo.exists():
            dados = baixar(dia)
            if dados is None:
                faltando += 1
                print(f"{dia} 404", flush=True)
            else:
                alvo.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
                baixados += 1
            time.sleep(args.pausa)
        dia += dt.timedelta(days=1)
    print(f"ok: {baixados} baixados, {faltando} sem liturgia", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
