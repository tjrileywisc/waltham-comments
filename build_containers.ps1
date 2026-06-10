$ErrorActionPreference = "Stop"
$root = $PSScriptRoot

$images = @(
    @{ tag = "transcription-service"; dockerfile = "$root\transcription-service\Dockerfile"; context = $root },
    @{ tag = "meeting-downloader";    dockerfile = "$root\meeting-downloader\Dockerfile";    context = $root },
    @{ tag = "embeddings-service";    dockerfile = "$root\embeddings-service\Dockerfile";    context = $root },
    @{ tag = "comments-web";          dockerfile = "$root\webapp\Dockerfile";                context = "$root\webapp" }
)

foreach ($image in $images) {
    Write-Host "Building $($image.tag)..."
    docker build -f $image.dockerfile -t $image.tag $image.context
    if ($LASTEXITCODE -ne 0) { throw "docker build failed for $($image.tag)" }

    Write-Host "Loading $($image.tag) into minikube..."
    $tar = "$env:TEMP\$($image.tag).tar"
    docker save $image.tag -o $tar
    minikube image load $tar --overwrite=true
    Remove-Item $tar
}
