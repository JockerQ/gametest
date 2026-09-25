// Declarations of the UnityEditor members used by Assets/_EvilCats/Editor, so those scripts can be
// compiled outside Unity. Unity does not publish UnityEditor reference assemblies; every member
// below was copied in shape (namespace, type kind, name, parameters) from Unity's C# reference
// source, tag 6000.3.9f1 (github.com/Unity-Technologies/UnityCsReference), files:
//   Editor/Mono/AssetPostprocessor.cs, Editor/Mono/AssetPipeline/AssetImporter.bindings.cs,
//   Editor/Mono/AssetPipeline/TextureImporter*.cs, Modules/AssetPipelineEditor/Public/AudioImporter.bindings.cs,
//   Modules/AssetDatabase/Editor/ScriptBindings/AssetDatabase.bindings.cs, Editor/Mono/AssetDatabase/AssetDatabase.cs,
//   Editor/Mono/EditorApplication*.cs, Editor/Mono/EditorUtility*.cs, Editor/Mono/EditorBuildSettings.bindings.cs,
//   Editor/Mono/PlayerSettings*.cs, Editor/Mono/PlatformSupport/PlayerSettingsPlatformIcons.bindings.cs,
//   Editor/Mono/EditorUserBuildSettings.bindings.cs, Editor/Mono/BuildPipeline.bindings.cs,
//   Editor/Mono/BuildPipeline/NamedBuildTarget.cs, Modules/BuildReportingEditor/Managed/*.cs,
//   Editor/Mono/EditorSceneManager*.cs, Editor/Mono/MenuItem.cs.
// Bodies are empty: this assembly is only compiled against, never run or shipped.
#pragma warning disable CS0067
using System;
using UnityEngine;
using UnityEngine.SceneManagement;
using Object = UnityEngine.Object;

namespace UnityEditor
{
    [AttributeUsage(AttributeTargets.Method, AllowMultiple = true)]
    public sealed class MenuItem : Attribute
    {
        public MenuItem(string itemName) { }
        public MenuItem(string itemName, bool isValidateFunction) { }
        public MenuItem(string itemName, bool isValidateFunction, int priority) { }
        public string menuItem;
        public bool validate;
        public int priority;
    }

    public class AssetPostprocessor
    {
        public string assetPath { get; set; }
        public AssetImporter assetImporter => null;
    }

    public class AssetImporter : Object
    {
        public static AssetImporter GetAtPath(string path) => null;
        public void SaveAndReimport() { }
    }

    public enum TextureImporterType { Default = 0, NormalMap = 1, GUI = 2, Sprite = 8, Cursor = 7, Cookie = 4, Lightmap = 6, SingleChannel = 10, Shadowmask = 11, DirectionalLightmap = 12 }
    public enum TextureImporterNPOTScale { None = 0, ToNearest = 1, ToLarger = 2, ToSmaller = 3 }
    public enum TextureImporterCompression { Uncompressed = 0, Compressed = 1, CompressedHQ = 2, CompressedLQ = 3 }
    public enum TextureImporterAlphaSource { None = 0, FromInput = 1, FromGrayScale = 2 }

    public sealed class TextureImporter : AssetImporter
    {
        public TextureImporterType textureType { get; set; }
        public TextureImporterNPOTScale npotScale { get; set; }
        public bool mipmapEnabled { get; set; }
        public FilterMode filterMode { get; set; }
        public TextureWrapMode wrapMode { get; set; }
        public TextureImporterCompression textureCompression { get; set; }
        public TextureImporterAlphaSource alphaSource { get; set; }
        public bool alphaIsTransparency { get; set; }
        public bool sRGBTexture { get; set; }
        public bool isReadable { get; set; }
        public int maxTextureSize { get; set; }
    }

    public partial struct AudioImporterSampleSettings
    {
        public AudioClipLoadType loadType;
        public AudioCompressionFormat compressionFormat;
        public float quality;
        public bool preloadAudioData;
    }

