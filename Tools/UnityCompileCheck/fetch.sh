#!/usr/bin/env bash
# Downloads the reference material for the compile check into .cache/ (not committed):
#  - UnityEngine module reference assemblies (NuGet "UnityEngine.Modules", Unity 2021.3 API)
#  - uGUI and TextMeshPro package source (public GitHub mirrors of the Unity packages)
# Everything here is only used to COMPILE the game scripts outside the Unity Editor.
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p .cache
cd .cache
if [ ! -d unityengine.modules ]; then
  curl -sSL -o unityengine.modules.nupkg https://api.nuget.org/v3-flatcontainer/unityengine.modules/2021.3.33/unityengine.modules.2021.3.33.nupkg
  unzip -q -o unityengine.modules.nupkg -d unityengine.modules
fi
[ -d ugui ] || git clone -q --depth 1 --branch "1.0.0/Unity-2021.1.17f1" https://github.com/needle-mirror/com.unity.ugui ugui
[ -d tmp ] || git clone -q --depth 1 --branch "3.2.0-pre.9" https://github.com/needle-mirror/com.unity.textmeshpro tmp
echo "reference material ready in $(pwd)"
