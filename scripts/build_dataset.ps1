$ErrorActionPreference = "Stop"
$env:PYTHONUTF8 = "1"

$ProjectRoot = Split-Path -Parent $PSScriptRoot
$PythonExe = "C:\Users\User\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$PackageDir = Join-Path $ProjectRoot ".tools\python-packages"

if (-not (Test-Path -LiteralPath $PythonExe)) {
    throw "Python runtime not found: $PythonExe"
}

New-Item -ItemType Directory -Force -Path $PackageDir | Out-Null

if (-not (Test-Path -LiteralPath (Join-Path $PackageDir "duckdb"))) {
    & $PythonExe -m pip install --disable-pip-version-check --target $PackageDir -r (Join-Path $ProjectRoot "requirements.txt")
    if ($LASTEXITCODE -ne 0) {
        throw "Dependency installation failed with exit code $LASTEXITCODE"
    }
}

$env:PYTHONPATH = $PackageDir
& $PythonExe (Join-Path $PSScriptRoot "generate_auction_lots.py")
if ($LASTEXITCODE -ne 0) {
    throw "Dataset generation failed with exit code $LASTEXITCODE"
}

& $PythonExe (Join-Path $PSScriptRoot "build_reference_tables.py")
if ($LASTEXITCODE -ne 0) {
    throw "Reference table generation failed with exit code $LASTEXITCODE"
}

& $PythonExe (Join-Path $PSScriptRoot "generate_documentation.py")
if ($LASTEXITCODE -ne 0) {
    throw "Documentation generation failed with exit code $LASTEXITCODE"
}
