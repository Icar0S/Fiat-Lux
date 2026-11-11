<#
.SYNOPSIS
    Configura o Fiat Lux nesta máquina, do zero ou aproveitando o que já existe.

.DESCRIPTION
    Faz só o que ainda falta, nesta ordem:
      1. acha o uv (ou instala o oficial) e o põe no PATH do usuário;
      2. instala o Python 3.12 e as dependências do projeto (uv sync);
      3. roda "fiatlux configurar": cria o .env, pergunta (se você quiser) o servidor de LLM
         (URL e chave) e o bot do Telegram, monta a base bíblica e o índice de busca e gera
         uma Palavra do Dia de teste (--dry-run: nada é enviado).
    Pode ser repetido à vontade: cada etapa confere o que já existe.

.PARAMETER Modo
    auto (padrão): completo se os modelos neurais já estiverem instalados ou baixados; senão, leve.
    leve: busca lexical; cerca de 5 minutos na primeira vez.
    completo: modelos neurais (torch, sentence-transformers e ~3,4 GB de modelos); o índice leva
    cerca de 40 minutos em CPU, uma vez só.

.PARAMETER SemDemonstracao
    Não gera a Palavra do Dia de teste no final.

.PARAMETER SemPerguntas
    Não pergunta o servidor de LLM nem o Telegram (para rodar sem ninguém olhando).

.PARAMETER ReconstruirIndice
    Reconstrói o índice de busca mesmo que o atual sirva.

.EXAMPLE
    Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass -Force; .\configurar.ps1

.EXAMPLE
    .\configurar.ps1 -Modo completo
#>
[CmdletBinding()]
param(
    [ValidateSet('auto', 'leve', 'completo')]
    [string]$Modo = 'auto',
    [switch]$SemDemonstracao,
    [switch]$SemPerguntas,
    [switch]$ReconstruirIndice
)

# Stop vale para os cmdlets. Em volta dos programas externos (uv, python) fica Continue: no
# Windows PowerShell 5.1, com a saída redirecionada (2>&1, *> log.txt), cada linha de progresso
# que eles escrevem no stderr viraria um erro fatal. Para eles, vale o código de saída.
$ErrorActionPreference = 'Stop'
$VersaoMinimaUv = [version]'0.9.0'
# O maior caminho dentro da .venv tem ~150 caracteres no modo completo (licenças do torch) e
# ~117 no leve (scikit-learn); com a pasta do projeto acima de ~105, o completo passa do limite
# de 260 do Windows. O aviso sai antes, com folga.
$LimiteCaminho = 100

# Visual: o mesmo do fiatlux configurar (logo em degradê dourado, ● nas etapas, ✓ · ! ✗ nas
# linhas). Cores só quando a saída é um terminal; RGB (24 bits) quando ele entende sequências
# ANSI (Windows Terminal, VS Code, ConEmu/Cmder); senão, as 16 cores do console. NO_COLOR desliga.
$script:Cor = (-not [Console]::IsOutputRedirected) -and (-not $env:NO_COLOR)
$script:Rgb = $script:Cor -and ($Host.UI.SupportsVirtualTerminal -or $env:WT_SESSION -or $env:ConEmuANSI -eq 'ON' -or $env:TERM_PROGRAM -eq 'vscode')
$script:Esc = [char]27
$Ouro = '#F5A623'
$Verde = '#6CC570'
$Amarelo = '#E8C468'
$Vermelho = '#E5534B'
$Cinza = '#949494'

function Write-Cor {
    # $Texto na cor $Hex (RGB) ou, sem ANSI, na cor $Reserva do console; vazio = cor padrão.
    param([string]$Texto, [string]$Hex = '', [string]$Reserva = '', [switch]$Negrito, [switch]$SemQuebra)
    if ($script:Rgb) {
        $codigos = @()
        if ($Negrito) { $codigos += '1' }
        if ($Hex) {
            $r = [Convert]::ToInt32($Hex.Substring(1, 2), 16)
            $g = [Convert]::ToInt32($Hex.Substring(3, 2), 16)
            $b = [Convert]::ToInt32($Hex.Substring(5, 2), 16)
            $codigos += "38;2;$r;$g;$b"
        }
        if ($codigos.Count) {
            $Texto = "$($script:Esc)[$($codigos -join ';')m$Texto$($script:Esc)[0m"
        }
        Write-Host $Texto -NoNewline:$SemQuebra
    } elseif ($script:Cor -and $Reserva) {
        Write-Host $Texto -ForegroundColor $Reserva -NoNewline:$SemQuebra
    } else {
        Write-Host $Texto -NoNewline:$SemQuebra
    }
}

