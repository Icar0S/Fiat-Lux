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

# Visual: o mesmo do fiatlux configurar (logo em degradê dourado, ● nas etapas, ✓ · ! ✗ nas
# linhas). Cores só num terminal e sem NO_COLOR; RGB quando o terminal anuncia COLORTERM
# truecolor/24bit, senão 256 cores.
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then cor=1; else cor=0; fi
case "${COLORTERM:-}" in
  truecolor | 24bit) rgb=$cor ;;
  *) rgb=0 ;;
esac
OURO="#F5A623"
VERDE="#6CC570"
AMARELO="#E8C468"
VERMELHO="#E5534B"
CINZA="#949494"

# tinta "#RRGGBB" N: liga a cor (24 bits ou a N das 256); sem cores, não escreve nada
tinta() {
  if [ "$cor" != 1 ]; then return 0; fi
  if [ "$rgb" = 1 ]; then
    local h=${1#\#}
    printf '\033[38;2;%d;%d;%dm' "0x${h:0:2}" "0x${h:2:2}" "0x${h:4:2}"
  else
    printf '\033[38;5;%sm' "$2"
  fi
}
negrito() { if [ "$cor" = 1 ]; then printf '\033[1m'; fi; }
normal() { if [ "$cor" = 1 ]; then printf '\033[0m'; fi; }
largura() {
  local c
  c=$(tput cols 2>/dev/null || true)
  case "$c" in '' | *[!0-9]*) c=100 ;; esac
  printf '%s' "$c"
}
repetir() { # repetir CARACTERE N
  local s
  s=$(printf '%*s' "$2" '')
  printf '%s' "${s// /$1}"
}

logo() {
  local i
  local linhas=(
    '███████╗██╗ █████╗ ████████╗    ██╗     ██╗   ██╗██╗  ██╗'
    '██╔════╝██║██╔══██╗╚══██╔══╝    ██║     ██║   ██║╚██╗██╔╝'
    '█████╗  ██║███████║   ██║       ██║     ██║   ██║ ╚███╔╝ '
    '██╔══╝  ██║██╔══██║   ██║       ██║     ██║   ██║ ██╔██╗ '
    '██║     ██║██║  ██║   ██║       ███████╗╚██████╔╝██╔╝ ██╗'
    '╚═╝     ╚═╝╚═╝  ╚═╝   ╚═╝       ╚══════╝ ╚═════╝ ╚═╝  ╚═╝'
  )
  # do claro ao âmbar, como luz que desce; a última linha, só de sombra, mais escura
  local cores=("#FFE08A" "#FFCF5C" "#F5B53A" "#F5A623" "#E3851B" "#9C5B1F")
  local c256=(222 221 215 214 208 130)
  printf '\n'
  if [ "$(largura)" -lt 62 ]; then
    printf '  %s%s✦ FIAT LUX%s\n' "$(negrito)" "$(tinta "$OURO" 214)" "$(normal)"
    return 0
  fi
  for i in 0 1 2 3 4 5; do
    printf '  %s%s%s%s\n' "$(negrito)" "$(tinta "${cores[$i]}" "${c256[$i]}")" "${linhas[$i]}" "$(normal)"
  done
}

