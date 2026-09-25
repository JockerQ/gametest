using System;
using System.Collections.Generic;
using System.IO;
using System.Reflection;
using System.Text;
using EvilCats.Game;
using TMPro;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;

namespace EvilCats.EditorTools
{
    /// <summary>
    /// "Evil Cats > 1. Set Up Project": prepares a freshly opened project so it can be played and
    /// built without manual clicks. Every step is idempotent (safe to run any number of times) and
    /// never overwrites values the owner changed on purpose (for example the application id).
    ///
    ///  1. folders                    6. Boot / Hub / Battle scenes + Build Settings
    ///  2. import settings            7. player settings (name, version, portrait, Android, icons)
    ///  3. TextMeshPro resources      8. quality settings
    ///  4. pixel font assets          9. input backend = Input System package (restart prompt)
    ///  5. URP with the 2D Renderer + unlit sprite material (falls back to the built-in renderer)
    ///
    /// Command line (CI): Unity -batchmode -quit -projectPath EvilCats -executeMethod EvilCats.EditorTools.ProjectSetup.RunBatch
    /// </summary>
    public static class ProjectSetup
    {
        public const string Root = "Assets/_EvilCats";
        public const string ScenesDir = Root + "/Scenes";
        public const string SettingsDir = Root + "/Settings";
        public const string MaterialsDir = Root + "/Art/Resources/ECArt/Materials";
        public const string SpriteMaterialPath = MaterialsDir + "/EC_SpriteUnlit.mat";
        public const string FontDir = Root + "/UI/Resources/ECUI/Fonts";
        public const string UrpAssetPath = SettingsDir + "/EC_URP_2D.asset";
        public const string UrpRendererPath = SettingsDir + "/EC_URP_2D_Renderer.asset";
        public static readonly string[] SceneNames = { GameApp.BootScene, GameApp.HubScene, GameApp.BattleScene };
        /// <summary>Placeholder application id; the owner must choose their own before publishing.</summary>
        public const string PlaceholderAppId = "com.evilcats.arclightcat";

        private enum Outcome { Done, AlreadyOk, Pending, Failed }

        private sealed class Report
        {
            public readonly List<(string step, Outcome outcome, string note)> Lines = new List<(string, Outcome, string)>();
            public bool NeedsRestart;
            public bool Failed => Lines.Exists(l => l.outcome == Outcome.Failed);
            public bool Pending => Lines.Exists(l => l.outcome == Outcome.Pending);

            public override string ToString()
            {
                var sb = new StringBuilder("[EvilCats] Project setup\n");
                foreach (var (step, outcome, note) in Lines)
                    sb.Append("  ").Append(outcome.ToString().PadRight(9)).Append(step).Append(string.IsNullOrEmpty(note) ? "" : " - " + note).Append('\n');
                if (NeedsRestart) sb.Append("  -> Restart the Unity Editor so the input backend change takes effect.\n");
                if (Pending) sb.Append("  -> Some steps wait for an import to finish; setup runs again automatically, or run it once more.\n");
                return sb.ToString();
            }
        }

        private static bool _running, _rerunScheduled;
        /// <summary>After the last run: some step is waiting for an import to finish.</summary>
        public static bool LastRunPending { get; private set; }
        /// <summary>After the last run: the Editor must restart before building (input backend changed).</summary>
        public static bool LastRunNeedsRestart { get; private set; }

        [MenuItem("Evil Cats/1. Set Up Project", priority = 1)]
        public static void RunFromMenu() => Run(true);

        public static void RunBatch()
        {
            if (!Run(false)) EditorApplication.Exit(1);
        }

