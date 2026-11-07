# Extra trusted root certificates (optional)

Put PEM-encoded root CA certificates here (`*.crt`) when something on your network re-signs HTTPS
traffic: antivirus web scanning (AVG, Avast, Kaspersky...) or a corporate proxy. Without them, `uv sync`
during `docker build`, and the API's own HTTPS calls (Groq, Nango, job boards), fail with
`CERTIFICATE_VERIFY_FAILED`.

The Dockerfile adds every file in this folder to the image's trust store. Leave it empty if you don't need it.
`*.crt` files here are git-ignored because they are specific to one machine.

Export a Windows root certificate as PEM (PowerShell), e.g. AVG's:

```powershell
$c = Get-ChildItem Cert:\LocalMachine\Root | Where-Object Subject -like "*AVG Web/Mail Shield Root*" | Select-Object -First 1
$b64 = [Convert]::ToBase64String($c.RawData, 'InsertLineBreaks') -replace "`r`n", "`n"
"-----BEGIN CERTIFICATE-----`n$b64`n-----END CERTIFICATE-----`n" | Set-Content -NoNewline -Encoding ascii docker\certs\avg-root.crt
```

Only public certificates belong here, never private keys.
