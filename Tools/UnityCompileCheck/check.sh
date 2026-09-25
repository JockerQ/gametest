#!/usr/bin/env bash
# Compiles the Unity game scripts outside the Unity Editor (see README.md).
# Usage: Tools/UnityCompileCheck/check.sh        -> exit code 0 when every variant compiles
set -euo pipefail
cd "$(dirname "$0")"
# global.json here selects a .NET 8 SDK, the version this check was verified with (GitHub
# runners would otherwise use their newest SDK).
echo "dotnet SDK $(dotnet --version)"
./fetch.sh
status=0
for variant in Editor Player Legacy; do
  echo "== EvilCats.Game ($variant)"
  if ! dotnet build EvilCats.Game/EvilCats.Game.csproj -c Release -nologo -v:q -p:Variant=$variant -o "bin/$variant" 2>&1 | grep -E "error|warning (CS|MSB|NU|NETSDK)|Build succeeded" | sort -u; then status=1; fi
  [ -f "bin/$variant/EvilCats.Game.dll" ] || status=1
done
echo "== EvilCats.Editor (setup, import, build and validation tools)"
dotnet build EvilCats.Editor/EvilCats.Editor.csproj -c Release -nologo -v:q -o bin/EditorTools 2>&1 | grep -E "error|warning (CS|MSB|NU|NETSDK)|Build succeeded" | sort -u || status=1
[ -f bin/EditorTools/EvilCats.Editor.dll ] || status=1
echo "== Unity-only tests (EditMode/Game + PlayMode)"
dotnet build EvilCats.Tests/EvilCats.Tests.csproj -c Release -nologo -v:q -o bin/Tests 2>&1 | grep -E "error|warning (CS|MSB|NU|NETSDK)|Build succeeded" | sort -u || status=1
[ -f bin/Tests/EvilCats.Tests.UnityOnly.dll ] || status=1
if [ $status -ne 0 ]; then
  # repeated at the end so it is visible in the tail of a long CI log
  echo "compile check FAILED (dotnet SDK $(dotnet --version); $(ls .cache/unityengine.modules/lib/netstandard2.0/*.dll 2>/dev/null | wc -l) UnityEngine reference assemblies)"
fi
exit $status
