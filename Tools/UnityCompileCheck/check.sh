#!/usr/bin/env bash
# Compiles the Unity game scripts outside the Unity Editor (see README.md).
# Usage: Tools/UnityCompileCheck/check.sh        -> exit code 0 when every variant compiles
set -euo pipefail
cd "$(dirname "$0")"
./fetch.sh
status=0
for variant in Editor Player Legacy; do
  echo "== EvilCats.Game ($variant)"
  if ! dotnet build EvilCats.Game/EvilCats.Game.csproj -c Release -nologo -v:q -p:Variant=$variant -o "bin/$variant" 2>&1 | grep -E "error|warning CS|Build succeeded" | sort -u; then status=1; fi
  [ -f "bin/$variant/EvilCats.Game.dll" ] || status=1
done
if [ -d EvilCats.Editor ]; then
  echo "== EvilCats.Editor"
  dotnet build EvilCats.Editor/EvilCats.Editor.csproj -c Release -nologo -v:q -o bin/EditorTools 2>&1 | grep -E "error|warning CS|Build succeeded" | sort -u || status=1
  [ -f bin/EditorTools/EvilCats.Editor.dll ] || status=1
fi
exit $status