    public sealed class AudioImporter : AssetImporter
    {
        public AudioImporterSampleSettings defaultSampleSettings { get; set; }
        public bool forceToMono { get; set; }
        public bool loadInBackground { get; set; }
    }

    public static class AssetDatabase
    {
        public delegate void ImportPackageCallback(string packageName);
        public static event ImportPackageCallback importPackageCompleted;
        public static string[] FindAssets(string filter) => null;
        public static string[] FindAssets(string filter, string[] searchInFolders) => null;
        public static string GUIDToAssetPath(string guid) => null;
        public static T LoadAssetAtPath<T>(string assetPath) where T : Object => null;
        public static Object[] LoadAllAssetsAtPath(string assetPath) => null;
        public static void CreateAsset(Object asset, string path) { }
        public static void AddObjectToAsset(Object objectToAdd, Object assetObject) { }
        public static void SaveAssets() { }
        public static bool IsValidFolder(string path) => false;
        public static string CreateFolder(string parentFolder, string newFolderName) => null;
        public static void ImportPackage(string packagePath, bool interactive) { }
    }

    public sealed partial class EditorApplication
    {
        public delegate void CallbackFunction();
        public static CallbackFunction delayCall;
        public static void Exit(int returnValue) { }
        public static void OpenProject(string projectPath, params string[] args) { }
    }

    public sealed partial class EditorUtility
    {
        public static bool DisplayDialog(string title, string message, string ok) => false;
        public static bool DisplayDialog(string title, string message, string ok, string cancel) => false;
        public static void SetDirty(Object target) { }
        public static void RevealInFinder(string path) { }
    }

    public class EditorBuildSettingsScene : IComparable
    {
        public EditorBuildSettingsScene() { }
        public EditorBuildSettingsScene(string path, bool enabled) { }
        public bool enabled { get; set; }
        public string path { get; set; }
        public int CompareTo(object obj) => 0;
    }

    public partial class EditorBuildSettings : Object
    {
        public static EditorBuildSettingsScene[] scenes { get; set; }
    }

    public enum UIOrientation { Portrait = 0, PortraitUpsideDown = 1, LandscapeRight = 2, LandscapeLeft = 3, AutoRotation = 4 }
    public enum ScriptingImplementation { Mono2x = 0, IL2CPP = 1, WinRTDotNET = 2 }
    public enum IconKind { Any = -1, Application = 0, Settings = 1, Notification = 2, Spotlight = 3, Store = 4 }
    [Flags] public enum AndroidArchitecture : uint { None = 0, ARMv7 = 1 << 0, ARM64 = 1 << 1 }
    public enum AndroidSdkVersions { AndroidApiLevelAuto = 0, AndroidApiLevel23 = 23, AndroidApiLevel24 = 24, AndroidApiLevel25 = 25, AndroidApiLevel26 = 26 }

    public class PlatformIconKind { }

    public class PlatformIcon
    {
        public void SetTextures(params Texture2D[] textures) { }
    }

    public sealed partial class PlayerSettings : Object
    {
        public static string productName { get; set; }
        public static string companyName { get; set; }
        public static string bundleVersion { get; set; }
        public static UIOrientation defaultInterfaceOrientation { get; set; }
        public static bool allowedAutorotateToPortrait { get; set; }
        public static bool allowedAutorotateToPortraitUpsideDown { get; set; }
        public static bool allowedAutorotateToLandscapeLeft { get; set; }
        public static bool allowedAutorotateToLandscapeRight { get; set; }
        public static bool runInBackground { get; set; }
        public static void SetApplicationIdentifier(Build.NamedBuildTarget buildTarget, string identifier) { }
        public static string GetApplicationIdentifier(Build.NamedBuildTarget buildTarget) => null;
        public static void SetScriptingBackend(Build.NamedBuildTarget buildTarget, ScriptingImplementation backend) { }
        public static void SetIcons(Build.NamedBuildTarget buildTarget, Texture2D[] icons, IconKind kind) { }
        public static int[] GetIconSizes(Build.NamedBuildTarget buildTarget, IconKind kind) => null;
        public static PlatformIcon[] GetPlatformIcons(Build.NamedBuildTarget buildTarget, PlatformIconKind kind) => null;
        public static void SetPlatformIcons(Build.NamedBuildTarget buildTarget, PlatformIconKind kind, PlatformIcon[] icons) { }

