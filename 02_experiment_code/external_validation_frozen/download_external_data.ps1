$ErrorActionPreference = 'Stop'
$raw = Join-Path $PSScriptRoot '..\external\raw'
$raw = [System.IO.Path]::GetFullPath($raw)
New-Item -ItemType Directory -Force -Path $raw | Out-Null

$headers = @{ 'User-Agent' = 'ResearchReplication/1.0 (public-data validation)' }

$gtmiUrl = 'https://datacatalogfiles.worldbank.org/ddh-published/0037889/DR0095721/WBG_GovTech_Dataset_Dec2025.xlsx'
$uciUrl = 'https://archive.ics.uci.edu/static/public/432/news%2Bpopularity%2Bin%2Bmultiple%2Bsocial%2Bmedia%2Bplatforms.zip'
$oecdUrl = 'https://sdmx.oecd.org/public/rest/data/OECD.GOV.GIP,DSD_GOV_INT@DF_GOV_TDG_2025,1.1/all?startPeriod=2019&dimensionAtObservation=AllDimensions&format=csvfilewithlabels'
$internetUrl = 'https://api.worldbank.org/v2/country/all/indicator/IT.NET.USER.ZS?format=json&per_page=20000&date=2022:2025'
$gdpUrl = 'https://api.worldbank.org/v2/country/all/indicator/NY.GDP.PCAP.PP.KD?format=json&per_page=20000&date=2022:2025'

if (-not (Test-Path -LiteralPath (Join-Path $raw 'world_bank_gtmi_2025.xlsx'))) {
    Invoke-WebRequest -Uri $gtmiUrl -Headers $headers -OutFile (Join-Path $raw 'world_bank_gtmi_2025.xlsx') -UseBasicParsing
}
if (-not (Test-Path -LiteralPath (Join-Path $raw 'uci_news_social_popularity_432.zip'))) {
    Invoke-WebRequest -Uri $uciUrl -Headers $headers -OutFile (Join-Path $raw 'uci_news_social_popularity_432.zip') -UseBasicParsing
}
Invoke-WebRequest -Uri $oecdUrl -Headers (@{ 'User-Agent' = $headers['User-Agent']; 'Accept' = 'text/csv;version=2.0.0' }) -OutFile (Join-Path $raw 'oecd_trust_security_dignity_2025.csv') -UseBasicParsing
Invoke-WebRequest -Uri $internetUrl -Headers $headers -OutFile (Join-Path $raw 'world_bank_internet_2022_2025.json') -UseBasicParsing
Invoke-WebRequest -Uri $gdpUrl -Headers $headers -OutFile (Join-Path $raw 'world_bank_gdp_ppp_per_capita_2022_2025.json') -UseBasicParsing

$uciFolder = Join-Path $raw 'uci432'
if (Test-Path -LiteralPath $uciFolder) {
    $resolved = [System.IO.Path]::GetFullPath($uciFolder)
    if (-not $resolved.StartsWith($raw, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe extraction target: $resolved"
    }
} else {
    New-Item -ItemType Directory -Path $uciFolder | Out-Null
}
Expand-Archive -LiteralPath (Join-Path $raw 'uci_news_social_popularity_432.zip') -DestinationPath $uciFolder -Force

Get-ChildItem -LiteralPath $raw -File | Select-Object Name,Length
