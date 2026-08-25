# Установщик presentation-agent для Windows.
# Запуск из папки проекта:
#   powershell -ExecutionPolicy Bypass -File install.ps1
$ErrorActionPreference = "Stop"
$Dir = Split-Path -Parent $MyInvocation.MyCommand.Path

$py = "py"
if (-not (Get-Command $py -ErrorAction SilentlyContinue)) { $py = "python" }
if (-not (Get-Command $py -ErrorAction SilentlyContinue)) {
    Write-Host "Не найден Python - поставь Python 3.9+ с python.org (галочка 'Add to PATH')"
    exit 1
}
Write-Host "Запускаю настройку через $py ..."
& $py "$Dir\setup.py"
