using System;
using System.Collections.Generic;
using System.Globalization;
using EvilCats.Content;
using EvilCats.Core;
using EvilCats.Sim;

namespace EvilCats.Meta
{
    public enum MetaResult
    {
        Ok, AlreadyClaimed, NotEnoughMoonGold, NotEnoughShards, MaxLevel, Locked, RequirementMissing,
        NotAvailable, Unknown, InvalidInput, ClockMovedBack, TooSoon, NothingToClaim,
    }

    public enum ModuleState { Unlocked, Available, Locked }

    public sealed class RewardSummary
    {
        public bool alreadyApplied;
        public long moonGold;
        public long stormShards;
        public bool firstClear;
        public string moduleUnlocked;    // became unlocked (free) or available (needs shards)
        public bool moduleNeedsShards;
        public bool newRecord;
        public List<string> achievementsReady = new List<string>();
        public List<string> objectivesReady = new List<string>();
        public List<string> slotsUnlocked = new List<string>();
        public string chapterScene;       // "gravewood" / "moonfall" when a biome was just finished
    }

    public sealed class DailyChallengeConfig
    {
        public string dateUtc;
        public ulong seed;
        public Dictionary<string, string> loadout = new Dictionary<string, string>();
        public List<string> modifiers = new List<string>();
        public string boss;
    }

    /// <summary>
    /// The permanent-progression rules on top of SaveData. Every method that grants something
    /// goes through the ledger with a stable transaction id, so rapid taps, repeated callbacks,
    /// app restarts and checkpoint replays can never pay out twice. Time is always passed in
    /// explicitly (testable; the Unity layer passes DateTime.UtcNow / DateTime.Now).
    /// </summary>
    public sealed class GameMeta
    {
        public readonly GameContent C;
        public SaveData Data { get; private set; }
        private readonly SaveManager _saves;
        private const int LedgerCap = 600;

        public event Action Changed;

        public GameMeta(GameContent content, SaveData data, SaveManager saves = null)
        {
            C = content;
            Data = data;
            _saves = saves;
            SaveSerializer.Normalize(Data);
            RepairLoadout();
        }

        public bool Save(DateTime utcNow)
        {
            Changed?.Invoke();
            return _saves == null || _saves.Save(Data, utcNow);
        }

        public void ReplaceData(SaveData data)
        {
            Data = data;
            SaveSerializer.Normalize(Data);
            RepairLoadout();
            Changed?.Invoke();
        }

        // ---- ledger -----------------------------------------------------------------------
        public bool IsClaimed(string tx) => Data.ledger.Contains(tx);

        private bool TryClaim(string tx)
        {
            if (Data.ledger.Contains(tx)) return false;
            Data.ledger.Add(tx);
            if (Data.ledger.Count > LedgerCap)
            {
                // Prune the oldest per-run entries only; permanent claims (achievements, first
                // clears, dates) are also tracked in their own lists so pruning is safe.
                for (int i = 0; i < Data.ledger.Count && Data.ledger.Count > LedgerCap; i++)
                    if (Data.ledger[i].StartsWith("run:", StringComparison.Ordinal)) { Data.ledger.RemoveAt(i); i--; }
            }
            return true;
        }

        // ---- permanent tree ------------------------------------------------------------------
        public int NodeCost(string id)
        {
            if (!C.NodeById.TryGetValue(id, out var n)) return int.MaxValue;
            return NodeCostAt(n, Data.NodeLevel(id));
        }

        public static int NodeCostAt(PermanentNodeDef n, int level) => MathX.CeilToInt(n.baseCost * Math.Pow(n.costGrowth, level));

        public MetaResult CanBuyNode(string id)
        {
            if (!C.NodeById.TryGetValue(id, out var n)) return MetaResult.Unknown;
            int level = Data.NodeLevel(id);
            if (level >= n.maxLevel) return MetaResult.MaxLevel;
            if (!string.IsNullOrEmpty(n.requiresNode) && Data.NodeLevel(n.requiresNode) < n.requiresLevel) return MetaResult.RequirementMissing;
            if (!string.IsNullOrEmpty(n.requiresMission) && !Data.Cleared(n.requiresMission)) return MetaResult.Locked;
            if (Data.moonGold < NodeCostAt(n, level)) return MetaResult.NotEnoughMoonGold;
            return MetaResult.Ok;
        }