        public static bool Run(bool interactive)
        {
            if (_running) return false;
            _running = true;
            var r = new Report();
            try
            {
                if (interactive && !EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())
                {
                    Debug.Log("[EvilCats] Setup cancelled (unsaved scene changes were kept).");
                    return false;
                }
                Step(r, "Folders", EnsureFolders);
                Step(r, "Texture and audio import settings", ApplyImportSettings);
                Step(r, "TextMeshPro essential resources", EnsureTmpEssentials);
                Step(r, "Pixel font assets", EnsureFontAssets);
                Step(r, "Render pipeline (URP 2D Renderer)", EnsureRenderPipeline);
                Step(r, "Sprite material", EnsureSpriteMaterial);
                Step(r, "Scenes and Build Settings", EnsureScenes);
                Step(r, "Player settings", ApplyPlayerSettings);
                Step(r, "Quality settings", ApplyQualitySettings);
                Step(r, "Input backend", () => EnsureInputSystemBackend(r));
                AssetDatabase.SaveAssets();
                LastRunPending = r.Pending;
                LastRunNeedsRestart = r.NeedsRestart;
                if (r.Failed) Debug.LogError(r.ToString());
                else Debug.Log(r.ToString());
                if (interactive)
                {
                    string msg = r.Failed ? "Setup finished with problems. See the Console for details."
                        : r.Pending ? "Setup is waiting for TextMeshPro resources to import. It will continue automatically."
                        : "Setup complete. Open Assets/_EvilCats/Scenes/Boot and press Play.";
                    if (r.NeedsRestart)
                    {
                        if (EditorUtility.DisplayDialog("Evil Cats", msg + "\n\nThe input backend was switched to the Input System package. Unity must restart to apply it.", "Restart now", "Later"))
                            EditorApplication.OpenProject(Directory.GetCurrentDirectory());
                    }
                    else EditorUtility.DisplayDialog("Evil Cats", msg, "OK");
                }
                return !r.Failed;
            }
            finally
            {
                _running = false;
            }
        }

        private static void Step(Report r, string name, Func<(Outcome, string)> action)
        {
            try
            {
                var (o, note) = action();
                r.Lines.Add((name, o, note));
            }
            catch (Exception e)
            {
                Debug.LogException(e);
                r.Lines.Add((name, Outcome.Failed, e.Message));
            }
        }

        // -----------------------------------------------------------------------------------------
        private static (Outcome, string) EnsureFolders()
        {
            bool made = false;
            foreach (var dir in new[] { ScenesDir, SettingsDir, MaterialsDir })
                made |= EnsureFolder(dir);
            return made ? (Outcome.Done, null) : (Outcome.AlreadyOk, null);
        }

        private static bool EnsureFolder(string path)
        {
            if (AssetDatabase.IsValidFolder(path)) return false;
            string parent = Path.GetDirectoryName(path).Replace('\\', '/');
            if (!AssetDatabase.IsValidFolder(parent)) EnsureFolder(parent);
            AssetDatabase.CreateFolder(parent, Path.GetFileName(path));
            return true;
        }

        private static (Outcome, string) ApplyImportSettings()
        {
            int fixedCount = 0;
            foreach (var guid in AssetDatabase.FindAssets("t:Texture2D", new[] { Root + "/Art", Root + "/UI" }))
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                if (AssetImporter.GetAtPath(path) is TextureImporter ti && ImportRules.IsGameTexture(path) && !ImportRules.Matches(ti))
                {
                    ImportRules.Apply(ti);
                    ti.SaveAndReimport();
                    fixedCount++;
                }
            }
            foreach (var guid in AssetDatabase.FindAssets("t:AudioClip", new[] { Root + "/Audio" }))
            {
                string path = AssetDatabase.GUIDToAssetPath(guid);
                bool music = ImportRules.IsMusic(path);
                if (AssetImporter.GetAtPath(path) is AudioImporter ai && !ImportRules.Matches(ai, music))
                {
                    ImportRules.Apply(ai, music);
                    ai.SaveAndReimport();
                    fixedCount++;
                }
            }
            return fixedCount > 0 ? (Outcome.Done, fixedCount + " assets re-imported") : (Outcome.AlreadyOk, null);
        }

