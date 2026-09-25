using System;
using System.Collections.Generic;
using System.IO;
using EvilCats.Content;
using EvilCats.Meta;
using EvilCats.Sim;
using NUnit.Framework;

namespace EvilCats.Tests
{
    public class SaveTests
    {
        private static readonly DateTime T0 = new DateTime(2026, 3, 1, 10, 0, 0, DateTimeKind.Utc);

        [Test]
        public void FirstLaunchCreatesAFreshProfile()
        {
            var mgr = new SaveManager(new MemorySaveStore());
            var r = mgr.Load(T0);
            Assert.That(r.outcome, Is.EqualTo(LoadOutcome.NewProfile));
            Assert.That(r.data.modulesUnlocked, Contains.Item("arc_coil"));
            Assert.That(r.data.slotsUnlocked, Is.EqualTo(new List<string> { "middle" }));
            Assert.That(r.data.moonGold, Is.EqualTo(0));
        }

        [Test]
        public void SaveAndLoadRoundTrips()
        {
            var store = new MemorySaveStore();
            var mgr = new SaveManager(store);
            var d = SaveManager.NewProfile(T0);
            d.moonGold = 1234; d.stormShards = 3; d.displayName = "Whiskers";
            d.nodes["pm_walls"] = 2;
            d.Mission("m01").cleared = true;
            d.settings.music = 0.25f;
            Assert.That(mgr.Save(d, T0), Is.True);
            var r = mgr.Load(T0);
            Assert.That(r.outcome, Is.EqualTo(LoadOutcome.Loaded));
            Assert.That(r.data.moonGold, Is.EqualTo(1234));
            Assert.That(r.data.displayName, Is.EqualTo("Whiskers"));
            Assert.That(r.data.NodeLevel("pm_walls"), Is.EqualTo(2));
            Assert.That(r.data.Cleared("m01"), Is.True);
            Assert.That(r.data.settings.music, Is.EqualTo(0.25f));
        }

        [Test]
        public void CorruptPrimaryRecoversFromBackupAndKeepsACopy()
        {
            var store = new MemorySaveStore();
            var mgr = new SaveManager(store);
            var d = SaveManager.NewProfile(T0);
            d.moonGold = 100;
            mgr.Save(d, T0);
            d.moonGold = 200;
            mgr.Save(d, T0);            // backup now holds 100, primary 200
            store.Primary = store.Primary.Substring(0, store.Primary.Length / 2);   // truncated write
            var r = mgr.Load(T0);
            Assert.That(r.outcome, Is.EqualTo(LoadOutcome.RecoveredFromBackup));
            Assert.That(r.data.moonGold, Is.EqualTo(100));
            Assert.That(store.Quarantined.Count, Is.EqualTo(1), "the damaged file is kept, not silently deleted");
        }

        [Test]
        public void TamperedChecksumIsDetected()
        {
            var store = new MemorySaveStore();
            var mgr = new SaveManager(store);
            var d = SaveManager.NewProfile(T0);
            d.moonGold = 50;
            mgr.Save(d, T0);
            store.Primary = store.Primary.Replace("50", "99");
            Assert.That(SaveSerializer.TryParse(store.Primary, out _, out var why), Is.Null);
            Assert.That(why, Does.Contain("checksum"));
        }

        [Test]
        public void BothFilesUnreadableStartsFreshAndKeepsCopies()
        {
            var store = new MemorySaveStore { Primary = "{not json", Backup = "garbage" };
            var r = new SaveManager(store).Load(T0);
            Assert.That(r.outcome, Is.EqualTo(LoadOutcome.ResetAfterCorruption));
            Assert.That(store.Quarantined.Count, Is.EqualTo(2));
        }

        [Test]
        public void PrototypeV1SaveMigratesToCurrentVersion()
        {
            string v1 = "{\"version\":1,\"gold\":321,\"shards\":4,\"unlocked\":[\"arc_coil\",\"ember_maw\",\"frost_whisker\"]," +
                        "\"missionsCleared\":[\"m01\",\"m02\"],\"settings\":{\"musicVolume\":0.3,\"sfxVolume\":0.6}}";
            var r = new SaveManager(new MemorySaveStore { Primary = v1 }).Load(T0);
            Assert.That(r.outcome, Is.EqualTo(LoadOutcome.Migrated));
            Assert.That(r.fromVersion, Is.EqualTo(1));
            Assert.That(r.data.version, Is.EqualTo(SaveData.CurrentVersion));
            Assert.That(r.data.moonGold, Is.EqualTo(321));
            Assert.That(r.data.stormShards, Is.EqualTo(4));
            Assert.That(r.data.modulesUnlocked, Contains.Item("frost_whisker"));
            Assert.That(r.data.Cleared("m02"), Is.True);
            Assert.That(r.data.settings.music, Is.EqualTo(0.3f).Within(1e-5f));
        }