        public MetaResult BuyNode(string id, DateTime utcNow)
        {
            var can = CanBuyNode(id);
            if (can != MetaResult.Ok) return can;
            var n = C.NodeById[id];
            int level = Data.NodeLevel(id);
            Data.moonGold -= NodeCostAt(n, level);
            Data.nodes[id] = level + 1;
            Data.lifetime["permanent_levels"] = TotalNodeLevels();
            Save(utcNow);
            return MetaResult.Ok;
        }

        public int TotalNodeLevels()
        {
            int s = 0;
            foreach (var kv in Data.nodes) s += kv.Value;
            return s;
        }

        /// <summary>Factor from the permanent tree for a stat with base 1 (econ.moonGold, econ.offline).</summary>
        public float PermanentFactor(string stat)
        {
            var set = new ModifierSet();
            foreach (var kv in Data.nodes)
                if (C.NodeById.TryGetValue(kv.Key, out var n)) set.Apply(n.mods, Math.Min(kv.Value, n.maxLevel));
            return set.Factor(stat);
        }

        // ---- modules ------------------------------------------------------------------------------
        public ModuleState GetModuleState(string id)
        {
            if (Data.modulesUnlocked.Contains(id)) return ModuleState.Unlocked;
            if (Data.modulesAvailable.Contains(id)) return ModuleState.Available;
            return ModuleState.Locked;
        }

        public MetaResult UnlockModule(string id, DateTime utcNow)
        {
            var def = C.Module(id);
            if (def == null) return MetaResult.Unknown;
            var state = GetModuleState(id);
            if (state == ModuleState.Unlocked) return MetaResult.AlreadyClaimed;
            if (state == ModuleState.Locked) return MetaResult.Locked;
            if (Data.stormShards < def.unlockShards) return MetaResult.NotEnoughShards;
            if (!TryClaim("module:" + id)) return MetaResult.AlreadyClaimed;
            Data.stormShards -= def.unlockShards;
            Data.modulesAvailable.Remove(id);
            Data.modulesUnlocked.Add(id);
            Data.lifetime["modules_unlocked"] = Data.modulesUnlocked.Count;
            Save(utcNow);
            return MetaResult.Ok;
        }

        public int TierCost(string id)
        {
            var def = C.Module(id);
            if (def == null) return int.MaxValue;
            int next = Data.ModuleTier(id) + 1;
            foreach (var t in def.tiers) if (t.tier == next) return t.moonGold;
            return int.MaxValue;
        }

        public int MaxTier(string id)
        {
            var def = C.Module(id);
            int max = 1;
            if (def != null) foreach (var t in def.tiers) max = Math.Max(max, t.tier);
            return max;
        }

        public MetaResult UpgradeModuleTier(string id, DateTime utcNow)
        {
            if (C.Module(id) == null) return MetaResult.Unknown;
            if (GetModuleState(id) != ModuleState.Unlocked) return MetaResult.Locked;
            int tier = Data.ModuleTier(id);
            if (tier >= MaxTier(id)) return MetaResult.MaxLevel;
            int cost = TierCost(id);
            if (Data.moonGold < cost) return MetaResult.NotEnoughMoonGold;
            Data.moonGold -= cost;
            Data.moduleTiers[id] = tier + 1;
            Save(utcNow);
            return MetaResult.Ok;
        }

        /// <summary>Visual tier (1-3) for station sprites from the permanent tier (1-5).</summary>
        public static int VisualTier(int tier) => tier >= 5 ? 3 : (tier >= 3 ? 2 : 1);

        // ---- missions ---------------------------------------------------------------------------
        public bool IsMissionUnlocked(MissionDef m)
        {
            if (m == null) return false;
            if (string.IsNullOrEmpty(m.requiresMission)) return true;
            return Data.Cleared(m.requiresMission);
        }