        // ---- TextMeshPro --------------------------------------------------------------------------
        private static bool TmpReady => AssetDatabase.FindAssets("t:TMP_Settings").Length > 0 && Shader.Find("TextMeshPro/Distance Field") != null;

        private static (Outcome, string) EnsureTmpEssentials()
        {
            if (TmpReady) return (Outcome.AlreadyOk, null);
            // Unity 6 ships TextMeshPro inside uGUI 2.0; older setups had a separate package.
            string[] candidates =
            {
                "Packages/com.unity.ugui/Package Resources/TMP Essential Resources.unitypackage",
                "Packages/com.unity.textmeshpro/Package Resources/TMP Essential Resources.unitypackage",
            };
            foreach (var c in candidates)
            {
                string full = Path.GetFullPath(c);
                if (!File.Exists(full)) continue;
                if (!_rerunScheduled)
                {
                    _rerunScheduled = true;
                    AssetDatabase.importPackageCompleted += OnTmpImported;
                }
                AssetDatabase.ImportPackage(full, false);
                return TmpReady ? (Outcome.Done, null) : (Outcome.Pending, "importing " + Path.GetFileName(full));
            }
            return (Outcome.Failed, "TMP Essential Resources package not found. Use Window > TextMeshPro > Import TMP Essential Resources.");
        }

        private static void OnTmpImported(string packageName)
        {
            AssetDatabase.importPackageCompleted -= OnTmpImported;
            _rerunScheduled = false;
            // continue the remaining steps once the imported shaders and settings exist
            EditorApplication.delayCall += () => Run(!Application.isBatchMode);
        }

        private static (Outcome, string) EnsureFontAssets()
        {
            if (!TmpReady) return (Outcome.Pending, "waiting for TextMeshPro resources");
            int made = 0;
            foreach (var name in new[] { "PixelifySans-Regular", "PixelifySans-Bold" })
            {
                string fontPath = FontDir + "/" + name + ".ttf";
                string assetPath = FontDir + "/" + name + " SDF.asset";
                if (AssetDatabase.LoadAssetAtPath<TMP_FontAsset>(assetPath) != null) continue;
                var font = AssetDatabase.LoadAssetAtPath<Font>(fontPath);
                if (font == null) return (Outcome.Failed, "missing " + fontPath);
                // Dynamic SDF font asset: glyphs are added on demand, so every character in the
                // string table works without a fixed character set.
                var fa = TMP_FontAsset.CreateFontAsset(font);   // dynamic SDF, 1024x1024 atlas
                if (fa == null) return (Outcome.Failed, "could not create a font asset from " + fontPath);
                fa.name = name + " SDF";
                AssetDatabase.CreateAsset(fa, assetPath);
                if (fa.atlasTextures != null && fa.atlasTextures.Length > 0 && fa.atlasTextures[0] != null)
                {
                    fa.atlasTextures[0].name = name + " Atlas";
                    AssetDatabase.AddObjectToAsset(fa.atlasTextures[0], fa);
                }
                if (fa.material != null)
                {
                    fa.material.name = name + " Material";
                    AssetDatabase.AddObjectToAsset(fa.material, fa);
                }
                EditorUtility.SetDirty(fa);
                made++;
            }
            AssetDatabase.SaveAssets();
            return made > 0 ? (Outcome.Done, made + " created") : (Outcome.AlreadyOk, null);
        }

