#!/usr/bin/env bash
# Configura o Fiat Lux nesta máquina (Linux/macOS), do zero ou aproveitando o que já existe.
#
# Uso: bash configurar.sh [--leve | --completo] [--sem-demonstracao] [--sem-perguntas] [--reconstruir-indice]
#
# Faz só o que falta: acha (ou instala) o uv, instala o Python 3.12 e as dependências e roda
# `fiatlux configurar` (.env, servidor de LLM opcional, base bíblica, índice e uma Palavra do Dia de
# teste com --dry-run). Sem --leve/--completo, o modo é completo se os modelos neurais já
# estiverem instalados ou baixados; senão, leve. Pode ser repetido à vontade.
set -euo pipefail

VERSAO_MINIMA_UV="0.9.0"
modo="auto"
opcoes=()

uso() { sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; }

while [ $# -gt 0 ]; do
  case "$1" in
    --leve) modo="leve" ;;
    --completo) modo="completo" ;;
    --sem-demonstracao | --sem-perguntas | --reconstruir-indice) opcoes+=("$1") ;;
    -h | --help)
      uso
      exit 0
      ;;
    *)
      printf 'opção desconhecida: %s\n\n' "$1" >&2
      uso >&2
      exit 2
      ;;
  esac
  shift
done

etapa() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }
info() { printf '    %s\n' "$1"; }
ok() { printf '    \033[32m%s\033[0m\n' "$1"; }
aviso() { printf '    \033[33maviso: %s\033[0m\n' "$1"; }
falhar() {
  printf '\n\033[31merro: %s\033[0m\n' "$1" >&2
  exit 1
}

# versao_ok A B: A >= B (versões x.y.z)
versao_ok() { [ "$(printf '%s\n%s\n' "$1" "$2" | sort -t. -k1,1n -k2,2n -k3,3n | head -n1)" = "$2" ]; }
versao_uv() { "$1" --version 2>/dev/null | sed -n 's/^uv \([0-9]*\.[0-9]*\.[0-9]*\).*/\1/p'; }

achar_uv() {
  local c v
  for c in "$(command -v uv 2>/dev/null || true)" "${UV_INSTALL_DIR:-/nao-definido}/uv" \
    "${XDG_BIN_HOME:-$HOME/.local/bin}/uv" "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv" \
    /opt/homebrew/bin/uv /usr/local/bin/uv; do
    if [ -z "$c" ] || [ ! -x "$c" ]; then continue; fi
    v="$(versao_uv "$c" || true)"
    if [ -n "$v" ] && versao_ok "$v" "$VERSAO_MINIMA_UV"; then
      printf '%s\n' "$c"
      return 0
    fi
  done
  return 1
}

instalar_uv() {
  info "uv não encontrado: instalando o oficial (https://docs.astral.sh/uv/), só para este usuário"
  if command -v curl >/dev/null 2>&1; then
    curl -LsSf https://astral.sh/uv/install.sh | sh || falhar "a instalação do uv falhou (veja a mensagem acima)"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO- https://astral.sh/uv/install.sh | sh || falhar "a instalação do uv falhou (veja a mensagem acima)"
  else
    falhar "preciso do curl ou do wget para instalar o uv (ou instale-o à mão: https://docs.astral.sh/uv/)"
  fi
}

cd "$(dirname "$0")"
[ -f pyproject.toml ] || falhar "o configurar.sh precisa estar na pasta do Fiat Lux (ao lado do pyproject.toml)"
inicio=$(date +%s)
printf '\033[1mFiat Lux · configuração\033[0m\n'
info "pasta do projeto: $(pwd)"

etapa "uv (gerencia o Python e as dependências)"
instalado_agora=0
uv="$(achar_uv || true)"
if [ -z "$uv" ]; then
  instalar_uv
  instalado_agora=1
  uv="$(achar_uv || true)"
  [ -n "$uv" ] || falhar "o instalador terminou, mas não achei o uv; abra um terminal novo e rode o script de novo"
fi
ok "uv $(versao_uv "$uv" || true): $uv"
pasta_uv="$(dirname "$uv")"
case ":$PATH:" in
  *":$pasta_uv:"*) info "o uv já está no PATH" ;;
  *)
    export PATH="$pasta_uv:$PATH"
    if [ "$instalado_agora" = 1 ]; then
      info "o instalador já pôs o uv no PATH dos próximos terminais"
    else
      aviso "a pasta do uv não está no PATH; para usar o comando uv, ponha no ~/.bashrc ou ~/.zshrc: export PATH=\"$pasta_uv:\$PATH\""
    fi
    ;;
esac

etapa "Python 3.12 e dependências"
tem_ml=0
for d in .venv/lib/python3*/site-packages/sentence_transformers .venv/Lib/site-packages/sentence_transformers; do
  if [ -d "$d" ]; then tem_ml=1; fi
done
tem_modelos=0
if [ -d .cache/huggingface/hub/models--intfloat--multilingual-e5-base ]; then tem_modelos=1; fi
if [ "$modo" = leve ] && [ "$tem_ml" = 1 ]; then
  aviso "o modo leve tira o torch e o sentence-transformers da .venv e troca o índice pelo lexical (para voltar: --completo)"
fi
if [ "$modo" = auto ]; then
  if [ "$tem_ml" = 1 ]; then
    modo=completo motivo="os modelos neurais já estão instalados na .venv"
  elif [ "$tem_modelos" = 1 ]; then
    modo=completo motivo="os modelos neurais já foram baixados em .cache/huggingface"
  else
    modo=leve motivo="padrão; para a busca neural, use --completo"
  fi
else
  motivo="escolhido na linha de comando"
fi
info "modo $modo ($motivo)"
args_sync=(sync --frozen)
if [ "$modo" = completo ]; then
  args_sync+=(--extra ml)
  info "o modo completo inclui o torch e o sentence-transformers (download grande na primeira vez)"
fi
"$uv" "${args_sync[@]}" || falhar "o uv sync falhou (veja a mensagem acima)"

etapa "Projeto (fiatlux configurar)"
codigo=0
"$uv" run --no-sync fiatlux configurar ${opcoes[@]+"${opcoes[@]}"} || codigo=$?

duracao=$(($(date +%s) - inicio))
printf '\n'
if [ "$codigo" -eq 0 ]; then
  # o veredito ("Tudo pronto." ou o que falta) é a última linha do fiatlux configurar, logo acima
  printf 'Terminado em %d min %02d s.\n' $((duracao / 60)) $((duracao % 60))
  if [ "$instalado_agora" = 1 ]; then info "o uv acabou de ser instalado: abra um terminal novo para usar o comando uv"; fi
else
  printf '\033[31mA configuração parou com erro (%d min %02d s). Corrija o que a mensagem indica e rode o script de novo: ele continua de onde parou.\033[0m\n' \
    $((duracao / 60)) $((duracao % 60))
fi
exit "$codigo"