        public MissionDef NextCampaignMission()
        {
            foreach (var m in C.Missions)
                if (IsMissionUnlocked(m) && !Data.Cleared(m.id)) return m;
            return C.Missions.Count > 0 ? C.Missions[C.Missions.Count - 1] : null;
        }

        public int HighestClearedIndex()
        {
            int best = 0;
            foreach (var m in C.Missions) if (Data.Cleared(m.id)) best = Math.Max(best, m.index);
            return best;
        }

        public bool EndlessUnlocked => Data.Cleared(C.Endless.requiresMission);
        public bool DailyUnlocked => Data.Cleared(C.Daily.requiresMission);

        // ---- loadout -----------------------------------------------------------------------------
        public MetaResult SetSlot(string slot, string moduleId, DateTime utcNow)
        {
            if (!C.SlotById.ContainsKey(slot)) return MetaResult.InvalidInput;
            if (!Data.slotsUnlocked.Contains(slot)) return MetaResult.Locked;
            if (string.IsNullOrEmpty(moduleId))
            {
                Data.loadout.Remove(slot);
                Save(utcNow);
                return MetaResult.Ok;
            }
            if (GetModuleState(moduleId) != ModuleState.Unlocked) return MetaResult.Locked;
            // a module can occupy only one slot: moving it swaps with whatever was there
            string from = StatsBuilder.SlotOf(Data.loadout, moduleId);
            Data.loadout.TryGetValue(slot, out var previous);
            Data.loadout[slot] = moduleId;
            if (from != null && from != slot)
            {
                if (!string.IsNullOrEmpty(previous)) Data.loadout[from] = previous;
                else Data.loadout.Remove(from);
            }
            Save(utcNow);
            return MetaResult.Ok;
        }

        private void RepairLoadout()
        {
            var fixedLoadout = new Dictionary<string, string>();
            var used = new HashSet<string>();
            foreach (var kv in Data.loadout)
            {
                if (!Data.slotsUnlocked.Contains(kv.Key) || !C.SlotById.ContainsKey(kv.Key)) continue;
                if (string.IsNullOrEmpty(kv.Value) || !Data.modulesUnlocked.Contains(kv.Value) || !used.Add(kv.Value)) continue;
                fixedLoadout[kv.Key] = kv.Value;
            }
            if (fixedLoadout.Count == 0 && Data.modulesUnlocked.Contains("arc_coil")) fixedLoadout["middle"] = "arc_coil";
            Data.loadout = fixedLoadout;
        }

        // ---- battle setup --------------------------------------------------------------------------
        public BattleSetup CreateCampaignSetup(string missionId, ulong seed, bool reviveAllowed)
        {
            var s = BaseSetup(seed, reviveAllowed);
            s.mode = BattleMode.Campaign;
            s.missionId = missionId;
            return s;
        }

        public BattleSetup CreateEndlessSetup(ulong seed, bool reviveAllowed)
        {
            var s = BaseSetup(seed, reviveAllowed);
            s.mode = BattleMode.Endless;
            s.missionId = "endless";
            return s;
        }

        public BattleSetup CreateDailySetup(DailyChallengeConfig cfg)
        {
            var s = new BattleSetup
            {
                mode = BattleMode.Daily,
                missionId = "daily",
                seed = cfg.seed,
                ignorePermanent = true,
                reviveAllowed = false,
                priority = Data.defaultPriority,
                heroSkin = Data.heroSkin,
                dailyBoss = cfg.boss,
            };
            foreach (var kv in cfg.loadout) { s.loadout[kv.Key] = kv.Value; s.unlockedSlots.Add(kv.Key); }
            s.extraModifiers.AddRange(cfg.modifiers);
            return s;
        }