        [Test]
        public void SaveFromNewerGameVersionIsNotOverwrittenBlindly()
        {
            var d = SaveManager.NewProfile(T0);
            string text = SaveSerializer.Serialize(d, T0).Replace("\"version\":" + SaveData.CurrentVersion, "\"version\":99");
            Assert.That(SaveSerializer.TryParse(text, out _, out var why), Is.Null);
            Assert.That(why, Does.Contain("newer"));
        }

        [Test]
        public void NullFieldsAreRepairedOnLoad()
        {
            var d = SaveManager.NewProfile(T0);
            d.daily = null; d.settings = null; d.ledger = null; d.loadout = null;
            var text = SaveSerializer.Serialize(d, T0);
            var loaded = SaveSerializer.TryParse(text, out _, out _);
            Assert.That(loaded.daily, Is.Not.Null);
            Assert.That(loaded.settings, Is.Not.Null);
            Assert.That(loaded.ledger, Is.Not.Null);
        }

        [Test]
        public void FailedWriteLeavesThePreviousSaveIntact()
        {
            var store = new MemorySaveStore();
            var mgr = new SaveManager(store);
            var d = SaveManager.NewProfile(T0);
            d.moonGold = 10;
            mgr.Save(d, T0);
            store.FailNextWrite = true;
            d.moonGold = 20;
            Assert.That(mgr.Save(d, T0), Is.False);
            Assert.That(mgr.Load(T0).data.moonGold, Is.EqualTo(10));
        }

        [Test]
        public void FileStoreWritesAtomicallyWithBackup()
        {
            string dir = Path.Combine(Path.GetTempPath(), "evilcats_test_" + Guid.NewGuid().ToString("N"));
            try
            {
                var store = new FileSaveStore(dir);
                var mgr = new SaveManager(store);
                var d = SaveManager.NewProfile(T0);
                d.moonGold = 1; mgr.Save(d, T0);
                d.moonGold = 2; mgr.Save(d, T0);
                Assert.That(File.Exists(store.PrimaryPath), Is.True);
                Assert.That(File.Exists(store.BackupPath), Is.True);
                Assert.That(mgr.Load(T0).data.moonGold, Is.EqualTo(2));
                File.WriteAllText(store.PrimaryPath, "{broken");
                var r = mgr.Load(T0);
                Assert.That(r.outcome, Is.EqualTo(LoadOutcome.RecoveredFromBackup));
                Assert.That(r.data.moonGold, Is.EqualTo(1));
            }
            finally
            {
                if (Directory.Exists(dir)) Directory.Delete(dir, true);
            }
        }
    }

    public class MetaTests
    {
        private static readonly DateTime T0 = new DateTime(2026, 3, 1, 10, 0, 0, DateTimeKind.Utc);

        private static GameMeta NewMeta(out MemorySaveStore store)
        {
            store = new MemorySaveStore();
            var mgr = new SaveManager(store);
            return new GameMeta(TestContent.Load(), SaveManager.NewProfile(T0), mgr);
        }

        private static RunResult Result(string mission, bool victory, int waves, string runId = null)
        {
            return new RunResult
            {
                runId = runId ?? Guid.NewGuid().ToString("N"), mode = BattleMode.Campaign, missionId = mission,
                victory = victory, wavesCleared = waves, totalWaves = TestContent.Load().Mission(mission).waves,
                levelReached = 5, healthFraction = 0.5f, stats = new RunStats { kills = 100, wavesCleared = waves, minHealthFraction = 0.6f },
            };
        }

