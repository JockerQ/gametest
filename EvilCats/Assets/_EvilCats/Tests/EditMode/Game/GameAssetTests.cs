using System.Collections.Generic;
using System.IO;
using System.Text.RegularExpressions;
using EvilCats.Content;
using EvilCats.EditorTools;
using EvilCats.Game;
using Newtonsoft.Json.Linq;
using NUnit.Framework;
using UnityEditor;
using UnityEngine;

namespace EvilCats.Tests
{
    /// <summary>
    /// Editor tests for the Unity layer's data: content loads from Resources and validates, every
    /// sprite/animation/sound/string the code asks for exists, and the pixel art imports untouched.
    /// </summary>
    public class GameAssetTests
    {
        private static string GameScripts => Path.Combine(Application.dataPath, "_EvilCats/Scripts/Game");

        private static IEnumerable<string> Literals(string pattern)
        {
            var rx = new Regex(pattern);
            foreach (var file in Directory.GetFiles(GameScripts, "*.cs", SearchOption.AllDirectories))
                foreach (Match m in rx.Matches(File.ReadAllText(file)))
                    yield return m.Groups[1].Value;
        }

        [Test]
        public void ContentLoadsFromResourcesAndValidates()
        {
            var c = GameContent.Load(new ResourcesContentSource(), strict: true);
            Assert.That(c.LoadErrors, Is.Empty);
            var report = ContentValidator.Validate(c);
            Assert.That(report.Errors, Is.Empty, report.ToString());
        }

        [Test]
        public void EveryPieceOfArtTheGameUsesExists()
        {
            var c = GameContent.Load(new ResourcesContentSource(), strict: true);
            var sp = new SpriteLibrary();
            sp.LoadAll();
            Assert.That(sp.Count, Is.GreaterThan(900));
            Assert.That(AssetAudit.Run(c, sp), Is.Empty);
        }

        [Test]
        public void EverySpriteNameWrittenInCodeExists()
        {
            var sp = new SpriteLibrary();
            sp.LoadAll();
            var missing = new List<string>();
            // literals followed by "+" (e.g. "citadel/cracks" + level) are completed at runtime
            foreach (var name in Literals("\"((?:icon|ui|fx|logo|portrait|avatar|citadel)/[a-z0-9_/]+)\"(?!\\s*\\+)"))
            {
                if (name.EndsWith("/")) continue;   // prefixes such as "icon/module/" are completed at runtime
                if (!sp.Has(name) && !sp.HasAnim(name)) missing.Add(name);
            }
            Assert.That(missing, Is.Empty);
        }

        [Test]
        public void EveryStringKeyWrittenInCodeExists()
        {
            var c = GameContent.Load(new ResourcesContentSource(), strict: true);
            var missing = new List<string>();
            foreach (var key in Literals("L\\.(?:T|F|Has)\\(\"([^\"]+)\""))
                if (!key.EndsWith(".") && !c.Strings.Has(key)) missing.Add(key);
            foreach (var key in Literals("ShowHint\\(\"([^\"]+)\""))
                if (!c.Strings.Has(key)) missing.Add(key);
            Assert.That(missing, Is.Empty);
        }

        [Test]
        public void EverySoundWrittenInCodeExists()
        {
            var manifest = Resources.Load<TextAsset>("ECAudio/audio_manifest");
            Assert.That(manifest, Is.Not.Null);
            var root = JObject.Parse(manifest.text);
            var sfx = (JObject)root["sfx"];
            var music = (JObject)root["music"];
            var missing = new List<string>();
            foreach (var id in Literals("\\.Play(?:Loop)?\\(\"([a-z0-9_]+)\""))
                if (sfx[id] == null) missing.Add("sfx " + id);
            foreach (var id in Literals("\\.PlayMusic\\(\"([a-z0-9_]+)\""))
                if (music[id] == null) missing.Add("music " + id);
            Assert.That(missing, Is.Empty);
            Assert.That(ContentTools.AudioProblems(), Is.Empty);
        }

        [Test]
        public void PixelArtImportsAtExactSizeWithoutFiltering()
        {
            var guids = AssetDatabase.FindAssets("t:Texture2D", new[] { "Assets/_EvilCats/Art/Resources/ECArt" });
            Assert.That(guids.Length, Is.GreaterThan(10));
            foreach (var g in guids)
            {
                string path = AssetDatabase.GUIDToAssetPath(g);
                var ti = (TextureImporter)AssetImporter.GetAtPath(path);
                Assert.That(ImportRules.Matches(ti), Is.True, path + " has changed import settings (run Evil Cats > 1. Set Up Project)");
                var json = AssetDatabase.LoadAssetAtPath<TextAsset>(path.Replace(".png", "_atlas.json").Replace("_flash_atlas.json", "_atlas.json"));
                var tex = AssetDatabase.LoadAssetAtPath<Texture2D>(path);
                if (json == null || tex == null) continue;
                var meta = JObject.Parse(json.text);
                Assert.That(tex.width, Is.EqualTo((int)meta["width"]), path);
                Assert.That(tex.height, Is.EqualTo((int)meta["height"]), path);
            }
        }
    }
}
