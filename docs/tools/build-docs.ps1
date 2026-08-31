<#
.SYNOPSIS
    Build the submission .docx / .pdf from their Markdown sources.

.DESCRIPTION
    Markdown is the single source of truth. Every .docx and .pdf under
    docs/submission/ is a build artefact of this script and is never edited by
    hand — a hand edit is lost on the next run, silently, which is exactly the
    four-format drift this script exists to end.

    Pipeline, per manifest entry:

        <source>.md  --preprocess-->  a temp .md
                     --officecli-->   docs/submission/<output>.docx
                     --Word COM-->    docs/submission/<output>.pdf

    Two external tools, both verified present on the build host before this was
    written. Neither is optional and neither has a fallback:

      * officecli — https://github.com/…/OfficeCLI, on PATH. Its `docx`
        `markdown` element expands a Markdown subset into native Word elements.
        There is no pandoc, no libreoffice and no soffice on this host, so this
        is the only route from Markdown to .docx.
      * Microsoft Word, via COM (`Word.Application`). The only PDF exporter
        available here. `-NoPdf` skips it — useful on a host without Word, and
        the .docx still builds.

.PARAMETER Only
    Build just the entries whose source path or output name contains this
    substring. Case-insensitive.

.PARAMETER OutDir
    Where artefacts land. Default: docs/submission/ under the repo root.

.PARAMETER ManifestFile
    Which manifest to build. A bare file name resolves inside docs/tools/; an
    absolute or relative path is taken as given. Default: manifest.json. This
    exists because the repository ships more than one document set — see
    manifest-v2.json — and each set has its own OutDir.

.PARAMETER NoPdf
    Build .docx only. Skips Word entirely.

.PARAMETER KeepIntermediate
    Keep the preprocessed .md files instead of deleting them. For debugging a
    document that came out wrong — the preprocessed file is what officecli
    actually saw.

.EXAMPLE
    pwsh docs/tools/build-docs.ps1

.EXAMPLE
    pwsh docs/tools/build-docs.ps1 -Only USER-GUIDE -NoPdf

.EXAMPLE
    pwsh docs/tools/build-docs.ps1 -ManifestFile manifest-v2.json -OutDir docs/submission-v2
#>

[CmdletBinding()]
param(
    [string] $Only,
    [string] $OutDir,
    [string] $ManifestFile,
    [switch] $NoPdf,
    [switch] $KeepIntermediate
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

# ---------------------------------------------------------------- paths

$toolsDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$repoRoot = Resolve-Path (Join-Path $toolsDir '..\..')
if (-not $ManifestFile) { $ManifestFile = 'manifest.json' }
# A bare file name lives in docs/tools/; anything with a separator is a path.
$manifestPath = if ($ManifestFile -eq (Split-Path -Leaf $ManifestFile)) {
    Join-Path $toolsDir $ManifestFile
} else {
    $ManifestFile
}
if (-not (Test-Path $manifestPath)) {
    throw "Manifest not found: $manifestPath"
}
$manifestPath = (Resolve-Path $manifestPath).Path

if (-not $OutDir) { $OutDir = Join-Path $repoRoot 'docs\submission' }
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir | Out-Null }
$OutDir = (Resolve-Path $OutDir).Path

# ---------------------------------------------------------------- tooling

$officecli = (Get-Command officecli -ErrorAction SilentlyContinue)?.Source
if (-not $officecli) {
    throw "officecli is not on PATH. It is the only Markdown-to-.docx route on this host (no pandoc, no libreoffice). Install it and re-run."
}

# ---------------------------------------------------------------- preprocess