quadro() { # quadro SUBTÍTULO PASTA: bordas arredondadas, como o do fiatlux configurar
  local sub=$1 pasta=$2 lema="  ·  assistente diário e semanal da Palavra de Deus" rot="pasta   "
  local max w b
  max=$(($(largura) - 8))
  if [ $((${#rot} + ${#pasta})) -gt "$max" ]; then
    local resta=$((max - ${#rot} - 1))
    if [ "$resta" -lt 10 ]; then resta=10; fi
    pasta="…${pasta: -$resta}"
  fi
  if [ $((2 + ${#sub} + ${#lema})) -gt "$max" ]; then lema=""; fi
  w=$((2 + ${#sub} + ${#lema}))
  if [ $((${#rot} + ${#pasta})) -gt "$w" ]; then w=$((${#rot} + ${#pasta})); fi
  b="$(tinta "$OURO" 214)"
  printf '\n  %s╭%s╮%s\n' "$b" "$(repetir ─ $((w + 2)))" "$(normal)"
  printf '  %s│%s %s%s✦ %s%s%s%s%s%s%s%*s %s│%s\n' "$b" "$(normal)" "$(negrito)" "$b" "$(normal)" \
    "$(negrito)" "$sub" "$(normal)" "$(tinta "$CINZA" 245)" "$lema" "$(normal)" \
    $((w - 2 - ${#sub} - ${#lema})) '' "$b" "$(normal)"
  printf '  %s│%*s│%s\n' "$b" $((w + 2)) '' "$(normal)"
  printf '  %s│%s %s%s%s%s%*s %s│%s\n' "$b" "$(normal)" "$(tinta "$CINZA" 245)" "$rot" "$(normal)" \
    "$pasta" $((w - ${#rot} - ${#pasta})) '' "$b" "$(normal)"
  printf '  %s╰%s╯%s\n' "$b" "$(repetir ─ $((w + 2)))" "$(normal)"
}

etapa() { # etapa TÍTULO [DETALHE]
  printf '\n %s%s●%s %s%s%s' "$(negrito)" "$(tinta "$OURO" 214)" "$(normal)" "$(negrito)" "$1" "$(normal)"
  if [ -n "${2:-}" ]; then printf '  %s%s%s' "$(tinta "$CINZA" 245)" "$2" "$(normal)"; fi
  printf '\n'
}
linha() { # linha ÍCONE COR COR256 TEXTO [1 = o texto também na cor]
  local t
  t="$(tinta "$2" "$3")"
  if [ "${5:-}" = 1 ]; then
    printf '   %s%s%s%s %s%s%s\n' "$(negrito)" "$t" "$1" "$(normal)" "$t" "$4" "$(normal)"
  else
    printf '   %s%s%s%s %s\n' "$(negrito)" "$t" "$1" "$(normal)" "$4"
  fi
}
ok() { linha "✓" "$VERDE" 77 "$1"; }
info() { linha "·" "$CINZA" 245 "$1" 1; }
aviso() { linha "!" "$AMARELO" 186 "$1" 1; }
falhar() {
  printf '\n' >&2
  linha "✗" "$VERMELHO" 167 "erro: $1" 1 >&2
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
logo
quadro "configuração" "$(pwd)"

etapa "uv" "gerencia o Python e as dependências"
instalado_agora=0
uv="$(achar_uv || true)"
if [ -z "$uv" ]; then
  instalar_uv
  instalado_agora=1
  uv="$(achar_uv || true)"
  [ -n "$uv" ] || falhar "o instalador terminou, mas não achei o uv; abra um terminal novo e rode o script de novo"
fi
ok "uv $(versao_uv "$uv" || true) · $uv"
pasta_uv="$(dirname "$uv")"
case ":$PATH:" in
  *":$pasta_uv:"*) ok "o uv já está no PATH" ;;
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
  if [ "$tem_ml" != 1 ]; then
    info "o modo completo inclui o torch e o sentence-transformers (download grande na primeira vez)"
  fi
fi
# sem download grande à vista (.venv pronta para o modo), o uv fica quieto e a linha de resultado
# é nossa; senão, as barras de progresso dele aparecem
if [ -d .venv ] && { [ "$modo" = leve ] || [ "$tem_ml" = 1 ]; }; then args_sync+=(--quiet); fi
"$uv" "${args_sync[@]}" || falhar "o uv sync falhou (veja a mensagem acima)"
ok "dependências em dia (uv sync)"

# o fiatlux configurar continua com as próximas etapas; o logo já foi mostrado aqui
codigo=0
"$uv" run --no-sync fiatlux configurar --sem-cabecalho ${opcoes[@]+"${opcoes[@]}"} || codigo=$?

duracao=$(($(date +%s) - inicio))
printf '\n'
if [ "$codigo" -eq 0 ]; then
  # o veredito está no painel final do fiatlux configurar, logo acima
  printf '   %sTerminado em %d min %02d s%s\n' "$(tinta "$CINZA" 245)" $((duracao / 60)) $((duracao % 60)) "$(normal)"
  if [ "$instalado_agora" = 1 ]; then info "o uv acabou de ser instalado: abra um terminal novo para usar o comando uv"; fi
else
  linha "✗" "$VERMELHO" 167 "A configuração parou com erro ($((duracao / 60)) min $((duracao % 60)) s). Corrija o que a mensagem indica e rode o script de novo: ele continua de onde parou." 1
fi
printf '\n'
exit "$codigo"