        private BattleSetup BaseSetup(ulong seed, bool reviveAllowed)
        {
            var s = new BattleSetup
            {
                seed = seed,
                priority = Data.defaultPriority,
                reviveAllowed = reviveAllowed,
                heroSkin = Data.heroSkin,
            };
            foreach (var kv in Data.loadout) s.loadout[kv.Key] = kv.Value;
            s.unlockedSlots.AddRange(Data.slotsUnlocked);
            s.availableModules.AddRange(Data.modulesUnlocked);
            foreach (var kv in Data.nodes) s.nodeLevels[kv.Key] = kv.Value;
            foreach (var kv in Data.moduleTiers) s.moduleTiers[kv.Key] = kv.Value;
            return s;
        }

        public static DailyChallengeConfig DailyChallenge(GameContent c, DateTime utcNow)
        {
            string date = utcNow.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
            ulong seed = Hash.Fnv1a64("evilcats-daily:" + date);
            var rng = new Rng(seed, 77u);
            var cfg = new DailyChallengeConfig { dateUtc = date, seed = seed };
            var ids = new List<string>();
            foreach (var m in c.Modules) ids.Add(m.id);
            rng.Shuffle(ids);
            for (int i = 0; i < 3 && i < ids.Count && i < c.Tuning.slots.Count; i++)
                cfg.loadout[c.Tuning.slots[i].id] = ids[i];
            if (c.Daily.modifierChoices.Count > 0) cfg.modifiers.Add(rng.Pick(c.Daily.modifierChoices));
            if (c.Daily.bossChoices.Count > 0) cfg.boss = rng.Pick(c.Daily.bossChoices);
            return cfg;
        }

        // ---- checkpoints ------------------------------------------------------------------------------
        public void CommitCheckpoint(RunCheckpoint cp, DateTime utcNow)
        {
            cp.savedAtUtc = utcNow.ToString("o");
            Data.activeRun = cp;
            foreach (var slot in cp.unlockedSlots) if (!Data.slotsUnlocked.Contains(slot) && C.SlotById.ContainsKey(slot)) Data.slotsUnlocked.Add(slot);
            Save(utcNow);
        }

        public void ClearCheckpoint(DateTime utcNow)
        {
            if (Data.activeRun == null) return;
            Data.activeRun = null;
            Save(utcNow);
        }

        /// <summary>A slot unlocked during a run is permanent immediately (saved even if the run is lost).</summary>
        public void UnlockSlot(string slot, DateTime utcNow)
        {
            if (!C.SlotById.ContainsKey(slot) || Data.slotsUnlocked.Contains(slot)) return;
            Data.slotsUnlocked.Add(slot);
            Save(utcNow);
        }

        // ---- run results ---------------------------------------------------------------------------
        /// <summary>
        /// Applies a finished run exactly once (ledger id "run:{runId}:result"). Permanent
        /// rewards earned are always kept; temporary run purchases are not carried over.
        /// </summary>
        public RewardSummary ApplyRunResult(RunResult r, DateTime utcNow, DateTime localNow)
        {
            var sum = new RewardSummary();
            if (!TryClaim("run:" + r.runId + ":result"))
            {
                sum.alreadyApplied = true;
                return sum;
            }
            if (Data.activeRun != null && Data.activeRun.runId == r.runId) Data.activeRun = null;
            foreach (var slot in r.unlockedSlots)
                if (C.SlotById.ContainsKey(slot) && !Data.slotsUnlocked.Contains(slot)) { Data.slotsUnlocked.Add(slot); sum.slotsUnlocked.Add(slot); }

            float mgFactor = r.mode == BattleMode.Daily ? 1f : PermanentFactor("econ.moonGold");
            switch (r.mode)
            {
                case BattleMode.Campaign: ApplyCampaign(r, sum, mgFactor, utcNow); break;
                case BattleMode.Daily: ApplyDaily(r, sum, utcNow); break;
                case BattleMode.Endless: ApplyEndless(r, sum, mgFactor); break;
            }
            Data.moonGold += sum.moonGold;
            Data.stormShards += sum.stormShards;
            AccumulateStats(r, localNow);
            foreach (var a in C.Progression.achievements) if (AchievementReady(a.id)) sum.achievementsReady.Add(a.id);
            foreach (var o in Data.daily.objectives) if (ObjectiveReady(o)) sum.objectivesReady.Add(o);
            Save(utcNow);
            return sum;
        }

