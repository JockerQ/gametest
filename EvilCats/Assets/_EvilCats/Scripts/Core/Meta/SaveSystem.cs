using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using EvilCats.Content;
using EvilCats.Core;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;

namespace EvilCats.Meta
{
    /// <summary>Raw text storage for the save file. Implementations must make WriteAtomic all-or-nothing.</summary>
    public interface ISaveStore
    {
        string ReadPrimary();
        string ReadBackup();
        /// <summary>Write text as the new primary save; the previous primary becomes the backup.</summary>
        void WriteAtomic(string text);
        /// <summary>Keep an unreadable file for manual recovery instead of deleting it.</summary>
        void Quarantine(string text, string reason);
        void DeleteAll();
    }

    /// <summary>
    /// File-based store (Application.persistentDataPath on device). Write order:
    ///   1. write save.json.tmp and flush to disk
    ///   2. File.Replace(tmp -> save.json, previous -> save.json.bak)   (atomic rename)
    ///   fallback when Replace is unsupported: copy primary to .bak, then move tmp over primary.
    /// A crash at any point leaves either the old or the new file readable, plus a backup.
    /// </summary>
    public sealed class FileSaveStore : ISaveStore
    {
        public readonly string Directory;
        public string PrimaryPath => Path.Combine(Directory, "evilcats_save.json");
        public string BackupPath => PrimaryPath + ".bak";
        private string TempPath => PrimaryPath + ".tmp";

        public FileSaveStore(string directory)
        {
            Directory = directory;
            System.IO.Directory.CreateDirectory(directory);
        }

        public string ReadPrimary() => ReadIfExists(PrimaryPath);
        public string ReadBackup() => ReadIfExists(BackupPath);

        private static string ReadIfExists(string path)
        {
            try { return File.Exists(path) ? File.ReadAllText(path, Encoding.UTF8) : null; }
            catch (IOException) { return null; }
            catch (UnauthorizedAccessException) { return null; }
        }

        public void WriteAtomic(string text)
        {
            var bytes = new UTF8Encoding(false).GetBytes(text);
            using (var fs = new FileStream(TempPath, FileMode.Create, FileAccess.Write, FileShare.None))
            {
                fs.Write(bytes, 0, bytes.Length);
                fs.Flush(true);
            }
            if (!File.Exists(PrimaryPath))
            {
                File.Move(TempPath, PrimaryPath);
                return;
            }
            try
            {
                File.Replace(TempPath, PrimaryPath, BackupPath, true);
            }
            catch (Exception e) when (e is PlatformNotSupportedException || e is IOException || e is NotSupportedException || e is UnauthorizedAccessException)
            {
                File.Copy(PrimaryPath, BackupPath, true);
                File.Delete(PrimaryPath);
                File.Move(TempPath, PrimaryPath);
            }
        }

        public void Quarantine(string text, string reason)
        {
            try
            {
                string name = "evilcats_save.corrupt-" + DateTime.UtcNow.ToString("yyyyMMddHHmmss") + ".json";
                File.WriteAllText(Path.Combine(Directory, name), (reason ?? "") + "\n" + (text ?? ""), Encoding.UTF8);
            }
            catch (Exception) { /* best effort */ }
        }

        public void DeleteAll()
        {
            foreach (var p in new[] { PrimaryPath, BackupPath, TempPath })
                if (File.Exists(p)) File.Delete(p);
        }
    }

    /// <summary>In-memory store for tests and for running without writable storage.</summary>
    public sealed class MemorySaveStore : ISaveStore
    {
        public string Primary, Backup;
        public readonly List<string> Quarantined = new List<string>();
        public int Writes;
        public bool FailNextWrite;

        public string ReadPrimary() => Primary;
        public string ReadBackup() => Backup;

        public void WriteAtomic(string text)
        {
            if (FailNextWrite)
            {
                FailNextWrite = false;
                throw new IOException("simulated write failure");
            }
            Backup = Primary;
            Primary = text;
            Writes++;
        }

        public void Quarantine(string text, string reason) => Quarantined.Add(reason + "|" + text);
        public void DeleteAll() { Primary = Backup = null; }
    }

    public enum LoadOutcome { NewProfile, Loaded, Migrated, RecoveredFromBackup, ResetAfterCorruption }

