# Decode the exact bytes of frontend build-info.json for Windows PowerShell 5.1.
# Do not use Invoke-WebRequest.Content: its default decoding can turn UTF-8 BOM
# bytes EF BB BF into the mojibake prefix "i" + non-ASCII characters.
function ConvertFrom-HvsFrontendManifestBytes {
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)][byte[]]$Bytes)
    if ($Bytes.Length -eq 0) {
        throw "FRONTEND_BUNDLE_HTTP_INVALID: HTTP manifest body is empty."
    }
    try {
        $strictUtf8 = New-Object System.Text.UTF8Encoding($false, $true)
        $json = $strictUtf8.GetString($Bytes).TrimStart([char]0xFEFF)
        $manifest = ConvertFrom-Json -InputObject $json -ErrorAction Stop
    } catch {
        throw "FRONTEND_BUNDLE_HTTP_INVALID: manifest is not valid UTF-8 JSON: $($_.Exception.Message)"
    }
    if ($null -eq $manifest -or $manifest -isnot [pscustomobject] -or
        $null -eq $manifest.PSObject.Properties["source_commit"] -or
        $null -eq $manifest.PSObject.Properties["bundle_sha256"] -or
        $null -eq $manifest.PSObject.Properties["schema_version"]) {
        throw "FRONTEND_BUNDLE_HTTP_INVALID: manifest is missing required identity fields."
    }
    if ($manifest.schema_version -ne "HVSFrontendBuild.v1" -or
        [string]$manifest.source_commit -cnotmatch '^[0-9a-f]{40}$' -or
        [string]$manifest.bundle_sha256 -cnotmatch '^[0-9a-f]{64}$') {
        throw "FRONTEND_BUNDLE_HTTP_INVALID: manifest identity fields are invalid."
    }
    return $manifest
}

function Get-HvsFrontendManifestHttp {
    [CmdletBinding()]
    param([Parameter(Mandatory=$true)][string]$Url)
    $uri = [System.Uri]$Url
    if ($uri.Scheme -ne "http" -or $uri.Host -notin @("127.0.0.1", "localhost") -or
        $uri.AbsolutePath -ne "/build-info.json") {
        throw "FRONTEND_BUNDLE_HTTP_INVALID: expected a local HTTP build-info.json URL."
    }
    $client = New-Object System.Net.WebClient
    try {
        # DownloadData preserves the raw bytes. Content-Type and the PowerShell
        # version cannot silently influence character decoding.
        $bytes = $client.DownloadData($uri)
        return ConvertFrom-HvsFrontendManifestBytes -Bytes $bytes
    } catch {
        if ($_.Exception.Message -match "FRONTEND_BUNDLE_HTTP_INVALID") { throw }
        throw "FRONTEND_BUNDLE_HTTP_INVALID: unable to read $Url : $($_.Exception.Message)"
    } finally {
        $client.Dispose()
    }
}