        [Test]
        public void RunRewardsAreAppliedExactlyOnce()
        {
            var meta = NewMeta(out _);
            var r = Result("m01", true, 10, "run-A");
            var first = meta.ApplyRunResult(r, T0, T0);
            long gold = meta.Data.moonGold;
            var again = meta.ApplyRunResult(r, T0, T0);
            Assert.That(first.alreadyApplied, Is.False);
            Assert.That(again.alreadyApplied, Is.True);
            Assert.That(meta.Data.moonGold, Is.EqualTo(gold), "repeated callback / relaunch does not pay twice");
            Assert.That(meta.Data.Lifetime("kills"), Is.EqualTo(100));
        }

        [Test]
        public void FirstClearGrantsShardsAndUnlocksTheNextStation()
        {
            var meta = NewMeta(out _);
            var s = meta.ApplyRunResult(Result("m01", true, 10), T0, T0);
            Assert.That(s.firstClear, Is.True);
            Assert.That(s.stormShards, Is.EqualTo(1));
            Assert.That(meta.Data.modulesUnlocked, Contains.Item("frost_whisker"), "free milestone unlock");
            var s2 = meta.ApplyRunResult(Result("m01", true, 10), T0, T0);
            Assert.That(s2.firstClear, Is.False);
            Assert.That(s2.stormShards, Is.EqualTo(0));
            Assert.That(s2.moonGold, Is.LessThan(s.moonGold), "replays pay a reduced amount");
        }

        [Test]
        public void DefeatKeepsProportionalPermanentRewards()
        {
            var meta = NewMeta(out _);
            var s = meta.ApplyRunResult(Result("m02", false, 10), T0, T0);
            var m = TestContent.Load().Mission("m02");
            Assert.That(s.moonGold, Is.EqualTo((long)Math.Floor(m.moonGold * 0.4 * 10 / 20.0)));
            Assert.That(meta.Data.Mission("m02").bestWave, Is.EqualTo(10));
            Assert.That(meta.Data.Cleared("m02"), Is.False);
        }

        [Test]
        public void MissionsUnlockInOrder()
        {
            var meta = NewMeta(out _);
            var c = TestContent.Load();
            Assert.That(meta.IsMissionUnlocked(c.Mission("m01")), Is.True);
            Assert.That(meta.IsMissionUnlocked(c.Mission("m02")), Is.False);
            meta.ApplyRunResult(Result("m01", true, 10), T0, T0);
            Assert.That(meta.IsMissionUnlocked(c.Mission("m02")), Is.True);
            Assert.That(meta.NextCampaignMission().id, Is.EqualTo("m02"));
        }

        [Test]
        public void PermanentNodesRespectCostPrerequisitesAndCaps()
        {
            var meta = NewMeta(out _);
            Assert.That(meta.BuyNode("pm_walls", T0), Is.EqualTo(MetaResult.NotEnoughMoonGold));
            meta.Data.moonGold = 100000;
            Assert.That(meta.BuyNode("pm_mend", T0), Is.EqualTo(MetaResult.RequirementMissing));
            Assert.That(meta.BuyNode("pm_walls", T0), Is.EqualTo(MetaResult.Ok));
            Assert.That(meta.BuyNode("pm_mend", T0), Is.EqualTo(MetaResult.Ok));
            for (int i = 0; i < 10; i++) meta.BuyNode("pm_walls", T0);
            Assert.That(meta.Data.NodeLevel("pm_walls"), Is.EqualTo(5));
            Assert.That(meta.BuyNode("pm_walls", T0), Is.EqualTo(MetaResult.MaxLevel));
        }

        [Test]
        public void ModuleUnlockNeedsMilestoneThenShards()
        {
            var meta = NewMeta(out _);
            Assert.That(meta.GetModuleState("bone_ballista"), Is.EqualTo(ModuleState.Locked));
            Assert.That(meta.UnlockModule("bone_ballista", T0), Is.EqualTo(MetaResult.Locked));
            meta.Data.missions["m01"] = new MissionRecord { cleared = true };
            meta.Data.missions["m02"] = new MissionRecord { cleared = true };
            var s = meta.ApplyRunResult(Result("m03", true, 20), T0, T0);
            Assert.That(s.moduleUnlocked, Is.EqualTo("bone_ballista"));
            Assert.That(meta.GetModuleState("bone_ballista"), Is.EqualTo(ModuleState.Available));
            meta.Data.stormShards = 0;
            Assert.That(meta.UnlockModule("bone_ballista", T0), Is.EqualTo(MetaResult.NotEnoughShards));
            meta.Data.stormShards = 5;
            Assert.That(meta.UnlockModule("bone_ballista", T0), Is.EqualTo(MetaResult.Ok));
            Assert.That(meta.UnlockModule("bone_ballista", T0), Is.EqualTo(MetaResult.AlreadyClaimed));
            Assert.That(meta.Data.stormShards, Is.EqualTo(3));
        }

