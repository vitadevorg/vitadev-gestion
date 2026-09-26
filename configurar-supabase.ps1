$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$previousUrl = $env:SUPABASE_DB_URL
$previousCert = $env:SUPABASE_SSLROOTCERT
$previousDriver = $env:VITADEV_PG_DRIVER
$pointer = [IntPtr]::Zero
try {
    Write-Host 'VitaDev - conectar con tu base Supabase'
    Write-Host 'Ingresa tu contrasena ACTUAL de la base de datos, sin corchetes.'
    Write-Host 'Si la conexion funciona, se guardara cifrada para tu usuario de Windows.'
    $runtime = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
    if (-not (Test-Path -LiteralPath $runtime)) { $runtime = (Get-Command python -ErrorAction Stop).Source }
    $verifier = Join-Path $PSScriptRoot 'work/verify_supabase_env.py'
    $driverMarker = Join-Path $PSScriptRoot 'work/pg-driver-path.txt'
    $driverReady = $false
    if (Test-Path -LiteralPath $driverMarker) {
        try {
            $env:VITADEV_PG_DRIVER = (Get-Content -LiteralPath $driverMarker -Raw).Trim()
            & $runtime -I -u $verifier --check-driver
            $driverReady = ($LASTEXITCODE -eq 0)
        } catch { $driverReady = $false }
    }
    if (-not $driverReady) {
        Write-Host 'Instalando controlador en una carpeta NUEVA. No se borra ni reemplaza la carpeta bloqueada.'
        $freshDriver = Join-Path $PSScriptRoot ('work/pg-drivers/' + [guid]::NewGuid().ToString('N'))
        New-Item -ItemType Directory -Path $freshDriver -Force | Out-Null
        & $runtime -I -m pip install --disable-pip-version-check --no-warn-script-location --target $freshDriver 'psycopg[binary]==3.3.5'
        if ($LASTEXITCODE -ne 0) { throw 'No se pudo instalar el controlador' }
        $env:VITADEV_PG_DRIVER = $freshDriver
        & $runtime -I -u $verifier --check-driver
        if ($LASTEXITCODE -ne 0) { throw 'El controlador nuevo no esta disponible' }
        Set-Content -LiteralPath $driverMarker -Value $freshDriver -Encoding UTF8
    }
    $secret = Read-Host 'Contrasena' -AsSecureString
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secret)
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    $env:SUPABASE_DB_URL = 'postgresql://postgres.ayxijuliiadazimicvnm:' + [Uri]::EscapeDataString($plain) + '@aws-0-us-east-1.pooler.supabase.com:5432/postgres'
    $env:SUPABASE_SSLROOTCERT = Join-Path $PSScriptRoot 'work/supabase-project-ca.crt'
    $runtime = Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe'
    if (-not (Test-Path -LiteralPath $runtime)) { $runtime = (Get-Command python -ErrorAction Stop).Source }
    Write-Host 'Comprobando conexion... Puede tardar hasta un minuto. No cierres esta ventana.'
    & $runtime -I -u $verifier
    if ($LASTEXITCODE -eq 0) {
        $protected = ConvertTo-SecureString -String $env:SUPABASE_DB_URL -AsPlainText -Force
        $protected | ConvertFrom-SecureString | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'work/supabase-connection.dpapi') -Encoding ASCII
        Write-Host 'Conexion guardada cifrada. SQLite no fue modificado.'
        Write-Host 'Ahora avisa en el chat: conexion correcta.'
    }
} catch {
    Write-Host 'No se pudo completar la configuracion. No compartas la contrasena en el chat.'
} finally {
    if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    $plain = $null
    if ($secret) { $secret.Dispose() }
    $env:SUPABASE_DB_URL = $previousUrl
    $env:SUPABASE_SSLROOTCERT = $previousCert
    $env:VITADEV_PG_DRIVER = $previousDriver
    Read-Host 'Presiona Enter para cerrar'
}

