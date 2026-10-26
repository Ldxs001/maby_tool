# ASCII only. User-run helper: create test cert, sign the MSIX, sideload it.
# Prerequisite (manual): Settings -> Privacy & security -> For developers ->
# Developer Mode = ON.
# Note: AppX deployment validates the signature chain against the LOCAL
# MACHINE trusted roots, so step 2 imports the cert into LocalMachine\Root
# via one UAC elevation prompt (you approve it, the script does not bypass
# anything).
param([string]$Msix = "")
$ErrorActionPreference = "Stop"
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Split-Path -Parent $here

if (-not $Msix) {
    $latest = Get-ChildItem (Join-Path $root "_setup_out") -Filter "*-Store.msix" |
        Sort-Object LastWriteTime -Descending | Select-Object -First 1
    if ($latest) { $Msix = $latest.FullName }
}
if (-not (Test-Path $Msix)) { Write-Host "MSIX not found"; exit 1 }
Write-Host "Package: $Msix"

# Publisher must match the package identity exactly.
$pub = "CN=MDEditorPlaceholder"
$ijf = Join-Path $here "_msix_identity.json"
if (Test-Path $ijf) {
    $j = Get-Content $ijf -Raw | ConvertFrom-Json
    if ($j.publisher) { $pub = $j.publisher }
}
Write-Host "Publisher: $pub"

# 1. Self-signed code signing cert whose subject == package publisher.
#    Reuse an existing one from a previous run if present.
$cert = Get-ChildItem Cert:\CurrentUser\My |
    Where-Object { $_.Subject -eq $pub -and $_.FriendlyName -eq "MDEditor test signing" } |
    Sort-Object NotBefore -Descending | Select-Object -First 1
if ($cert) {
    Write-Host "Reusing existing cert: $($cert.Thumbprint)"
} else {
    $cert = New-SelfSignedCertificate -Type Custom -Subject $pub `
        -KeyUsage DigitalSignature -FriendlyName "MDEditor test signing" `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3", "2.5.29.19={text}")
    Write-Host "Created cert: $($cert.Thumbprint)"
}

# 2. Trust it for sideloading.
#    2a. LocalMachine\Root -- REQUIRED by AppX signature validation
#        (self-signed cert is its own root). Needs one UAC approval.
$cer = Join-Path $env:TEMP "mdeditor_test.cer"
Export-Certificate -Cert $cert -FilePath $cer | Out-Null
$already = (Get-ChildItem Cert:\LocalMachine\Root | Where-Object { $_.Thumbprint -eq $cert.Thumbprint })
if (-not $already) {
    Write-Host "Requesting admin approval to trust the test root (UAC)..."
    $proc = Start-Process powershell -Verb RunAs -Wait -PassThru -WindowStyle Hidden -ArgumentList @(
        "-NoProfile", "-Command",
        "Import-Certificate -FilePath '$cer' -CertStoreLocation Cert:\LocalMachine\Root | Out-Null")
    if ($proc.ExitCode -ne 0) {
        Write-Host "Root trust import failed or was declined. Cannot sideload."; exit 1
    }
} else {
    Write-Host "Root already trusted in LocalMachine\Root."
}
Remove-Item $cer -ErrorAction SilentlyContinue

#    2b. CurrentUser TrustedPeople -- belt and braces, no admin needed.
$pwd0 = ConvertTo-SecureString -String "mdeditor-test" -Force -AsPlainText
$pfx = Join-Path $env:TEMP "mdeditor_test.pfx"
Export-PfxCertificate -Cert $cert -FilePath $pfx -Password $pwd0 | Out-Null
Import-PfxCertificate -FilePath $pfx -CertStoreLocation "Cert:\CurrentUser\TrustedPeople" -Password $pwd0 | Out-Null
Remove-Item $pfx

# 3. Sign the package.
$signtool = Get-ChildItem "${env:ProgramFiles(x86)}\Windows Kits\10\bin" -Recurse -Filter signtool.exe |
    Where-Object { $_.Directory.Name -eq "x64" } |
    Sort-Object FullName -Descending | Select-Object -First 1
& $signtool.FullName sign /fd SHA256 /sha1 $cert.Thumbprint $Msix
if ($LASTEXITCODE -ne 0) { Write-Host "SIGN FAILED"; exit 1 }

# 4. Sideload.
Add-AppxPackage -Path $Msix
if ($?) { Write-Host "DONE. Look for MDEditor in the Start Menu." }