        [Test]
        public void LoadoutMovesSwapModulesAndRespectLockedSlots()
        {
            var meta = NewMeta(out _);
            Assert.That(meta.SetSlot("crown", "ember_maw", T0), Is.EqualTo(MetaResult.Locked), "crown locked at start");
            meta.Data.slotsUnlocked.Add("crown");
            Assert.That(meta.SetSlot("crown", "ember_maw", T0), Is.EqualTo(MetaResult.Ok));
            Assert.That(meta.SetSlot("crown", "arc_coil", T0), Is.EqualTo(MetaResult.Ok));
            Assert.That(meta.Data.loadout["crown"], Is.EqualTo("arc_coil"));
            Assert.That(meta.Data.loadout["middle"], Is.EqualTo("ember_maw"), "moving a module swaps it");
            Assert.That(meta.SetSlot("middle", "gravity_paw", T0), Is.EqualTo(MetaResult.Locked), "locked module");
        }

        [Test]
        public void AchievementClaimsAreIdempotent()
        {
            var meta = NewMeta(out var store);
            Assert.That(meta.ClaimAchievement("ach_first_victory", T0), Is.EqualTo(MetaResult.NothingToClaim));
            meta.ApplyRunResult(Result("m01", true, 10), T0, T0);
            long gold = meta.Data.moonGold;
            Assert.That(meta.ClaimAchievement("ach_first_victory", T0), Is.EqualTo(MetaResult.Ok));
            Assert.That(meta.ClaimAchievement("ach_first_victory", T0), Is.EqualTo(MetaResult.AlreadyClaimed));
            Assert.That(meta.Data.moonGold, Is.EqualTo(gold + 50));
            // survives a restart: reload from the store and try again
            var reloaded = new GameMeta(TestContent.Load(), new SaveManager(store).Load(T0).data);
            Assert.That(reloaded.ClaimAchievement("ach_first_victory", T0), Is.EqualTo(MetaResult.AlreadyClaimed));
        }

        [Test]
        public void AttendanceNeverPunishesMissedDays()
        {
            var meta = NewMeta(out _);
            var day1 = new DateTime(2026, 3, 1, 9, 0, 0);
            Assert.That(meta.ClaimAttendance(day1, day1), Is.EqualTo(MetaResult.Ok));
            Assert.That(meta.ClaimAttendance(day1, day1.AddHours(5)), Is.EqualTo(MetaResult.AlreadyClaimed), "one per day");
            var day5 = day1.AddDays(4);                       // skipped three days
            Assert.That(meta.ClaimAttendance(day5, day5), Is.EqualTo(MetaResult.Ok));
            Assert.That(meta.Data.attendance.dayIndex, Is.EqualTo(2), "progress continues, not reset");
            Assert.That(meta.ClaimAttendance(day1.AddDays(2), day1.AddDays(2)), Is.EqualTo(MetaResult.ClockMovedBack));
        }

        [Test]
        public void SeventhAttendanceDayGivesAShardAndWraps()
        {
            var meta = NewMeta(out _);
            var d = new DateTime(2026, 3, 1, 9, 0, 0);
            for (int i = 0; i < 7; i++) meta.ClaimAttendance(d.AddDays(i), d.AddDays(i));
            Assert.That(meta.Data.stormShards, Is.EqualTo(1));
            Assert.That(meta.Data.attendance.dayIndex, Is.EqualTo(0));
            Assert.That(meta.Data.attendance.totalClaims, Is.EqualTo(7));
        }