    public sealed class LoadResult
    {
        public SaveData data;
        public LoadOutcome outcome;
        public int fromVersion;
        public string detail;
    }

    /// <summary>Envelope format: {"format":"EvilCatsSave","version":N,"checksum":"fnv64","savedAtUtc":"...","payload":"&lt;json&gt;"}</summary>
    public static class SaveSerializer
    {
        public const string Format = "EvilCatsSave";

        public static string Serialize(SaveData data, DateTime utcNow)
        {
            data.version = SaveData.CurrentVersion;
            string payload = Json.Serialize(data);
            var env = new JObject
            {
                ["format"] = Format,
                ["version"] = SaveData.CurrentVersion,
                ["checksum"] = Hash.ToHex(Hash.Fnv1a64(payload)),
                ["savedAtUtc"] = utcNow.ToString("o"),
                ["payload"] = payload,
            };
            return env.ToString(Formatting.None);
        }

        /// <summary>Parses and verifies a save. Returns null (with reason) when unreadable.</summary>
        public static SaveData TryParse(string text, out int fromVersion, out string reason)
        {
            fromVersion = 0;
            reason = null;
            if (string.IsNullOrWhiteSpace(text)) { reason = "empty"; return null; }
            JObject env;
            try { env = JObject.Parse(text); }
            catch (Exception e) { reason = "not json: " + e.Message; return null; }
            JObject payload;
            if ((string)env["format"] == Format)
            {
                string p = (string)env["payload"];
                string sum = (string)env["checksum"];
                if (p == null) { reason = "no payload"; return null; }
                if (sum != Hash.ToHex(Hash.Fnv1a64(p))) { reason = "checksum mismatch"; return null; }
                try { payload = JObject.Parse(p); }
                catch (Exception e) { reason = "payload not json: " + e.Message; return null; }
                fromVersion = (int?)env["version"] ?? (int?)payload["version"] ?? 1;
            }
            else
            {
                // Legacy prototype files (v1) were plain JSON without an envelope.
                payload = env;
                fromVersion = (int?)payload["version"] ?? 1;
            }
            if (fromVersion > SaveData.CurrentVersion) { reason = "save is from a newer game version (" + fromVersion + ")"; return null; }
            try
            {
                SaveMigrations.Migrate(payload, fromVersion);
                var data = payload.ToObject<SaveData>(JsonSerializer.Create(Json.Settings(false)));
                if (data == null) { reason = "empty payload"; return null; }
                Normalize(data);
                return data;
            }
            catch (Exception e)
            {
                reason = "migration/deserialize failed: " + e.Message;
                return null;
            }
        }

        /// <summary>Repairs nulls from older or hand-edited files so the game never crashes on them.</summary>
        public static void Normalize(SaveData d)
        {
            d.nodes ??= new Dictionary<string, int>();
            d.modulesUnlocked ??= new List<string>();
            d.modulesAvailable ??= new List<string>();
            d.moduleTiers ??= new Dictionary<string, int>();
            d.slotsUnlocked ??= new List<string>();
            d.loadout ??= new Dictionary<string, string>();
            d.missions ??= new Dictionary<string, MissionRecord>();
            d.cosmeticsOwned ??= new List<string>();
            d.lifetime ??= new Dictionary<string, long>();
            d.achievementsClaimed ??= new List<string>();
            d.attendance ??= new AttendanceState();
            d.daily ??= new DailyState();
            d.daily.objectives ??= new List<string>();
            d.daily.progress ??= new Dictionary<string, long>();
            d.daily.claimed ??= new List<string>();
            d.offline ??= new OfflineState();
            d.endless ??= new EndlessRecord();
            d.settings ??= new SettingsData();
            d.tutorial ??= new TutorialState();
            d.tutorial.hintsShown ??= new List<string>();
            d.tutorial.chapterScenesSeen ??= new List<string>();
            d.ledger ??= new List<string>();
            if (!d.modulesUnlocked.Contains("arc_coil")) d.modulesUnlocked.Insert(0, "arc_coil");
            if (!d.slotsUnlocked.Contains("middle")) d.slotsUnlocked.Insert(0, "middle");
            if (!d.cosmeticsOwned.Contains("arc_light_cat")) d.cosmeticsOwned.Add("arc_light_cat");
            if (!d.cosmeticsOwned.Contains("banner_violet")) d.cosmeticsOwned.Add("banner_violet");
            if (d.moonGold < 0) d.moonGold = 0;
            if (d.stormShards < 0) d.stormShards = 0;
            if (string.IsNullOrEmpty(d.profileId)) d.profileId = Guid.NewGuid().ToString("N");
            d.version = SaveData.CurrentVersion;
        }
    }