        private void ApplyCampaign(RunResult r, RewardSummary sum, float mgFactor, DateTime utcNow)
        {
            var m = C.Mission(r.missionId);
            if (m == null) return;
            var rec = Data.Mission(m.id);
            rec.attempts++;
            if (r.wavesCleared > rec.bestWave) { rec.bestWave = r.wavesCleared; sum.newRecord = true; }
            if (r.victory)
            {
                bool first = !rec.cleared;
                rec.cleared = true;
                rec.clears++;
                if (rec.bestTimeSec <= 0f || r.stats.timeSec < rec.bestTimeSec) rec.bestTimeSec = r.stats.timeSec;
                float frac = first ? 1f : C.Tuning.economy.replayMoonGoldFraction;
                sum.moonGold = (long)Math.Floor(m.moonGold * frac * mgFactor);
                if (first && TryClaim("firstclear:" + m.id))
                {
                    sum.firstClear = true;
                    sum.stormShards = m.firstClearShards;
                    if (!string.IsNullOrEmpty(m.unlocksModule)) MakeModuleAvailable(m.unlocksModule, sum);
                    if (Data.offline.stampUtcTicks == 0) Data.offline.stampUtcTicks = utcNow.Ticks;
                    if (m.id == "m06") sum.chapterScene = "gravewood";
                    if (m.id == "m12") sum.chapterScene = "moonfall";
                }
            }
            else
            {
                float frac = C.Tuning.economy.defeatMoonGoldFraction * (r.totalWaves > 0 ? (float)r.wavesCleared / r.totalWaves : 0f);
                sum.moonGold = r.wavesCleared > 0 ? Math.Max(5L, (long)Math.Floor(m.moonGold * frac * mgFactor)) : 0L;
            }
        }

        private void MakeModuleAvailable(string moduleId, RewardSummary sum)
        {
            var def = C.Module(moduleId);
            if (def == null || Data.modulesUnlocked.Contains(moduleId)) return;
            sum.moduleUnlocked = moduleId;
            if (def.unlockShards <= 0)
            {
                Data.modulesUnlocked.Add(moduleId);
                Data.modulesAvailable.Remove(moduleId);
                Data.lifetime["modules_unlocked"] = Data.modulesUnlocked.Count;
            }
            else
            {
                if (!Data.modulesAvailable.Contains(moduleId)) Data.modulesAvailable.Add(moduleId);
                sum.moduleNeedsShards = true;
            }
        }

        private void ApplyDaily(RunResult r, RewardSummary sum, DateTime utcNow)
        {
            string date = utcNow.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);
            var d = Data.daily;
            if (d.challengeDate != date)
            {
                d.challengeDate = date;
                d.challengeBestScore = 0;
                d.challengeBestWave = 0;
                d.challengeAttempts = 0;
            }
            d.challengeAttempts++;
            if (r.score > d.challengeBestScore) { d.challengeBestScore = r.score; d.challengeBestWave = r.wavesCleared; sum.newRecord = true; }
            // Moon Gold only for the first finished attempt of the day, scaled by progress.
            if (TryClaim("dailychallenge:" + date))
            {
                float frac = r.victory ? 1f : (r.totalWaves > 0 ? (float)r.wavesCleared / r.totalWaves : 0f);
                sum.moonGold = (long)Math.Floor(C.Daily.moonGold * frac);
                Data.AddLifetime("daily_completed", 1);
            }
        }

        private void ApplyEndless(RunResult r, RewardSummary sum, float mgFactor)
        {
            var e = Data.endless;
            e.runs++;
            if (r.wavesCleared > e.bestWave) { e.bestWave = r.wavesCleared; sum.newRecord = true; }
            if (r.score > e.bestScore) e.bestScore = r.score;
            Data.MaxLifetime("endless_best", e.bestWave);
            sum.moonGold = (long)Math.Floor(C.Endless.moonGoldPerWave * r.wavesCleared * mgFactor);
        }