        [Test]
        public void OfflineGoldIsCappedAtEightHoursAndNeedsProgress()
        {
            var meta = NewMeta(out _);
            Assert.That(meta.CollectOffline(T0, out _), Is.EqualTo(MetaResult.Locked), "nothing before the first clear");
            meta.ApplyRunResult(Result("m01", true, 10), T0, T0);
            float rate = meta.OfflineRatePerHour();
            Assert.That(rate, Is.EqualTo(4f + 2f * 1).Within(1e-3f));
            Assert.That(meta.CollectOffline(T0.AddDays(3), out long amount), Is.EqualTo(MetaResult.Ok));
            Assert.That(amount, Is.EqualTo((long)Math.Floor(rate * 8)), "capped at 8 hours");
            Assert.That(meta.CollectOffline(T0.AddDays(3).AddMinutes(1), out _), Is.EqualTo(MetaResult.TooSoon), "cannot collect twice");
        }

        [Test]
        public void OfflineClockMovedBackwardsGrantsNothing()
        {
            var meta = NewMeta(out _);
            meta.ApplyRunResult(Result("m01", true, 10), T0, T0);
            long before = meta.Data.moonGold;
            Assert.That(meta.CollectOffline(T0.AddHours(-5), out long amt), Is.EqualTo(MetaResult.ClockMovedBack));
            Assert.That(amt, Is.EqualTo(0));
            Assert.That(meta.Data.moonGold, Is.EqualTo(before));
        }

        [Test]
        public void DailyObjectivesRollDistinctlyAndClaimOnce()
        {
            var meta = NewMeta(out _);
            var local = new DateTime(2026, 3, 1, 12, 0, 0);
            meta.EnsureDaily(local);
            Assert.That(meta.Data.daily.objectives.Count, Is.EqualTo(3));
            Assert.That(new HashSet<string>(meta.Data.daily.objectives).Count, Is.EqualTo(3));
            // fulfil everything with one huge run
            var r = Result("m01", true, 10);
            r.stats = new RunStats { kills = 1000, eliteKills = 50, stormUses = 50, wardUses = 50, upgradesBought = 100, perksTaken = 50,
                wavesCleared = 100, burnsApplied = 500, freezes = 200, pulls = 200, barrierAbsorbed = 9000 };
            meta.ApplyRunResult(r, T0, local);
            string id = meta.Data.daily.objectives[0];
            Assert.That(meta.ObjectiveReady(id), Is.True);
            Assert.That(meta.ClaimObjective(id, T0, local), Is.EqualTo(MetaResult.Ok));
            Assert.That(meta.ClaimObjective(id, T0, local), Is.EqualTo(MetaResult.AlreadyClaimed));
            meta.EnsureDaily(local.AddDays(1));
            Assert.That(meta.Data.daily.claimed, Is.Empty, "new day, new objectives");
        }

        [Test]
        public void DailyChallengeIsReproducibleForADate()
        {
            var c = TestContent.Load();
            var a = GameMeta.DailyChallenge(c, new DateTime(2026, 4, 2, 1, 0, 0, DateTimeKind.Utc));
            var b = GameMeta.DailyChallenge(c, new DateTime(2026, 4, 2, 23, 0, 0, DateTimeKind.Utc));
            var d = GameMeta.DailyChallenge(c, new DateTime(2026, 4, 3, 1, 0, 0, DateTimeKind.Utc));
            Assert.That(b.seed, Is.EqualTo(a.seed));
            Assert.That(b.loadout, Is.EqualTo(a.loadout));
            Assert.That(b.boss, Is.EqualTo(a.boss));
            Assert.That(d.seed, Is.Not.EqualTo(a.seed));
            Assert.That(a.loadout.Count, Is.EqualTo(3));
            Assert.That(new HashSet<string>(a.loadout.Values).Count, Is.EqualTo(3));
        }

        [Test]
        public void DailyChallengeRewardOnlyOncePerDay()
        {
            var meta = NewMeta(out _);
            var r1 = new RunResult { runId = "d1", mode = BattleMode.Daily, missionId = "daily", victory = true, wavesCleared = 15, totalWaves = 15, score = 100, stats = new RunStats() };
            var r2 = new RunResult { runId = "d2", mode = BattleMode.Daily, missionId = "daily", victory = true, wavesCleared = 15, totalWaves = 15, score = 200, stats = new RunStats() };
            var s1 = meta.ApplyRunResult(r1, T0, T0);
            var s2 = meta.ApplyRunResult(r2, T0.AddHours(1), T0.AddHours(1));
            Assert.That(s1.moonGold, Is.GreaterThan(0));
            Assert.That(s2.moonGold, Is.EqualTo(0));
            Assert.That(meta.Data.daily.challengeBestScore, Is.EqualTo(200), "records still update");
        }