function Get-Largura {
    try { return [Math]::Max(40, [int]$Host.UI.RawUI.WindowSize.Width) } catch { return 100 }
}

function Write-Logo {
    $linhas = @(
        '███████╗██╗ █████╗ ████████╗    ██╗     ██╗   ██╗██╗  ██╗',
        '██╔════╝██║██╔══██╗╚══██╔══╝    ██║     ██║   ██║╚██╗██╔╝',
        '█████╗  ██║███████║   ██║       ██║     ██║   ██║ ╚███╔╝ ',
        '██╔══╝  ██║██╔══██║   ██║       ██║     ██║   ██║ ██╔██╗ ',
        '██║     ██║██║  ██║   ██║       ███████╗╚██████╔╝██╔╝ ██╗',
        '╚═╝     ╚═╝╚═╝  ╚═╝   ╚═╝       ╚══════╝ ╚═════╝ ╚═╝  ╚═╝'
    )
    # do claro ao âmbar, como luz que desce; a última linha, só de sombra, mais escura
    $cores = @('#FFE08A', '#FFCF5C', '#F5B53A', '#F5A623', '#E3851B', '#9C5B1F')
    $reservas = @('Yellow', 'Yellow', 'Yellow', 'DarkYellow', 'DarkYellow', 'DarkGray')
    Write-Host ''
    if ((Get-Largura) -lt 62) {
        Write-Cor '  ✦ FIAT LUX' $Ouro 'DarkYellow' -Negrito
        return
    }
    for ($i = 0; $i -lt $linhas.Count; $i++) {
        Write-Cor ('  ' + $linhas[$i]) $cores[$i] $reservas[$i] -Negrito
    }
}

function Write-Quadro([string]$Subtitulo, [string]$Pasta) {
    # Quadro de bordas arredondadas, como o do fiatlux configurar: título, lema e a pasta.
    $lema = '  ·  assistente diário e semanal da Palavra de Deus'
    $rotulo = 'pasta   '
    $maximo = (Get-Largura) - 8
    if ($rotulo.Length + $Pasta.Length -gt $maximo) {
        $resta = [Math]::Max(10, $maximo - $rotulo.Length - 1)
        $Pasta = '…' + $Pasta.Substring($Pasta.Length - $resta)
    }
    if (2 + $Subtitulo.Length + $lema.Length -gt $maximo) { $lema = '' }
    $largura = [Math]::Max(2 + $Subtitulo.Length + $lema.Length, $rotulo.Length + $Pasta.Length)
    Write-Host ''
    Write-Cor ('  ╭' + ('─' * ($largura + 2)) + '╮') $Ouro 'DarkYellow'
    Write-Cor '  │ ' $Ouro 'DarkYellow' -SemQuebra
    Write-Cor '✦ ' $Ouro 'DarkYellow' -Negrito -SemQuebra
    Write-Cor $Subtitulo '' '' -Negrito -SemQuebra
    Write-Cor $lema $Cinza 'DarkGray' -SemQuebra
    Write-Host (' ' * [Math]::Max(0, $largura - 2 - $Subtitulo.Length - $lema.Length)) -NoNewline
    Write-Cor ' │' $Ouro 'DarkYellow'
    Write-Cor ('  │' + (' ' * ($largura + 2)) + '│') $Ouro 'DarkYellow'
    Write-Cor '  │ ' $Ouro 'DarkYellow' -SemQuebra
    Write-Cor $rotulo $Cinza 'DarkGray' -SemQuebra
    Write-Host ($Pasta + (' ' * [Math]::Max(0, $largura - $rotulo.Length - $Pasta.Length))) -NoNewline
    Write-Cor ' │' $Ouro 'DarkYellow'
    Write-Cor ('  ╰' + ('─' * ($largura + 2)) + '╯') $Ouro 'DarkYellow'
}

function Write-Etapa([string]$Texto, [string]$Detalhe = '') {
    Write-Host ''
    Write-Cor ' ● ' $Ouro 'DarkYellow' -Negrito -SemQuebra
    if ($Detalhe) {
        Write-Cor $Texto '' '' -Negrito -SemQuebra
        Write-Cor "  $Detalhe" $Cinza 'DarkGray'
    } else {
        Write-Cor $Texto '' '' -Negrito
    }
}

