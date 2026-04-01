"""Test Windows Search index para correos Outlook"""
import subprocess, json, sys

query_term = sys.argv[1] if len(sys.argv) > 1 else "8030027307"

ps_script = f"""
$ErrorActionPreference = 'Stop'
try {{
    $conn = New-Object -ComObject ADODB.Connection
    $conn.Open("Provider=Search.CollatorDSO;Extended Properties='Application=Windows'")
    $sql = "SELECT TOP 10 System.Subject, System.Message.FromAddress, System.Message.ToAddress, System.DateModified, System.ItemUrl FROM SystemIndex WHERE System.Kind = 'email' AND CONTAINS('`"{query_term}`"')"
    $rs = $conn.Execute($sql)
    $results = @()
    while (-not $rs.EOF) {{
        $results += @{{
            subject = [string]$rs.Fields["System.Subject"].Value
            from = [string]$rs.Fields["System.Message.FromAddress"].Value
            to = [string]$rs.Fields["System.Message.ToAddress"].Value
            date = [string]$rs.Fields["System.DateModified"].Value
            url = [string]$rs.Fields["System.ItemUrl"].Value
        }}
        $rs.MoveNext()
    }}
    $conn.Close()
    $results | ConvertTo-Json -Depth 2
}} catch {{
    Write-Output "ERROR: $($_.Exception.Message)"
}}
"""

result = subprocess.run(
    ["powershell", "-NoProfile", "-Command", ps_script],
    capture_output=True, text=True, timeout=20, encoding="utf-8", errors="replace"
)
print("STDOUT:", result.stdout[:1000])
print("STDERR:", result.stderr[:300])