        [Test]
        public void DailyRunFinishedAfterMidnightCountsForItsChallengeDay()
        {
            var content = TestContent.Load();
            var meta = NewMeta(out _);
            var lateEvening = new DateTime(2026, 9, 25, 23, 50, 0, DateTimeKind.Utc);
            var setup = meta.CreateDailySetup(GameMeta.DailyChallenge(content, lateEvening));
            Assert.That(setup.dailyDate, Is.EqualTo("2026-09-25"));
            setup.emitEvents = false;
            var b = new Battle(content, setup);
            var cp = Json.Deserialize<RunCheckpoint>(Json.Serialize(b.TakeCheckpoint()));
            Assert.That(cp.dailyDate, Is.EqualTo("2026-09-25"), "the checkpoint keeps the challenge's own date");

            // finished 30 minutes later, on the next UTC day
            var nextDay = lateEvening.AddMinutes(30);
            var r = b.BuildResult();
            r.victory = true;
            r.wavesCleared = r.totalWaves;
            meta.ApplyRunResult(r, nextDay, nextDay);
            Assert.That(meta.Data.daily.challengeDate, Is.EqualTo("2026-09-25"));
            Assert.That(meta.Data.ledger, Contains.Item("dailychallenge:2026-09-25"));
            Assert.That(meta.Data.ledger, Has.No.Member("dailychallenge:2026-09-26"), "the next day's reward is still available");

            // an older day's run never resets a newer day's records
            meta.Data.daily.challengeDate = "2026-09-26";
            meta.Data.daily.challengeBestScore = 999;
            var old = new RunResult { runId = "old", mode = BattleMode.Daily, missionId = "daily", dailyDate = "2026-09-25", score = 5000, totalWaves = 20, stats = new RunStats() };
            meta.ApplyRunResult(old, nextDay, nextDay);
            Assert.That(meta.Data.daily.challengeDate, Is.EqualTo("2026-09-26"));
            Assert.That(meta.Data.daily.challengeBestScore, Is.EqualTo(999));
        }

        [Test]
        public void CosmeticsNeverAffectStatsAndCannotBeBoughtTwice()
        {
            var meta = NewMeta(out _);
            meta.Data.moonGold = 5000;
            Assert.That(meta.BuyCosmetic("arc_light_cat_ember", T0), Is.EqualTo(MetaResult.Ok));
            Assert.That(meta.BuyCosmetic("arc_light_cat_ember", T0), Is.EqualTo(MetaResult.AlreadyClaimed));
            Assert.That(meta.BuyCosmetic("banner_supporter", T0), Is.EqualTo(MetaResult.NotAvailable), "store not configured");
            Assert.That(meta.EquipCosmetic("arc_light_cat_ember", T0), Is.EqualTo(MetaResult.Ok));
            var setup = meta.CreateCampaignSetup("m01", 1, false);
            var b = new Battle(TestContent.Load(), setup);
            Assert.That(b.Stats.hero.damage, Is.EqualTo(12f).Within(1e-3f));
        }

        [Test]
        public void DisplayNameValidation()
        {
            Assert.That(GameMeta.ValidDisplayName("Arc Fan 99"), Is.True);
            Assert.That(GameMeta.ValidDisplayName("ab"), Is.False);
            Assert.That(GameMeta.ValidDisplayName("<script>"), Is.False);
            Assert.That(GameMeta.ValidDisplayName(new string('x', 30)), Is.False);
        }

        [Test]
        public void CheckpointReplayCannotDuplicateRewards()
        {
            // The same run finishing twice (resume after a crash, then a stale callback) pays once.
            var meta = NewMeta(out _);
            var cp = new RunCheckpoint { runId = "run-Z", missionId = "m01", nextWave = 5 };
            meta.CommitCheckpoint(cp, T0);
            Assert.That(meta.Data.activeRun, Is.Not.Null);
            var r = Result("m01", true, 10, "run-Z");
            meta.ApplyRunResult(r, T0, T0);
            Assert.That(meta.Data.activeRun, Is.Null, "finished run clears the checkpoint");
            long gold = meta.Data.moonGold;
            meta.ApplyRunResult(r, T0, T0);
            Assert.That(meta.Data.moonGold, Is.EqualTo(gold));
        }
    }
}