        public static partial class Android
        {
            public static int bundleVersionCode { get; set; }
            public static AndroidSdkVersions minSdkVersion { get; set; }
            public static AndroidSdkVersions targetSdkVersion { get; set; }
            public static AndroidArchitecture targetArchitectures { get; set; }
            public static bool forceInternetPermission { get; set; }
            public static bool useCustomKeystore { get; set; }
            public static string keystoreName { get; set; }
            public static string keystorePass { get; set; }
            public static string keyaliasName { get; set; }
            public static string keyaliasPass { get; set; }
        }
    }

    public enum BuildTarget { StandaloneWindows64 = 19, Android = 13, iOS = 9, WebGL = 20 }
    public enum BuildTargetGroup { Unknown = 0, Standalone = 1, iOS = 4, Android = 7, WebGL = 13 }
    [Flags] public enum BuildOptions { None = 0, Development = 1 << 0, AutoRunPlayer = 1 << 2 }

    public struct BuildPlayerOptions
    {
        public string[] scenes { get; set; }
        public string locationPathName { get; set; }
        public BuildTargetGroup targetGroup { get; set; }
        public BuildTarget target { get; set; }
        public BuildOptions options { get; set; }
    }

    public sealed partial class EditorUserBuildSettings : Object
    {
        public static BuildTarget activeBuildTarget => BuildTarget.Android;
        public static bool buildAppBundle { get; set; }
        public static bool SwitchActiveBuildTarget(BuildTargetGroup targetGroup, BuildTarget target) => false;
    }

    public class BuildPipeline
    {
        public static Build.Reporting.BuildReport BuildPlayer(BuildPlayerOptions buildPlayerOptions) => null;
    }

    public class SerializedProperty
    {
        public int intValue { get; set; }
    }

    public class SerializedObject : IDisposable
    {
        public SerializedObject(Object obj) { }
        public SerializedProperty FindProperty(string propertyPath) => null;
        public bool ApplyModifiedPropertiesWithoutUndo() => false;
        public void Dispose() { }
    }
}

namespace UnityEditor.Build
{
    public readonly struct NamedBuildTarget : IEquatable<NamedBuildTarget>
    {
        public static readonly NamedBuildTarget Unknown = default;
        public static readonly NamedBuildTarget Android = default;
        public bool Equals(NamedBuildTarget other) => true;
    }
}

namespace UnityEditor.Build.Reporting
{
    public enum BuildResult { Unknown = 0, Succeeded = 1, Failed = 2, Cancelled = 3 }

    public struct BuildSummary
    {
        public string outputPath { get; }
        public ulong totalSize { get; }
        public TimeSpan totalTime => default;
        public int totalErrors { get; }
        public int totalWarnings { get; }
        public BuildResult result { get; }
    }

    public sealed class BuildReport : Object
    {
        public BuildSummary summary => default;
    }
}

namespace UnityEditor.SceneManagement
{
    public enum NewSceneSetup { EmptyScene, DefaultGameObjects }
    public enum NewSceneMode { Single, Additive }
    public enum OpenSceneMode { Single, Additive, AdditiveWithoutLoading }

    public sealed partial class EditorSceneManager
    {
        public static bool SaveCurrentModifiedScenesIfUserWantsTo() => false;
        public static Scene NewScene(NewSceneSetup setup, NewSceneMode mode) => default;
        public static bool SaveScene(Scene scene, string dstScenePath) => false;
        public static Scene OpenScene(string scenePath) => default;
        public static Scene OpenScene(string scenePath, OpenSceneMode mode) => default;
    }
}