$script:LinkPattern = @'
(?<code>`+[^`]*`+)|(?<img>!\[(?<alt>[^\]]*)\]\([^)]*\))|(?<web>\[(?<wtext>[^\]]+)\]\((?<url>https?://[^)\s]+)\))|(?<rel>\[(?<rtext>[^\]]+)\]\([^)\s]*\))
'@.Trim()

$script:LinkEvaluator = [System.Text.RegularExpressions.MatchEvaluator] {
    param($m)
    if ($m.Groups['code'].Success) { return $m.Value }                                   # untouched
    if ($m.Groups['img'].Success)  { return $m.Groups['alt'].Value }                      # no picture is embedded
    if ($m.Groups['web'].Success)  { return "$($m.Groups['wtext'].Value) ($($m.Groups['url'].Value))" }
    return $m.Groups['rtext'].Value                                                       # relative / anchor / mailto
}

function Convert-MarkdownForOfficeCli {
    <#
        officecli's Markdown expansion degrades links to their visible text
        only: `[t](u)` keeps `t` and drops `u` entirely, and `![a](u)` becomes
        the literal `!a`. In a printed submission document a URL that vanishes
        is worse than a URL that is ugly, so links are rewritten HERE, before
        officecli ever sees them:

          * an http(s) link      -> `text (url)`   — the URL survives in print
          * a relative .md link  -> `text`          — the path means nothing to
                                                      a PDF reader, and the
                                                      document it points at is
                                                      in the same bundle
          * an anchor link       -> `text`          — same reason
          * an image             -> `alt`           — no picture is embedded, so
                                                      the leading `!` officecli
                                                      would leave behind is just
                                                      noise

        Code spans and fenced code blocks are left alone: a link inside them is
        sample text, not a link. One known edge: a multi-backtick span that
        itself contains a single-backtick span (``a `[b](c)` d``) is only
        protected at its outer boundary, so a link nested that deep is still
        rewritten. It has never appeared in these documents; the fix would be a
        real CommonMark inline parser, which this is deliberately not.
    #>
    param([string[]] $Lines)

    $out = [System.Collections.Generic.List[string]]::new()
    $inFence = $false

    foreach ($line in $Lines) {
        if ($line -match '^\s*(```|~~~)') {
            $inFence = -not $inFence
            $out.Add($line)
            continue
        }
        if ($inFence) { $out.Add($line); continue }

        # One pass, alternation ordered so the first branch wins: a code span is
        # matched BEFORE any link shape, which is what keeps `[t](u)` inside
        # backticks intact. Doing this as three sequential Replace calls looks
        # simpler and is wrong — each one would reach inside code spans.
        #
        # Images come before links for the same reason in miniature: an image is
        # a link with a `!` in front, so matching the link shape first would
        # strip `(url)` and leave `!alt` behind.
        $out.Add([regex]::Replace($line, $script:LinkPattern, $script:LinkEvaluator))
    }

    return $out
}

# ---------------------------------------------------------------- docx

# A blank officecli document carries no heading styles, so its Markdown
# expansion references `Heading1`/`Heading2`/… as-is and warns that they are
# missing. Word still renders those paragraphs — it falls back to direct
# formatting — but they are `Normal` as far as the file is concerned, which
# costs the navigation pane, any table of contents, and the PDF bookmark tree.
#
# So the styles are DEFINED first, before the Markdown is added. Naming them
# `heading N` is what makes Word treat them as its own built-ins rather than as
# five custom styles that merely look like headings; `outlineLvl` is what puts
# them in the bookmark tree.
$HEADING_STYLES = @(
    @{ Id = 'Heading1'; Name = 'heading 1'; Level = 0; Size = '20pt';   Before = '20pt'; After = '8pt' }
    @{ Id = 'Heading2'; Name = 'heading 2'; Level = 1; Size = '15pt';   Before = '16pt'; After = '6pt' }
    @{ Id = 'Heading3'; Name = 'heading 3'; Level = 2; Size = '12.5pt'; Before = '13pt'; After = '5pt' }
    @{ Id = 'Heading4'; Name = 'heading 4'; Level = 3; Size = '11pt';   Before = '11pt'; After = '4pt' }
    @{ Id = 'Heading5'; Name = 'heading 5'; Level = 4; Size = '11pt';   Before = '10pt'; After = '4pt' }
    @{ Id = 'Heading6'; Name = 'heading 6'; Level = 5; Size = '11pt';   Before = '10pt'; After = '4pt' }
)