        // ---- Render pipeline ------------------------------------------------------------------------
        /// <summary>
        /// Creates "URP Asset (with 2D Renderer)" exactly like Unity's own menu does (URP 17.3:
        /// Renderer2DMenus.CreateRendererAsset + UniversalRenderPipelineAsset.Create), through
        /// reflection so this script still compiles if the URP package is missing. If anything
        /// fails, the game keeps working on the built-in renderer (it only draws unlit sprites).
        /// </summary>
        private static (Outcome, string) EnsureRenderPipeline()
        {
            var asset = AssetDatabase.LoadAssetAtPath<RenderPipelineAsset>(UrpAssetPath);
            bool created = false;
            if (asset == null)
            {
                var urpType = Type.GetType("UnityEngine.Rendering.Universal.UniversalRenderPipelineAsset, Unity.RenderPipelines.Universal.Runtime");
                var dataType = Type.GetType("UnityEngine.Rendering.Universal.ScriptableRendererData, Unity.RenderPipelines.Universal.Runtime");
                var rendererTypeEnum = Type.GetType("UnityEngine.Rendering.Universal.RendererType, Unity.RenderPipelines.Universal.Runtime");
                var menus = Type.GetType("UnityEditor.Rendering.Universal.Renderer2DMenus, Unity.RenderPipelines.Universal.Editor");
                if (urpType == null || dataType == null || rendererTypeEnum == null || menus == null)
                    return (Outcome.Failed, "URP package not found; the game will use the built-in renderer");
                var createRenderer = menus.GetMethod("CreateRendererAsset", BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public);
                var create = urpType.GetMethod("Create", BindingFlags.Static | BindingFlags.Public, null, new[] { dataType }, null);
                if (createRenderer == null || create == null)
                    return (Outcome.Failed, "URP API changed; create 'URP Asset (with 2D Renderer)' manually and assign it in Project Settings > Graphics");
                object rendererData = AssetDatabase.LoadAssetAtPath<ScriptableObject>(UrpRendererPath);
                if (rendererData == null)
                    rendererData = createRenderer.Invoke(null, new object[] { UrpRendererPath, Enum.Parse(rendererTypeEnum, "_2DRenderer"), false, "Renderer" });
                asset = (RenderPipelineAsset)create.Invoke(null, new[] { rendererData });
                AssetDatabase.CreateAsset(asset, UrpAssetPath);
                created = true;
            }
            bool changed = created;
            if (GraphicsSettings.defaultRenderPipeline != asset)
            {
                GraphicsSettings.defaultRenderPipeline = asset;
                changed = true;
            }
            int current = QualitySettings.GetQualityLevel();
            for (int i = 0; i < QualitySettings.names.Length; i++)
            {
                QualitySettings.SetQualityLevel(i, false);
                if (QualitySettings.renderPipeline != null && QualitySettings.renderPipeline != asset)
                {
                    QualitySettings.renderPipeline = asset;
                    changed = true;
                }
            }
            QualitySettings.SetQualityLevel(current, false);
            return changed ? (Outcome.Done, created ? "created " + UrpAssetPath : "assigned") : (Outcome.AlreadyOk, null);
        }

        private static (Outcome, string) EnsureSpriteMaterial()
        {
            bool urp = GraphicsSettings.defaultRenderPipeline != null;
            var shader = Shader.Find(urp ? "Universal Render Pipeline/2D/Sprite-Unlit-Default" : "Sprites/Default");
            if (shader == null) shader = Shader.Find("Sprites/Default");
            if (shader == null) return (Outcome.Failed, "no sprite shader found");
            var mat = AssetDatabase.LoadAssetAtPath<Material>(SpriteMaterialPath);
            if (mat != null && mat.shader == shader) return (Outcome.AlreadyOk, shader.name);
            if (mat == null)
            {
                mat = new Material(shader) { name = "EC_SpriteUnlit" };
                AssetDatabase.CreateAsset(mat, SpriteMaterialPath);
            }
            else
            {
                mat.shader = shader;
                EditorUtility.SetDirty(mat);
            }
            return (Outcome.Done, shader.name);
        }

