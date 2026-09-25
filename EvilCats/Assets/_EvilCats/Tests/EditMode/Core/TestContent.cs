using System;
using System.IO;
using EvilCats.Content;

namespace EvilCats.Tests
{
    /// <summary>Reads content JSON straight from the project folder. Works both in the Unity
    /// editor (current directory = project root) and under `dotnet test` (walks up from the
    /// test binaries to the repository).</summary>
    public sealed class FileContentSource : IContentSource
    {
        public readonly string Dir;
        public FileContentSource(string dir) { Dir = dir; }

        public string Read(string name)
        {
            string path = Path.Combine(Dir, name + ".json");
            return File.Exists(path) ? File.ReadAllText(path) : null;
        }

        public static string FindDataDir()
        {
            const string rel = "Assets/_EvilCats/Data/Resources/ECData";
            foreach (var start in new[] { Environment.CurrentDirectory, AppContext.BaseDirectory })
            {
                var dir = new DirectoryInfo(start);
                while (dir != null)
                {
                    string a = Path.Combine(dir.FullName, rel);
                    if (Directory.Exists(a)) return a;
                    string b = Path.Combine(dir.FullName, "EvilCats", rel);
                    if (Directory.Exists(b)) return b;
                    dir = dir.Parent;
                }
            }
            throw new DirectoryNotFoundException("Could not find " + rel);
        }
    }

    public static class TestContent
    {
        private static GameContent _cached;

        /// <summary>Shared, read-only content instance (content is never mutated by the game).</summary>
        public static GameContent Load()
        {
            if (_cached == null) _cached = GameContent.Load(new FileContentSource(FileContentSource.FindDataDir()), strict: true);
            return _cached;
        }

        /// <summary>A private copy for tests that tweak tuning values.</summary>
        public static GameContent Fresh() => GameContent.Load(new FileContentSource(FileContentSource.FindDataDir()), strict: true);
    }
}