function Add-HeadingStyles {
    param([string] $DocxPath)

    foreach ($h in $HEADING_STYLES) {
        & $officecli add $DocxPath /styles --type style `
            --prop "id=$($h.Id)" `
            --prop "name=$($h.Name)" `
            --prop 'type=paragraph' `
            --prop 'basedOn=Normal' `
            --prop 'next=Normal' `
            --prop "outlineLvl=$($h.Level)" `
            --prop "size=$($h.Size)" `
            --prop 'bold=true' `
            --prop "spaceBefore=$($h.Before)" `
            --prop "spaceAfter=$($h.After)" `
            --prop 'keepNext=true' `
            --prop 'keepLines=true' `
            --prop 'qFormat=true' *> $null
        if ($LASTEXITCODE -ne 0) { throw "officecli add style $($h.Id) failed for $DocxPath (exit $LASTEXITCODE)" }
    }
}

function New-Docx {
    param(
        [string] $MarkdownPath,
        [string] $DocxPath
    )

    # officecli `create` refuses an existing file, and refuses one a live
    # resident still holds. The documented reliable idiom is
    # close -> rm -> create -> add -> close, and the `rm` must come BEFORE the
    # `create`: with the on-disk file gone, create auto-closes a resident still
    # pinning that path.
    & $officecli close $DocxPath *> $null
    if (Test-Path $DocxPath) { Remove-Item -LiteralPath $DocxPath -Force }

    & $officecli create $DocxPath
    if ($LASTEXITCODE -ne 0) { throw "officecli create failed for $DocxPath (exit $LASTEXITCODE)" }

    Add-HeadingStyles -DocxPath $DocxPath

    & $officecli add $DocxPath / --type markdown --prop "src=$MarkdownPath"
    if ($LASTEXITCODE -ne 0) { throw "officecli add --type markdown failed for $DocxPath (exit $LASTEXITCODE)" }

    # Flush and release the handle — Word is about to open this file, and a
    # live resident would otherwise hand it the pre-edit bytes.
    & $officecli close $DocxPath
    if ($LASTEXITCODE -ne 0) { throw "officecli close failed for $DocxPath (exit $LASTEXITCODE)" }
}

# ---------------------------------------------------------------- pdf

function Export-Pdf {
    param(
        [System.Collections.Generic.List[object]] $Pairs   # @{ Docx; Pdf }
    )

    # One Word instance for the whole batch. Starting it costs seconds; starting
    # it once per document costs that many times over.
    $word = $null
    try {
        $word = New-Object -ComObject Word.Application
        $word.Visible = $false
        $word.DisplayAlerts = 0   # wdAlertsNone

        foreach ($p in $Pairs) {
            if (Test-Path $p.Pdf) { Remove-Item -LiteralPath $p.Pdf -Force }

            $doc = $word.Documents.Open($p.Docx, $false, $true)   # ReadOnly
            try {
                # 17 = wdExportFormatPDF
                $doc.ExportAsFixedFormat($p.Pdf, 17)
            }
            finally {
                $doc.Close(0)   # wdDoNotSaveChanges
                [System.Runtime.InteropServices.Marshal]::ReleaseComObject($doc) | Out-Null
            }

            Write-Host ("      pdf   {0}" -f (Split-Path -Leaf $p.Pdf)) -ForegroundColor DarkGray
        }
    }
    finally {
        if ($word) {
            $word.Quit()
            [System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
        }
    }
}

# ---------------------------------------------------------------- run

$manifest = Get-Content -LiteralPath $manifestPath -Raw -Encoding UTF8 | ConvertFrom-Json

if ($Only) {
    $manifest = @($manifest | Where-Object {
        $_.source -like "*$Only*" -or $_.output -like "*$Only*"
    })
    if ($manifest.Count -eq 0) { throw "No manifest entry matches -Only '$Only'." }
}

Write-Host "EmeHub — building submission documents" -ForegroundColor Cyan
Write-Host ("  out: {0}" -f $OutDir) -ForegroundColor DarkGray
Write-Host ''

$pdfPairs = [System.Collections.Generic.List[object]]::new()
$temps = [System.Collections.Generic.List[string]]::new()

foreach ($entry in $manifest) {
    $srcPath = Join-Path $repoRoot $entry.source
    if (-not (Test-Path $srcPath)) {
        throw "Manifest lists '$($entry.source)' but it does not exist. Fix the manifest or write the document."
    }

    Write-Host ("  {0}" -f $entry.source) -ForegroundColor White

    $lines = Get-Content -LiteralPath $srcPath -Encoding UTF8
    $processed = Convert-MarkdownForOfficeCli -Lines $lines

    $tempMd = Join-Path ([System.IO.Path]::GetTempPath()) ("emehub-doc-{0}.md" -f ([guid]::NewGuid().ToString('N')))
    # UTF-8 without BOM — officecli reads the file as text and a BOM would land
    # in the first heading.
    [System.IO.File]::WriteAllLines($tempMd, $processed, (New-Object System.Text.UTF8Encoding($false)))
    $temps.Add($tempMd)

    $docx = Join-Path $OutDir ("{0}.docx" -f $entry.output)
    New-Docx -MarkdownPath $tempMd -DocxPath $docx
    Write-Host ("      docx  {0}" -f (Split-Path -Leaf $docx)) -ForegroundColor DarkGray

    if (-not $NoPdf) {
        $pdfPairs.Add(@{
            Docx = $docx
            Pdf  = (Join-Path $OutDir ("{0}.pdf" -f $entry.output))
        })
    }
}

if ($pdfPairs.Count -gt 0) {
    Write-Host ''
    Write-Host "  exporting PDF via Word" -ForegroundColor White
    Export-Pdf -Pairs $pdfPairs
}

if (-not $KeepIntermediate) {
    foreach ($t in $temps) { if (Test-Path $t) { Remove-Item -LiteralPath $t -Force } }
} else {
    Write-Host ''
    Write-Host "  intermediate Markdown kept:" -ForegroundColor DarkGray
    foreach ($t in $temps) { Write-Host ("    {0}" -f $t) -ForegroundColor DarkGray }
}

Write-Host ''
Write-Host ("Done — {0} document(s)." -f $manifest.Count) -ForegroundColor Green
