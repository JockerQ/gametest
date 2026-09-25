using System;
using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Sim;

namespace EvilCats.Meta
{
    /// <summary>
    /// Everything persisted for one player. Uses stable ids only (never display names).
    /// Bump CurrentVersion and add a migration in SaveMigrations whenever the layout changes.
    /// </summary>
    [Serializable]
    public sealed class SaveData
    {
        public const int CurrentVersion = 2;

        public int version = CurrentVersion;
        public string profileId = Guid.NewGuid().ToString("N");
        public string createdUtc;
        public string displayName = "Guest";
        public string avatar = "arc_light_cat";

        public long moonGold;
        public long stormShards;

        public Dictionary<string, int> nodes = new Dictionary<string, int>();
        public List<string> modulesUnlocked = new List<string> { "arc_coil", "ember_maw" };
        public List<string> modulesAvailable = new List<string>();      // milestone reached, not yet bought with shards
        public Dictionary<string, int> moduleTiers = new Dictionary<string, int>();
        public List<string> slotsUnlocked = new List<string> { "middle" };
        public Dictionary<string, string> loadout = new Dictionary<string, string> { { "middle", "arc_coil" } };
        public TargetPriority defaultPriority = TargetPriority.Nearest;

        public Dictionary<string, MissionRecord> missions = new Dictionary<string, MissionRecord>();
        public List<string> cosmeticsOwned = new List<string> { "arc_light_cat", "banner_violet" };
        public string heroSkin = "arc_light_cat";
        public string banner = "banner_violet";

        public Dictionary<string, long> lifetime = new Dictionary<string, long>();
        public List<string> achievementsClaimed = new List<string>();

        public AttendanceState attendance = new AttendanceState();
        public DailyState daily = new DailyState();
        public OfflineState offline = new OfflineState();
        public EndlessRecord endless = new EndlessRecord();
        public SettingsData settings = new SettingsData();
        public TutorialState tutorial = new TutorialState();

        public RunCheckpoint activeRun;
        /// <summary>Idempotency ledger: transaction ids that have already paid out.</summary>
        public List<string> ledger = new List<string>();

        public long Lifetime(string key) => lifetime.TryGetValue(key, out var v) ? v : 0L;
        public void AddLifetime(string key, long v) { if (v != 0) lifetime[key] = Lifetime(key) + v; }
        public void MaxLifetime(string key, long v) { if (v > Lifetime(key)) lifetime[key] = v; }

        public MissionRecord Mission(string id)
        {
            if (!missions.TryGetValue(id, out var r))
            {
                r = new MissionRecord();
                missions[id] = r;
            }
            return r;
        }

        public bool Cleared(string missionId) => missionId != null && missions.TryGetValue(missionId, out var r) && r.cleared;
        public int NodeLevel(string id) => nodes.TryGetValue(id, out var l) ? l : 0;
        public int ModuleTier(string id) => moduleTiers.TryGetValue(id, out var t) ? Math.Max(1, t) : 1;
    }

    [Serializable]
    public sealed class MissionRecord
    {
        public bool cleared;
        public int clears;
        public int bestWave;
        public float bestTimeSec;
        public int attempts;
    }

    [Serializable]
    public sealed class AttendanceState
    {
        public int dayIndex;            // 0..6: next reward to claim
        public string lastClaimDate;    // local calendar date yyyy-MM-dd
        public int totalClaims;
    }

    [Serializable]
    public sealed class DailyState
    {
        public string date;             // local calendar date these objectives belong to
        public List<string> objectives = new List<string>();
        public Dictionary<string, long> progress = new Dictionary<string, long>();
        public List<string> claimed = new List<string>();
        public string challengeDate;    // UTC date of the challenge record below
        public long challengeBestScore;
        public int challengeBestWave;
        public int challengeAttempts;
    }

    [Serializable]
    public sealed class OfflineState
    {
        public long stampUtcTicks;      // accrual start; 0 = not started (no mission cleared yet)
        public long totalCollected;
    }

    [Serializable]
    public sealed class EndlessRecord
    {
        public int bestWave;
        public long bestScore;
        public int runs;
    }

    [Serializable]
    public sealed class SettingsData
    {
        public float music = 0.8f;
        public float sfx = 0.9f;
        public bool vibration = true;
        public bool screenShake = true;
        public bool flashes = true;
        public bool damageNumbers = true;
        public bool startAt2x;
        public string routeLayout = "routes_5";
        public string language = "en";
    }

    [Serializable]
    public sealed class TutorialState
    {
        public bool storySeen;
        public bool guestChosen;
        public List<string> hintsShown = new List<string>();
        public List<string> chapterScenesSeen = new List<string>();
    }
}