        private void AccumulateStats(RunResult r, DateTime localNow)
        {
            var s = r.stats;
            Data.AddLifetime("runs_played", 1);
            Data.AddLifetime(r.victory ? "victories" : "defeats", 1);
            Data.AddLifetime("kills", s.kills);
            Data.AddLifetime("elite_kills", s.eliteKills);
            Data.AddLifetime("freezes", s.freezes);
            Data.AddLifetime("burns", s.burnsApplied);
            Data.AddLifetime("pulls", s.pulls);
            Data.AddLifetime("barrier_absorbed", (long)s.barrierAbsorbed);
            Data.AddLifetime("powder_interrupts", s.powderInterrupts);
            Data.AddLifetime("storm_uses", s.stormUses);
            Data.AddLifetime("ward_uses", s.wardUses);
            Data.AddLifetime("upgrades_bought", s.upgradesBought);
            Data.AddLifetime("perks_taken", s.perksTaken);
            Data.AddLifetime("waves_cleared", s.wavesCleared);
            Data.MaxLifetime("max_chain", s.maxChain);
            Data.MaxLifetime("max_level", r.levelReached);
            foreach (var b in s.bossesDefeated) Data.AddLifetime("boss_" + b, 1);
            int cleared = 0;
            foreach (var m in C.Missions) if (Data.Cleared(m.id)) cleared++;
            Data.lifetime["missions_cleared"] = cleared;
            if (r.victory && s.minHealthFraction >= 0.5f) Data.AddLifetime("high_health_victories", 1);

            // Daily objective progress for today's local date.
            EnsureDaily(localNow);
            void P(string stat, long v) { if (v > 0) Data.daily.progress[stat] = (Data.daily.progress.TryGetValue(stat, out var n) ? n : 0) + v; }
            P("kills", s.kills); P("elite_kills", s.eliteKills); P("storm_uses", s.stormUses); P("ward_uses", s.wardUses);
            P("upgrades_bought", s.upgradesBought); P("perks_taken", s.perksTaken); P("waves_cleared", s.wavesCleared);
            P("burns", s.burnsApplied); P("freezes", s.freezes); P("pulls", s.pulls); P("barrier_absorbed", (long)s.barrierAbsorbed);
            if (r.victory) P("victories", 1);
        }

        // ---- achievements ------------------------------------------------------------------------------
        public long AchievementProgress(string id)
        {
            if (!C.AchievementById.TryGetValue(id, out var a)) return 0;
            return Data.Lifetime(a.stat);
        }

        public bool AchievementReady(string id) =>
            C.AchievementById.TryGetValue(id, out var a) && !Data.achievementsClaimed.Contains(id) && Data.Lifetime(a.stat) >= a.target;

        public MetaResult ClaimAchievement(string id, DateTime utcNow)
        {
            if (!C.AchievementById.TryGetValue(id, out var a)) return MetaResult.Unknown;
            if (Data.achievementsClaimed.Contains(id)) return MetaResult.AlreadyClaimed;
            if (Data.Lifetime(a.stat) < a.target) return MetaResult.NothingToClaim;
            if (!TryClaim("ach:" + id)) return MetaResult.AlreadyClaimed;
            Data.achievementsClaimed.Add(id);
            Grant(a.reward);
            Save(utcNow);
            return MetaResult.Ok;
        }

        private void Grant(RewardDef reward)
        {
            if (reward == null) return;
            Data.moonGold += reward.moonGold;
            Data.stormShards += reward.stormShards;
            if (!string.IsNullOrEmpty(reward.cosmetic) && !Data.cosmeticsOwned.Contains(reward.cosmetic)) Data.cosmeticsOwned.Add(reward.cosmetic);
        }