        // ---- Scenes -----------------------------------------------------------------------------------
        private static (Outcome, string) EnsureScenes()
        {
            int made = 0;
            var previous = SceneManager.GetActiveScene().path;
            foreach (var name in SceneNames)
            {
                string path = ScenesDir + "/" + name + ".unity";
                if (File.Exists(path)) continue;
                var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                // The controller is part of the scene; SceneAttach would also add it at runtime.
                var go = new GameObject(name + "Controller");
                switch (name)
                {
                    case GameApp.BootScene: go.AddComponent<BootController>(); break;
                    case GameApp.HubScene: go.AddComponent<HubController>(); break;
                    default: go.AddComponent<BattleController>(); break;
                }
                EditorSceneManager.SaveScene(scene, path);
                made++;
            }
            var wanted = new List<EditorBuildSettingsScene>();
            foreach (var name in SceneNames) wanted.Add(new EditorBuildSettingsScene(ScenesDir + "/" + name + ".unity", true));
            bool same = EditorBuildSettings.scenes.Length == wanted.Count;
            for (int i = 0; same && i < wanted.Count; i++)
                same = EditorBuildSettings.scenes[i].path == wanted[i].path && EditorBuildSettings.scenes[i].enabled;
            if (!same) EditorBuildSettings.scenes = wanted.ToArray();
            if (made > 0)
            {
                string open = !string.IsNullOrEmpty(previous) && File.Exists(previous) ? previous : ScenesDir + "/" + GameApp.BootScene + ".unity";
                EditorSceneManager.OpenScene(open, OpenSceneMode.Single);
            }
            return made > 0 || !same ? (Outcome.Done, made + " scenes created") : (Outcome.AlreadyOk, null);
        }

        // ---- Player settings -----------------------------------------------------------------------
        private static (Outcome, string) ApplyPlayerSettings()
        {
            var notes = new List<string>();
            if (string.IsNullOrEmpty(PlayerSettings.productName) || PlayerSettings.productName == "EvilCats" || PlayerSettings.productName.StartsWith("New Unity Project", StringComparison.Ordinal))
                PlayerSettings.productName = "Evil Cats";
            if (string.IsNullOrEmpty(PlayerSettings.companyName) || PlayerSettings.companyName == "DefaultCompany")
                PlayerSettings.companyName = "Evil Cats Team";
            string id = PlayerSettings.GetApplicationIdentifier(NamedBuildTarget.Android);
            if (string.IsNullOrEmpty(id) || id.StartsWith("com.DefaultCompany", StringComparison.OrdinalIgnoreCase) || id == "com.Company.ProductName")
            {
                PlayerSettings.SetApplicationIdentifier(NamedBuildTarget.Android, PlaceholderAppId);
                notes.Add("placeholder application id " + PlaceholderAppId + " (change it before publishing)");
            }
            if (PlayerSettings.bundleVersion != GameApp.Version) PlayerSettings.bundleVersion = GameApp.Version;
            if (PlayerSettings.Android.bundleVersionCode < 1) PlayerSettings.Android.bundleVersionCode = 1;

            // portrait only
            PlayerSettings.defaultInterfaceOrientation = UIOrientation.Portrait;
            PlayerSettings.allowedAutorotateToPortrait = true;
            PlayerSettings.allowedAutorotateToPortraitUpsideDown = false;
            PlayerSettings.allowedAutorotateToLandscapeLeft = false;
            PlayerSettings.allowedAutorotateToLandscapeRight = false;
            PlayerSettings.runInBackground = false;

            // Android: 64-bit IL2CPP (required by Google Play), Android 7.0+, no internet permission needed
            if (PlayerSettings.Android.minSdkVersion < AndroidSdkVersions.AndroidApiLevel24) PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel24;
            PlayerSettings.Android.targetSdkVersion = AndroidSdkVersions.AndroidApiLevelAuto;
            PlayerSettings.SetScriptingBackend(NamedBuildTarget.Android, ScriptingImplementation.IL2CPP);
            PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
            PlayerSettings.Android.forceInternetPermission = false;

            ApplyIcons(notes);
            return (Outcome.Done, string.Join("; ", notes));
        }

