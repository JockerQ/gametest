using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using EvilCats.Game;
using UnityEditor;
using UnityEditor.Build;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace EvilCats.EditorTools
{
    /// <summary>
    /// Android builds from a menu or the command line. Nothing is uploaded or published.
    ///
    ///  * Development APK: debug-signed by Unity, installs on your own phone over USB.
    ///  * Release App Bundle (.aab): needs YOUR upload keystore, read from environment variables
    ///    (never stored in the project or in version control):
    ///      EC_ANDROID_KEYSTORE        full path to the .keystore / .jks file
    ///      EC_ANDROID_KEYSTORE_PASS   keystore password
    ///      EC_ANDROID_KEY_ALIAS       key alias
    ///      EC_ANDROID_KEY_PASS        key password
    ///
    /// Command line:
    ///   Unity -batchmode -quit -projectPath EvilCats -buildTarget Android -executeMethod EvilCats.EditorTools.BuildScript.BuildDevelopmentApk
    ///   Unity -batchmode -quit -projectPath EvilCats -buildTarget Android -executeMethod EvilCats.EditorTools.BuildScript.BuildReleaseAab
    /// </summary>
    public static class BuildScript
    {
        public const string OutputDir = "Builds/Android";

        [MenuItem("Evil Cats/Build/Android APK (development)", priority = 20)]
        public static void BuildDevelopmentApkMenu() => BuildAndroid(false, true);

        [MenuItem("Evil Cats/Build/Android App Bundle (release, needs your keystore)", priority = 21)]
        public static void BuildReleaseAabMenu() => BuildAndroid(true, true);

        public static void BuildDevelopmentApk()
        {
            if (!BuildAndroid(false, false)) EditorApplication.Exit(1);
        }

        public static void BuildReleaseAab()
        {
            if (!BuildAndroid(true, false)) EditorApplication.Exit(1);
        }

        public static bool BuildAndroid(bool release, bool interactive)
        {
            var log = new StringBuilder();
            // 1) the project must be set up and the content must be valid before anything is built
            if (!ProjectSetup.Run(false))
                return Fail("Project setup reported problems; see the Console.", interactive);
            if (ProjectSetup.LastRunPending)
                return Fail("Setup is still importing TextMeshPro resources. Wait for it to finish, then build again.", interactive);
            if (ProjectSetup.LastRunNeedsRestart)
                return Fail("The input backend was just changed. Restart Unity, then build again.", interactive);
            var problems = ContentTools.ValidateAll(out string summary);
            log.AppendLine(summary);
            if (problems > 0) return Fail("Content or asset validation failed:\n" + summary, interactive);

            // 2) Android target
            if (EditorUserBuildSettings.activeBuildTarget != BuildTarget.Android &&
                !EditorUserBuildSettings.SwitchActiveBuildTarget(BuildTargetGroup.Android, BuildTarget.Android))
                return Fail("Could not switch to the Android platform. Install 'Android Build Support' for this Unity version in Unity Hub.", interactive);

            // 3) signing
            bool signed = false;
            if (release)
            {
                string ks = Environment.GetEnvironmentVariable("EC_ANDROID_KEYSTORE");
                string ksPass = Environment.GetEnvironmentVariable("EC_ANDROID_KEYSTORE_PASS");
                string alias = Environment.GetEnvironmentVariable("EC_ANDROID_KEY_ALIAS");
                string aliasPass = Environment.GetEnvironmentVariable("EC_ANDROID_KEY_PASS");
                if (string.IsNullOrEmpty(ks) || !File.Exists(ks) || string.IsNullOrEmpty(ksPass) || string.IsNullOrEmpty(alias) || string.IsNullOrEmpty(aliasPass))
                    return Fail("A release build needs your upload keystore. Set EC_ANDROID_KEYSTORE, EC_ANDROID_KEYSTORE_PASS, EC_ANDROID_KEY_ALIAS and EC_ANDROID_KEY_PASS (see README.md). Nothing was built.", interactive);
                if (PlayerSettings.GetApplicationIdentifier(NamedBuildTarget.Android) == ProjectSetup.PlaceholderAppId)
                    return Fail("Choose your own application id first (Project Settings > Player > Android > Other Settings > Package Name). It is permanent once published.", interactive);
                PlayerSettings.Android.useCustomKeystore = true;
                PlayerSettings.Android.keystoreName = ks;
                PlayerSettings.Android.keystorePass = ksPass;
                PlayerSettings.Android.keyaliasName = alias;
                PlayerSettings.Android.keyaliasPass = aliasPass;
                signed = true;
            }
            else PlayerSettings.Android.useCustomKeystore = false;   // Unity's debug key

            EditorUserBuildSettings.buildAppBundle = release;
            Directory.CreateDirectory(OutputDir);
            string file = "EvilCats-" + GameApp.Version + "-" + PlayerSettings.Android.bundleVersionCode + (release ? "-release.aab" : "-dev.apk");
            var scenes = new List<string>();
            foreach (var s in EditorBuildSettings.scenes) if (s.enabled) scenes.Add(s.path);
            var options = new BuildPlayerOptions
            {
                scenes = scenes.ToArray(),
                locationPathName = Path.Combine(OutputDir, file),
                target = BuildTarget.Android,
                targetGroup = BuildTargetGroup.Android,
                options = release ? BuildOptions.None : BuildOptions.Development,
            };
            BuildReport report;
            try
            {
                report = BuildPipeline.BuildPlayer(options);
            }
            finally
            {
                if (signed)
                {
                    // passwords are never saved to disk by Unity; clear them from memory as well
                    PlayerSettings.Android.keystorePass = "";
                    PlayerSettings.Android.keyaliasPass = "";
                }
            }
            var sum = report.summary;
            log.AppendLine("Result: " + sum.result);
            log.AppendLine("Output: " + sum.outputPath);
            log.AppendLine("Size: " + (sum.totalSize / (1024f * 1024f)).ToString("0.0") + " MB");
            log.AppendLine("Time: " + sum.totalTime);
            log.AppendLine("Errors: " + sum.totalErrors + ", warnings: " + sum.totalWarnings);
            File.WriteAllText(Path.Combine(OutputDir, "last-build-report.txt"), log.ToString());
            if (sum.result != BuildResult.Succeeded) return Fail("Build failed:\n" + log, interactive);
            Debug.Log("[EvilCats] Build succeeded\n" + log);
            if (interactive) EditorUtility.RevealInFinder(sum.outputPath);
            return true;
        }

        private static bool Fail(string message, bool interactive)
        {
            Debug.LogError("[EvilCats] " + message);
            if (interactive) EditorUtility.DisplayDialog("Evil Cats build", message, "OK");
            return false;
        }
    }
}