        // ---- daily objectives + attendance ------------------------------------------------------------
        public static string LocalDate(DateTime localNow) => localNow.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture);

        /// <summary>Rolls today's three objectives (deterministic per date and profile) when the date changes.</summary>
        public void EnsureDaily(DateTime localNow)
        {
            string date = LocalDate(localNow);
            var d = Data.daily;
            if (d.date == date && d.objectives.Count > 0) return;
            d.date = date;
            d.objectives.Clear();
            d.progress.Clear();
            d.claimed.Clear();
            var pool = new List<DailyObjectiveDef>();
            foreach (var o in C.Progression.dailyObjectives)
                if (string.IsNullOrEmpty(o.requiresMission) || Data.Cleared(o.requiresMission)) pool.Add(o);
            var rng = new Rng(Hash.Fnv1a64("objectives:" + date + ":" + Data.profileId), 91u);
            var usedStats = new HashSet<string>();
            int guard = 0;
            while (d.objectives.Count < 3 && pool.Count > 0 && guard++ < 50)
            {
                int i = rng.Range(0, pool.Count);
                var o = pool[i];
                pool.RemoveAt(i);
                if (!usedStats.Add(o.stat)) continue;   // three different kinds of task
                d.objectives.Add(o.id);
            }
        }

        public long ObjectiveProgress(string id)
        {
            if (!C.ObjectiveById.TryGetValue(id, out var o)) return 0;
            return Data.daily.progress.TryGetValue(o.stat, out var v) ? v : 0;
        }

        public bool ObjectiveReady(string id) =>
            C.ObjectiveById.TryGetValue(id, out var o) && Data.daily.objectives.Contains(id) &&
            !Data.daily.claimed.Contains(id) && ObjectiveProgress(id) >= o.target;

        public MetaResult ClaimObjective(string id, DateTime utcNow, DateTime localNow)
        {
            EnsureDaily(localNow);
            if (!C.ObjectiveById.TryGetValue(id, out var o)) return MetaResult.Unknown;
            if (!Data.daily.objectives.Contains(id)) return MetaResult.NotAvailable;
            if (Data.daily.claimed.Contains(id)) return MetaResult.AlreadyClaimed;
            if (ObjectiveProgress(id) < o.target) return MetaResult.NothingToClaim;
            if (!TryClaim("obj:" + Data.daily.date + ":" + id)) return MetaResult.AlreadyClaimed;
            Data.daily.claimed.Add(id);
            Grant(o.reward);
            Save(utcNow);
            return MetaResult.Ok;
        }

        public bool AttendanceAvailable(DateTime localNow, out bool clockBack)
        {
            string today = LocalDate(localNow);
            string last = Data.attendance.lastClaimDate;
            clockBack = last != null && string.CompareOrdinal(today, last) < 0;
            return last == null || string.CompareOrdinal(today, last) > 0;
        }

        /// <summary>
        /// One claim per calendar day. Missing days never reset the track (day index only
        /// advances when you claim). A clock set backwards cannot re-claim earlier days.
        /// </summary>
        public MetaResult ClaimAttendance(DateTime utcNow, DateTime localNow)
        {
            if (!AttendanceAvailable(localNow, out bool back)) return back ? MetaResult.ClockMovedBack : MetaResult.AlreadyClaimed;
            string today = LocalDate(localNow);
            if (!TryClaim("attend:" + today)) return MetaResult.AlreadyClaimed;
            var a = Data.attendance;
            var list = C.Progression.attendance;
            if (list.Count > 0) Grant(list[a.dayIndex % list.Count]);
            a.dayIndex = list.Count > 0 ? (a.dayIndex + 1) % list.Count : 0;
            a.lastClaimDate = today;
            a.totalClaims++;
            Data.lifetime["attendance_claims"] = a.totalClaims;
            Save(utcNow);
            return MetaResult.Ok;
        }

        // ---- offline Moon Gold ----------------------------------------------------------------------------
        /// <summary>Moon Gold per hour: (base + perMission × highest cleared mission) × offline bonus. 0 before any clear.</summary>
        public float OfflineRatePerHour()
        {
            int idx = HighestClearedIndex();
            if (idx <= 0) return 0f;
            var o = C.Tuning.offline;
            return (o.baseRatePerHour + o.ratePerMissionCleared * idx) * PermanentFactor("econ.offline");
        }

        public long OfflinePending(DateTime utcNow, out double hours, out bool clockBack)
        {
            hours = 0;
            clockBack = false;
            long stamp = Data.offline.stampUtcTicks;
            if (stamp == 0 || OfflineRatePerHour() <= 0f) return 0;
            long delta = utcNow.Ticks - stamp;
            if (delta < 0) { clockBack = true; return 0; }
            hours = Math.Min(TimeSpan.FromTicks(delta).TotalHours, C.Tuning.offline.capHours);
            return (long)Math.Floor(OfflineRatePerHour() * hours);
        }

        /// <summary>
        /// Collects offline Moon Gold (capped at 8 hours). Never grants combat victories or scores.
        /// A local clock moved backwards restarts accrual from now; this is not server-grade anti-cheat.
        /// </summary>
        public MetaResult CollectOffline(DateTime utcNow, out long amount)
        {
            amount = OfflinePending(utcNow, out double hours, out bool back);
            if (Data.offline.stampUtcTicks == 0) return MetaResult.Locked;
            if (back)
            {
                Data.offline.stampUtcTicks = utcNow.Ticks;
                Save(utcNow);
                return MetaResult.ClockMovedBack;
            }
            if (hours * 60.0 < C.Tuning.offline.minCollectMinutes || amount <= 0) return MetaResult.TooSoon;
            // the stamp itself is the transaction: moving it forward makes a second collect return 0
            Data.offline.stampUtcTicks = utcNow.Ticks;
            Data.offline.totalCollected += amount;
            Data.moonGold += amount;
            Data.AddLifetime("offline_collected", 1);
            Save(utcNow);
            return MetaResult.Ok;
        }

        // ---- cosmetics / profile ---------------------------------------------------------------------------
        public MetaResult BuyCosmetic(string id, DateTime utcNow)
        {
            if (!C.CosmeticById.TryGetValue(id, out var cos)) return MetaResult.Unknown;
            if (Data.cosmeticsOwned.Contains(id)) return MetaResult.AlreadyClaimed;
            if (cos.supporterOnly || !string.IsNullOrEmpty(cos.achievement)) return MetaResult.NotAvailable;
            if (Data.moonGold < cos.moonGold) return MetaResult.NotEnoughMoonGold;
            if (Data.stormShards < cos.stormShards) return MetaResult.NotEnoughShards;
            if (!TryClaim("cos:" + id)) return MetaResult.AlreadyClaimed;
            Data.moonGold -= cos.moonGold;
            Data.stormShards -= cos.stormShards;
            Data.cosmeticsOwned.Add(id);
            Save(utcNow);
            return MetaResult.Ok;
        }

        public MetaResult EquipCosmetic(string id, DateTime utcNow)
        {
            if (!C.CosmeticById.TryGetValue(id, out var cos)) return MetaResult.Unknown;
            if (!Data.cosmeticsOwned.Contains(id)) return MetaResult.Locked;
            if (cos.kind == "hero_skin") Data.heroSkin = id;
            else if (cos.kind == "banner") Data.banner = id;
            Save(utcNow);
            return MetaResult.Ok;
        }

        public static bool ValidDisplayName(string name)
        {
            if (string.IsNullOrWhiteSpace(name)) return false;
            name = name.Trim();
            if (name.Length < 3 || name.Length > 16) return false;
            foreach (char ch in name) if (!(char.IsLetterOrDigit(ch) || ch == ' ' || ch == '_' || ch == '-')) return false;
            return true;
        }

        public MetaResult SetDisplayName(string name, DateTime utcNow)
        {
            if (!ValidDisplayName(name)) return MetaResult.InvalidInput;
            Data.displayName = name.Trim();
            Save(utcNow);
            return MetaResult.Ok;
        }

        public MetaResult SetAvatar(string avatar, DateTime utcNow)
        {
            if (!C.Progression.avatars.Contains(avatar)) return MetaResult.InvalidInput;
            Data.avatar = avatar;
            Save(utcNow);
            return MetaResult.Ok;
        }
    }
}
