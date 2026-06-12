
minikube start
kubectl config use-context minikube

:: secrets in env file
kubectl create secret generic waltham-comments-env --from-env-file=.env

pwsh .\build_containers.ps1

:: ensure host directories exist before mounting
mkdir "C:\workspace\waltham-comments\models" 2>nul
mkdir "C:\workspace\waltham-comments\videos" 2>nul
mkdir "C:\workspace\waltham-comments\audio" 2>nul
mkdir "C:\workspace\waltham-comments\transcriptions" 2>nul
mkdir "C:\workspace\waltham-comments\data" 2>nul

:: minikube runs in a linux container, so these need to be mounted to a linux path first
start "models-mount" minikube mount "C:/workspace/waltham-comments/models:/host/models"
start "videos-mount" minikube mount "C:/workspace/waltham-comments/videos:/host/videos"
start "audio-mount" minikube mount "C:/workspace/waltham-comments/audio:/host/audio"
start "transcriptions-mount" minikube mount "C:/workspace/waltham-comments/transcriptions:/host/transcriptions"
start "data-mount" minikube mount "C:/workspace/waltham-comments/data:/host/data"

:: poll until all 5 mount points are visible inside minikube
echo Waiting for mounts to establish...
:wait_loop
minikube ssh -- "test -d /host/models && test -d /host/videos && test -d /host/audio && test -d /host/transcriptions && test -d /host/data" 2>nul
if errorlevel 1 (
    timeout /t 2 >nul
    goto wait_loop
)
echo Mounts ready.

kubectl apply -f ./spec.yaml