    /// <summary>Stepwise, testable migrations applied to the raw JSON payload.</summary>
    public static class SaveMigrations
    {
        public static void Migrate(JObject p, int fromVersion)
        {
            int v = fromVersion;
            if (v < 2) { V1ToV2(p); v = 2; }
            p["version"] = v;
        }

        /// <summary>
        /// v1 was the internal prototype layout: "gold", "shards", "unlocked" (modules),
        /// "missionsCleared" (list of ids) and "settings": {"musicVolume","sfxVolume"}.
        /// </summary>
        public static void V1ToV2(JObject p)
        {
            Rename(p, "gold", "moonGold");
            Rename(p, "shards", "stormShards");
            Rename(p, "unlocked", "modulesUnlocked");
            if (p["missionsCleared"] is JArray cleared)
            {
                var missions = p["missions"] as JObject ?? new JObject();
                foreach (var id in cleared)
                {
                    string key = (string)id;
                    if (string.IsNullOrEmpty(key)) continue;
                    missions[key] = new JObject { ["cleared"] = true, ["clears"] = 1, ["bestWave"] = 0 };
                }
                p["missions"] = missions;
                p.Remove("missionsCleared");
            }
            if (p["settings"] is JObject s)
            {
                Rename(s, "musicVolume", "music");
                Rename(s, "sfxVolume", "sfx");
            }
        }

        private static void Rename(JObject o, string from, string to)
        {
            if (o[from] == null) return;
            if (o[to] == null) o[to] = o[from];
            o.Remove(from);
        }
    }

    public sealed class SaveManager
    {
        private readonly ISaveStore _store;
        public LoadResult LastLoad { get; private set; }
        public Exception LastWriteError { get; private set; }

        public SaveManager(ISaveStore store) { _store = store; }

        /// <summary>
        /// Load order: primary → backup → new profile. Unreadable files are quarantined
        /// (kept) rather than silently deleted, and the outcome is reported to the UI.
        /// </summary>
        public LoadResult Load(DateTime utcNow)
        {
            var res = new LoadResult();
            string primary = _store.ReadPrimary();
            string backup = _store.ReadBackup();
            if (primary == null && backup == null)
            {
                res.data = NewProfile(utcNow);
                res.outcome = LoadOutcome.NewProfile;
                return LastLoad = res;
            }
            var data = SaveSerializer.TryParse(primary, out int ver, out string why);
            if (data != null)
            {
                res.data = data;
                res.fromVersion = ver;
                res.outcome = ver < SaveData.CurrentVersion ? LoadOutcome.Migrated : LoadOutcome.Loaded;
                return LastLoad = res;
            }
            if (primary != null) _store.Quarantine(primary, "primary unreadable: " + why);
            var fromBackup = SaveSerializer.TryParse(backup, out int bver, out string bwhy);
            if (fromBackup != null)
            {
                res.data = fromBackup;
                res.fromVersion = bver;
                res.outcome = LoadOutcome.RecoveredFromBackup;
                res.detail = why;
                return LastLoad = res;
            }
            if (backup != null) _store.Quarantine(backup, "backup unreadable: " + bwhy);
            res.data = NewProfile(utcNow);
            res.outcome = primary == null ? LoadOutcome.NewProfile : LoadOutcome.ResetAfterCorruption;
            res.detail = why + " / " + bwhy;
            return LastLoad = res;
        }

        public static SaveData NewProfile(DateTime utcNow)
        {
            var d = new SaveData { createdUtc = utcNow.ToString("o") };
            SaveSerializer.Normalize(d);
            return d;
        }

        /// <returns>false if the write failed (the previous file remains intact).</returns>
        public bool Save(SaveData data, DateTime utcNow)
        {
            try
            {
                _store.WriteAtomic(SaveSerializer.Serialize(data, utcNow));
                LastWriteError = null;
                return true;
            }
            catch (Exception e)
            {
                LastWriteError = e;
                return false;
            }
        }

        public void DeleteAll() => _store.DeleteAll();
    }
}
