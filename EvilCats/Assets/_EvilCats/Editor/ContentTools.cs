using System.IO;
using System.Text;
using EvilCats.Content;
using EvilCats.Game;
using Newtonsoft.Json.Linq;
using UnityEditor;
using UnityEngine;

namespace EvilCats.EditorTools
{
    /// <summary>Validation and maintenance menu items.</summary>
    public static class ContentTools
    {
        [MenuItem("Evil Cats/2. Validate Content, Art and Audio", priority = 2)]
        public static void ValidateMenu()
        {
            int problems = ValidateAll(out string summary);
            if (problems == 0) Debug.Log(summary);
            else Debug.LogError(summary);
            EditorUtility.DisplayDialog("Evil Cats", problems == 0 ? "Everything is valid." : problems + " problem(s) found. See the Console.", "OK");
        }

        /// <summary>Content rules (ContentValidator), art (AssetAudit) and audio manifest. Returns the error count.</summary>
        public static int ValidateAll(out string summary)
        {
            var sb = new StringBuilder("[EvilCats] Validation\n");
            int errors = 0;
            var content = GameContent.Load(new ResourcesContentSource(), strict: true);
            foreach (var e in content.LoadErrors) { sb.AppendLine("  content load: " + e); errors++; }
            var report = ContentValidator.Validate(content);
            foreach (var e in report.Errors) { sb.AppendLine("  content: " + e); errors++; }
            foreach (var w in report.Warnings) sb.AppendLine("  (warning) " + w);
            var sprites = new SpriteLibrary();
            sprites.LoadAll();
            foreach (var p in AssetAudit.Run(content, sprites)) { sb.AppendLine("  art: " + p); errors++; }
            foreach (var p in AudioProblems()) { sb.AppendLine("  audio: " + p); errors++; }
            sb.AppendLine(errors == 0 ? "  OK: content, " + sprites.Count + " sprites and the audio manifest are valid." : "  " + errors + " problem(s).");
            summary = sb.ToString();
            return errors;
        }

        public static System.Collections.Generic.List<string> AudioProblems()
        {
            var problems = new System.Collections.Generic.List<string>();
            var manifest = Resources.Load<TextAsset>("ECAudio/audio_manifest");
            if (manifest == null) { problems.Add("audio_manifest.json missing (run Tools/audio/build_audio.py)"); return problems; }
            var root = JObject.Parse(manifest.text);
            if (root["music"] is JObject music)
                foreach (var kv in music)
                    if (Resources.Load<AudioClip>("ECAudio/" + (string)kv.Value["file"]) == null) problems.Add("music '" + kv.Key + "' file missing");
            if (root["sfx"] is JObject sfx)
                foreach (var kv in sfx)
                    if (kv.Value["files"] is JArray files)
                        foreach (var f in files)
                            if (Resources.Load<AudioClip>("ECAudio/" + (string)f) == null) problems.Add("sfx '" + kv.Key + "' file " + f + " missing");
            return problems;
        }

        [MenuItem("Evil Cats/Save Data/Show Save Folder", priority = 40)]
        public static void ShowSaveFolder() => EditorUtility.RevealInFinder(Application.persistentDataPath);

        [MenuItem("Evil Cats/Save Data/Delete Editor Save", priority = 41)]
        public static void DeleteEditorSave()
        {
            if (!EditorUtility.DisplayDialog("Evil Cats", "Delete the save file used when playing in the Editor? (Phone saves are not affected.)", "Delete", "Cancel")) return;
            var store = new Meta.FileSaveStore(Application.persistentDataPath);
            store.DeleteAll();
            Debug.Log("[EvilCats] Editor save deleted: " + store.PrimaryPath);
        }

        [MenuItem("Evil Cats/Open Boot Scene", priority = 3)]
        public static void OpenBoot()
        {
            string path = ProjectSetup.ScenesDir + "/" + GameApp.BootScene + ".unity";
            if (!File.Exists(path)) { EditorUtility.DisplayDialog("Evil Cats", "Run 'Evil Cats > 1. Set Up Project' first.", "OK"); return; }
            if (UnityEditor.SceneManagement.EditorSceneManager.SaveCurrentModifiedScenesIfUserWantsTo())
                UnityEditor.SceneManagement.EditorSceneManager.OpenScene(path);
        }
    }
}
