# Unity compile check (no Unity Editor required)

The Unity Editor cannot run in every environment (for example a cloud container without a
Unity licence). This folder compiles the game's Unity scripts with the normal .NET SDK so
that typing mistakes and wrong API calls are caught early. **It does not replace opening the
project in Unity** - it cannot run scenes, shaders, import assets or build an APK.

What it compiles against:

| Dependency | Source used here | Notes |
|---|---|---|
| UnityEngine modules | NuGet `UnityEngine.Modules` 2021.3.33 (reference DLLs) | Older than Unity 6.3; APIs the game uses were also checked in Unity's C# reference source (tag 6000.3.9f1). |
| uGUI (`UnityEngine.UI`) | Real source, public mirror `needle-mirror/com.unity.ugui` 1.0.0 | Unity 6 ships uGUI 2.0; the parts used are unchanged. |
| TextMeshPro | Real source, public mirror `needle-mirror/com.unity.textmeshpro` 3.2.0-pre.9 | Unity 6 merges TMP 3.2 into uGUI 2.0. |
| Input System | `Stubs/Unity.InputSystem` (hand-written, 3 types) | Checked against the 1.20.0 package source. |
| Missing engine bits | `Stubs/UnityEngine.Supplement` | `Handheld.Vibrate` (absent from the desktop reference DLLs). |
| Newtonsoft.Json | NuGet 13.0.3 | Same major version as `com.unity.nuget.newtonsoft-json` 3.2. |

Variants (scripting defines):

* **Editor** - Unity Editor, Android target, Input System active, development build.
* **Player** - Android release player: no editor-only code, no development mocks.
* **Legacy** - only the old Input Manager backend active.

Run it:

```bash
Tools/UnityCompileCheck/check.sh
```

The first run downloads about 100 MB of reference material into `.cache/` (ignored by git).
