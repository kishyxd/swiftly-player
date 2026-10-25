# The environment for a build: MSVC and Swift.
#
# **Why this is here and not in the system environment.** Swift needs the
# headers and link libraries of MSVC (`INCLUDE`, `LIB`), and only
# `vcvars64.bat` sets them. Skipping it produces a list of missing symbols at
# link time that looks like an error in our own code.
#
# Dot-source it:  . .\environment.ps1

param(
    [string]$SwiftWurzel = 'C:\Swift',
    [string]$SwiftFassung = '6.2.1',
    [string]$BuildTools = 'C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools'
)

# **Where MSVC is, when the build tools are not at the expected path.**
#
# The path above is where a separate "Build Tools" installation puts itself.
# A machine that has a full Visual Studio instead - which every GitHub
# runner does, and which is what `vcvars64.bat` is actually asked for -
# has it somewhere else. `vswhere` knows where: it is installed with
# Visual Studio and answers for every installation it finds.
#
# So: try the given path first, and only then ask. A developer with the
# Build Tools where the script expects it is not affected at all.
$vcvars = Join-Path $BuildTools 'VC\Auxiliary\Build\vcvars64.bat'
if (-not (Test-Path $vcvars)) {
    $vswhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (Test-Path $vswhere) {
        $gefunden = & $vswhere -latest -products * `
            -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 `
            -property installationPath
        if ($gefunden) {
            $kandidat = Join-Path $gefunden 'VC\Auxiliary\Build\vcvars64.bat'
            if (Test-Path $kandidat) { $vcvars = $kandidat }
        }
    }
}
if (-not (Test-Path $vcvars)) { throw "vcvars64.bat fehlt: $vcvars" }

# `cmd` runs the batch script and prints the environment afterwards; the lines
# are read back here. There is no other way to get at the result of a batch
# script.
cmd /c "`"$vcvars`" >nul 2>&1 && set" | ForEach-Object {
    if ($_ -match '^([^=]+)=(.*)$') {
        Set-Item -Path "env:$($matches[1])" -Value $matches[2] -ErrorAction SilentlyContinue
    }
}

$toolchain = Join-Path $SwiftWurzel "Toolchains\$SwiftFassung+Asserts\usr\bin"
$laufzeit  = Join-Path $SwiftWurzel "Runtimes\$SwiftFassung\usr\bin"
$sdk       = Join-Path $SwiftWurzel "Platforms\$SwiftFassung\Windows.platform\Developer\SDKs\Windows.sdk"
if (-not (Test-Path $toolchain)) { throw "Swift fehlt: $toolchain" }

$env:SDKROOT = $sdk
$env:Path = "$toolchain;$laufzeit;" + $env:Path