        private static void ApplyIcons(List<string> notes)
        {
            string dir = Root + "/Art/Icons/";
            var big = AssetDatabase.LoadAssetAtPath<Texture2D>(dir + "launcher_512.png");
            if (big == null) { notes.Add("launcher icons missing (run Tools/art/build_all.py)"); return; }
            PlayerSettings.SetIcons(NamedBuildTarget.Unknown, new[] { big }, IconKind.Application);
            // legacy Android icons: nearest available size for each slot Unity asks for
            int[] sizes = PlayerSettings.GetIconSizes(NamedBuildTarget.Android, IconKind.Application);
            if (sizes != null && sizes.Length > 0)
            {
                var available = new[] { 48, 72, 96, 144, 192, 512 };
                var icons = new Texture2D[sizes.Length];
                for (int i = 0; i < sizes.Length; i++)
                {
                    int best = 512;
                    foreach (var a in available) if (a >= sizes[i]) { best = a; break; }
                    icons[i] = AssetDatabase.LoadAssetAtPath<Texture2D>(dir + "launcher_" + best + ".png");
                }
                PlayerSettings.SetIcons(NamedBuildTarget.Android, icons, IconKind.Application);
            }
            // adaptive icons (Android 8+) live in the Android module; set them only when it is installed
            try
            {
                var kindType = Type.GetType("UnityEditor.Android.AndroidPlatformIconKind, UnityEditor.Android.Extensions");
                var member = kindType?.GetProperty("Adaptive", BindingFlags.Public | BindingFlags.Static)?.GetValue(null)
                             ?? kindType?.GetField("Adaptive", BindingFlags.Public | BindingFlags.Static)?.GetValue(null);
                if (member is PlatformIconKind adaptive)
                {
                    var bg = AssetDatabase.LoadAssetAtPath<Texture2D>(dir + "adaptive_bg_432.png");
                    var fg = AssetDatabase.LoadAssetAtPath<Texture2D>(dir + "adaptive_fg_432.png");
                    var slots = PlayerSettings.GetPlatformIcons(NamedBuildTarget.Android, adaptive);
                    if (bg != null && fg != null && slots != null)
                    {
                        foreach (var s in slots) s.SetTextures(bg, fg);
                        PlayerSettings.SetPlatformIcons(NamedBuildTarget.Android, adaptive, slots);
                    }
                }
                else notes.Add("adaptive icons skipped (Android Build Support not installed)");
            }
            catch (Exception e)
            {
                notes.Add("adaptive icons skipped: " + e.Message);
            }
        }

        private static (Outcome, string) ApplyQualitySettings()
        {
            int current = QualitySettings.GetQualityLevel();
            bool changed = false;
            for (int i = 0; i < QualitySettings.names.Length; i++)
            {
                QualitySettings.SetQualityLevel(i, false);
                if (QualitySettings.vSyncCount != 0) { QualitySettings.vSyncCount = 0; changed = true; }   // the game sets 60 fps itself
            }
            QualitySettings.SetQualityLevel(current, false);
            return changed ? (Outcome.Done, null) : (Outcome.AlreadyOk, null);
        }

        // ---- Input backend ----------------------------------------------------------------------------
        /// <summary>0 = Input Manager (old), 1 = Input System package (new), 2 = both. The game uses the
        /// Input System package through the UI EventSystem; changing this needs an Editor restart.</summary>
        private static (Outcome, string) EnsureInputSystemBackend(Report r)
        {
            var assets = AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/ProjectSettings.asset");
            if (assets == null || assets.Length == 0) return (Outcome.Failed, "ProjectSettings.asset not found");
            var so = new SerializedObject(assets[0]);
            var prop = so.FindProperty("activeInputHandler");
            if (prop == null) return (Outcome.Failed, "activeInputHandler setting not found");
            if (prop.intValue == 1) return (Outcome.AlreadyOk, "Input System package");
            prop.intValue = 1;
            so.ApplyModifiedPropertiesWithoutUndo();
            r.NeedsRestart = true;
            return (Outcome.Done, "switched to the Input System package (restart required)");
        }
    }
}