function Write-Linha([string]$Icone, [string]$Hex, [string]$Reserva, [string]$Texto, [string]$HexTexto = '', [string]$ReservaTexto = '') {
    Write-Cor "   $Icone " $Hex $Reserva -Negrito -SemQuebra
    Write-Cor $Texto $HexTexto $ReservaTexto
}

function Write-Ok([string]$Texto) { Write-Linha '✓' $Verde 'Green' $Texto }

function Write-Info([string]$Texto) { Write-Linha '·' $Cinza 'DarkGray' $Texto $Cinza 'DarkGray' }

function Write-Aviso([string]$Texto) { Write-Linha '!' $Amarelo 'Yellow' $Texto $Amarelo 'Yellow' }

function Write-Erro([string]$Texto) { Write-Linha '✗' $Vermelho 'Red' $Texto $Vermelho 'Red' }

function Get-VersaoUv([string]$Exe) {
    # "uv 0.11.32 (3010295ae 2026-07-23 ...)" -> [version]0.11.32; $null se não roda.
    if (-not $Exe -or $Exe.StartsWith('\') -or -not (Test-Path -LiteralPath $Exe)) { return $null }
    $ErrorActionPreference = 'Continue'
    try { $saida = & $Exe --version 2>$null } catch { return $null }
    if ($LASTEXITCODE -ne 0) { return $null }
    if ("$saida" -match '(\d+)\.(\d+)\.(\d+)') {
        return [version]('{0}.{1}.{2}' -f $Matches[1], $Matches[2], $Matches[3])
    }
    return $null
}

function Find-Uv {
    # Procura no PATH e onde os instaladores costumam deixar o uv: instalador oficial, winget,
    # scoop, chocolatey, pip/pipx em qualquer Python (inclusive o da Microsoft Store) e conda.
    $candidatos = New-Object System.Collections.Generic.List[string]
    foreach ($c in @(Get-Command uv.exe -CommandType Application -All -ErrorAction SilentlyContinue)) {
        $candidatos.Add($c.Path)
    }
    $padroes = @(
        "$env:UV_INSTALL_DIR\uv.exe",
        "$env:USERPROFILE\.local\bin\uv.exe",
        "$env:USERPROFILE\.cargo\bin\uv.exe",
        "$env:LOCALAPPDATA\Microsoft\WinGet\Links\uv.exe",
        "$env:LOCALAPPDATA\Microsoft\WinGet\Packages\astral-sh.uv*\uv.exe",
        "$env:USERPROFILE\scoop\shims\uv.exe",
        "$env:ProgramData\chocolatey\bin\uv.exe",
        "$env:APPDATA\Python\Python3*\Scripts\uv.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python3*\Scripts\uv.exe",
        "$env:LOCALAPPDATA\Packages\PythonSoftwareFoundation.Python.3*\LocalCache\local-packages\Python3*\Scripts\uv.exe",
        "$env:CONDA_PREFIX\Scripts\uv.exe",
        "$env:USERPROFILE\anaconda3\Scripts\uv.exe",
        "$env:USERPROFILE\miniconda3\Scripts\uv.exe",
        "$env:USERPROFILE\miniforge3\Scripts\uv.exe"
    )
    foreach ($p in $padroes) {
        if ($p.StartsWith('\')) { continue }  # variável de ambiente vazia
        foreach ($a in @(Get-Item -Path $p -ErrorAction SilentlyContinue | Sort-Object FullName -Descending)) {
            $candidatos.Add($a.FullName)
        }
    }
    $vistos = @{}
    $antigo = $null
    foreach ($c in $candidatos) {
        $chave = $c.ToLowerInvariant()
        if ($vistos.ContainsKey($chave)) { continue }
        $vistos[$chave] = $true
        $v = Get-VersaoUv $c
        if (-not $v) { continue }
        if ($v -ge $VersaoMinimaUv) { return [pscustomobject]@{ Caminho = $c; Versao = $v } }
        if (-not $antigo) { $antigo = [pscustomobject]@{ Caminho = $c; Versao = $v } }
    }
    if ($antigo) {
        Write-Info "uv $($antigo.Versao) é antigo (mínimo $VersaoMinimaUv): tentando atualizar"
        $ErrorActionPreference = 'Continue'
        & $antigo.Caminho self update | Out-Host  # Out-Host: a saída não entra no valor devolvido
        $v = Get-VersaoUv $antigo.Caminho
        if ($v -and $v -ge $VersaoMinimaUv) {
            return [pscustomobject]@{ Caminho = $antigo.Caminho; Versao = $v }
        }
    }
    return $null
}

function Install-Uv {
    Write-Info 'uv não encontrado: instalando o oficial (https://docs.astral.sh/uv/), só para este usuário'
    $powershell = (Get-Process -Id $PID).Path
    $comando = '[Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor 3072; irm https://astral.sh/uv/install.ps1 | iex'
    $ErrorActionPreference = 'Continue'
    & $powershell -NoProfile -ExecutionPolicy Bypass -Command $comando | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw 'a instalação do uv falhou (veja a mensagem acima). Instale à mão: https://docs.astral.sh/uv/getting-started/installation/'
    }
    foreach ($p in @("$env:UV_INSTALL_DIR\uv.exe", "$env:USERPROFILE\.local\bin\uv.exe", "$env:USERPROFILE\.cargo\bin\uv.exe")) {
        $v = Get-VersaoUv $p
        if ($v) { return [pscustomobject]@{ Caminho = $p; Versao = $v } }
    }
    throw 'o instalador terminou, mas o uv.exe não apareceu em ~\.local\bin. Abra um terminal novo e rode o script de novo.'
}

function Send-AvisoAmbiente {
    # Avisa o Windows que o ambiente mudou, para os terminais abertos depois já verem o PATH novo.
    try {
        if (-not ('FiatLux.Ambiente' -as [type])) {
            Add-Type -Namespace FiatLux -Name Ambiente -MemberDefinition @'
[DllImport("user32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
public static extern IntPtr SendMessageTimeout(IntPtr hWnd, uint Msg, UIntPtr wParam, string lParam, uint fuFlags, uint uTimeout, out UIntPtr lpdwResult);
'@
        }
        $resultado = [UIntPtr]::Zero
        [void][FiatLux.Ambiente]::SendMessageTimeout([IntPtr]0xffff, 0x1A, [UIntPtr]::Zero, 'Environment', 2, 5000, [ref]$resultado)
    } catch {
        Write-Verbose "aviso de mudança de ambiente não enviado: $($_.Exception.Message)"
    }
}

function Test-NoPath([string]$Valor, [string]$Pasta) {
    foreach ($p in @($Valor -split ';')) {
        if ($p -and [Environment]::ExpandEnvironmentVariables($p).TrimEnd('\') -eq $Pasta) { return $true }
    }
    return $false
}

function Add-PathUsuario([string]$Pasta) {
    # Põe $Pasta no PATH desta sessão e, se faltar, no PATH do usuário (registro), sem duplicar
    # e preservando o tipo do valor (REG_EXPAND_SZ). Devolve $true se mudou o registro.
    $Pasta = $Pasta.TrimEnd('\')
    if (-not (Test-NoPath $env:Path $Pasta)) { $env:Path = "$Pasta;$env:Path" }
    if (Test-NoPath ([Environment]::GetEnvironmentVariable('Path', 'Machine')) $Pasta) { return $false }
    $chave = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey('Environment')
    try {
        $bruto = [string]$chave.GetValue('Path', '', [Microsoft.Win32.RegistryValueOptions]::DoNotExpandEnvironmentNames)
        if (Test-NoPath $bruto $Pasta) { return $false }
        $tipo = [Microsoft.Win32.RegistryValueKind]::ExpandString
        if ($chave.GetValueNames() -contains 'Path') { $tipo = $chave.GetValueKind('Path') }
        $partes = @($bruto -split ';' | Where-Object { $_ -ne '' })
        $chave.SetValue('Path', ((@($partes) + $Pasta) -join ';'), $tipo)
    } finally {
        $chave.Close()
    }
    Send-AvisoAmbiente
    return $true
}

function Resolve-Modo([string]$Pedido) {
    $temMl = Test-Path -LiteralPath '.venv\Lib\site-packages\sentence_transformers'
    $temModelos = Test-Path -LiteralPath '.cache\huggingface\hub\models--intfloat--multilingual-e5-base'
    if ($Pedido -eq 'leve' -and $temMl) {
        Write-Aviso 'o modo leve tira o torch e o sentence-transformers da .venv e troca o índice pelo lexical (para voltar: -Modo completo)'
    }
    if ($Pedido -ne 'auto') { return [pscustomobject]@{ Modo = $Pedido; Motivo = 'escolhido com -Modo' } }
    if ($temMl) { return [pscustomobject]@{ Modo = 'completo'; Motivo = 'os modelos neurais já estão instalados na .venv' } }
    if ($temModelos) { return [pscustomobject]@{ Modo = 'completo'; Motivo = 'os modelos neurais já foram baixados em .cache\huggingface' } }
    return [pscustomobject]@{ Modo = 'leve'; Motivo = 'padrão; para a busca neural, use -Modo completo' }
}

$inicio = Get-Date
$codigo = 0
Push-Location -LiteralPath $PSScriptRoot
try {
    Write-Logo
    Write-Quadro 'configuração' $PSScriptRoot
    if (-not (Test-Path -LiteralPath 'pyproject.toml')) {
        throw 'o configurar.ps1 precisa estar na pasta do Fiat Lux (ao lado do pyproject.toml)'
    }
    $longos = 0
    try {
        $longos = [int](Get-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' -Name LongPathsEnabled -ErrorAction Stop).LongPathsEnabled
    } catch {
        $longos = 0
    }
    if ($PSScriptRoot.Length -gt $LimiteCaminho -and $longos -ne 1) {
        Write-Aviso "o caminho desta pasta tem $($PSScriptRoot.Length) caracteres; acima de ~105, alguns arquivos do modo completo (torch) passam do limite de 260 do Windows. Prefira algo como C:\projetos\Fiat-Lux (ou habilite caminhos longos)."
    }

    Write-Etapa 'uv' 'gerencia o Python e as dependências'
    $uv = Find-Uv
    if (-not $uv) { $uv = Install-Uv }
    Write-Ok "uv $($uv.Versao) · $($uv.Caminho)"
    $pastaUv = Split-Path -Parent $uv.Caminho
    if (Add-PathUsuario $pastaUv) {
        Write-Info "adicionei $pastaUv ao PATH do usuário: o comando uv passa a funcionar também nos próximos terminais"
    } else {
        Write-Ok 'o uv já está no PATH do usuário'
    }

    Write-Etapa 'Python 3.12 e dependências'
    $m = Resolve-Modo $Modo
    Write-Info "modo $($m.Modo) ($($m.Motivo))"
    $argsSync = @('sync', '--frozen')
    $temMl = Test-Path -LiteralPath '.venv\Lib\site-packages\sentence_transformers'
    if ($m.Modo -eq 'completo') {
        $argsSync += @('--extra', 'ml')
        if (-not $temMl) {
            Write-Info 'o modo completo inclui o torch e o sentence-transformers (download grande na primeira vez)'
        }
    }
    # sem download grande à vista (.venv pronta para o modo), o uv fica quieto e a linha de
    # resultado é nossa; senão, as barras de progresso dele aparecem
    $quieto = (Test-Path -LiteralPath '.venv') -and ($m.Modo -eq 'leve' -or $temMl)
    if ($quieto) { $argsSync += '--quiet' }
    $ErrorActionPreference = 'Continue'
    & $uv.Caminho @argsSync
    $codigoSync = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
    if ($codigoSync -ne 0) {
        throw "o uv sync falhou (código $codigoSync; veja a mensagem acima). Se aparecer 'Acesso negado' (os error 5), feche o VS Code e outros programas que usam a .venv e rode o script de novo."
    }
    Write-Ok 'dependências em dia (uv sync)'

    # o fiatlux configurar continua com as próximas etapas; o logo já foi mostrado aqui
    $argsCfg = @('run', '--no-sync', 'fiatlux', 'configurar', '--sem-cabecalho')
    if ($SemDemonstracao) { $argsCfg += '--sem-demonstracao' }
    if ($SemPerguntas) { $argsCfg += '--sem-perguntas' }
    if ($ReconstruirIndice) { $argsCfg += '--reconstruir-indice' }
    $ErrorActionPreference = 'Continue'
    & $uv.Caminho @argsCfg
    $codigo = $LASTEXITCODE
    $ErrorActionPreference = 'Stop'
} catch {
    Write-Host ''
    Write-Erro "erro: $($_.Exception.Message)"
    $codigo = 1
} finally {
    Pop-Location
}

$duracao = (Get-Date) - $inicio
$tempo = '{0} min {1:00} s' -f [int][math]::Floor($duracao.TotalMinutes), $duracao.Seconds
Write-Host ''
if ($codigo -eq 0) {
    # o veredito está no painel final do fiatlux configurar, logo acima
    Write-Cor "   Terminado em $tempo · o comando uv já funciona neste terminal e nos próximos (no VS Code, feche e abra o VS Code antes)" $Cinza 'DarkGray'
} else {
    Write-Erro "A configuração parou com erro ($tempo). Corrija o que a mensagem indica e rode o script de novo: ele continua de onde parou."
}
Write-Host ''
exit $codigo
