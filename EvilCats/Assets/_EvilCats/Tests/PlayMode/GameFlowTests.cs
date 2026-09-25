using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using EvilCats.Game;
using EvilCats.Meta;
using EvilCats.Sim;
using NUnit.Framework;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.TestTools;

namespace EvilCats.Tests
{
    /// <summary>
    /// Play Mode tests of the real Unity layer: boot, a battle running through the controller with
    /// pause and 2x speed, the exactly-once result, every hub screen, and saving to disk. Saves go to
    /// a temporary folder, never to the developer's own save. (Unity logs any exception as an error,
    /// which fails the test.)
    /// </summary>
    public class GameFlowTests
    {
        private string _dir;
        private readonly HashSet<GameObject> _roots = new HashSet<GameObject>();

        [OneTimeSetUp]
        public void BootOnce()
        {
            _dir = Path.Combine(Application.temporaryCachePath, "evilcats-tests-" + Guid.NewGuid().ToString("N"));
            Directory.CreateDirectory(_dir);
            GameApp.SaveDirectoryOverride = _dir;
            GameApp.Ensure().BootImmediate();
        }

        [OneTimeTearDown]
        public void Shutdown()
        {
            if (GameApp.I != null) UnityEngine.Object.Destroy(GameApp.I.gameObject);
            GameApp.SaveDirectoryOverride = null;
            Time.timeScale = 1f;
            try { Directory.Delete(_dir, true); } catch (Exception) { /* best effort */ }
        }

        [SetUp]
        public void RememberScene()
        {
            _roots.Clear();
            foreach (var go in SceneManager.GetActiveScene().GetRootGameObjects()) _roots.Add(go);
        }

        [TearDown]
        public void CleanScene()
        {
            foreach (var go in SceneManager.GetActiveScene().GetRootGameObjects())
                if (!_roots.Contains(go)) UnityEngine.Object.Destroy(go);
            Time.timeScale = 1f;
        }

        [Test]
        public void BootLoadsContentArtAudioAndSave()
        {
            var app = GameApp.I;
            Assert.That(app.IsBooted, Is.True, string.Join("\n", app.BootProblems));
            Assert.That(app.BootProblems, Is.Empty, string.Join("\n", app.BootProblems));
            Assert.That(app.Sprites.Count, Is.GreaterThan(900));
            Assert.That(app.Audio.Ready, Is.True);
            Assert.That(app.Meta.Data, Is.Not.Null);
        }

        [UnityTest]
        public IEnumerator BattleRunsPausesAndAppliesTheResultOnce()
        {
            var app = GameApp.I;
            app.PendingBattle = app.Meta.CreateCampaignSetup("m01", 7, false);
            var ctl = new GameObject("BattleController").AddComponent<BattleController>();
            ctl.AutoPauseOnFocusLoss = false;   // clicking another window must not pause the test battle
            yield return null;
            yield return null;
            Assert.That(ctl.Battle, Is.Not.Null);
            ctl.ToggleSpeed();
            Assert.That(ctl.Speed, Is.EqualTo(2));

            // let the battle run for a few real seconds; answer any perk offer directly
            float until = Time.realtimeSinceStartup + 5f;
            while (Time.realtimeSinceStartup < until)
            {
                if (ctl.Battle.Phase == BattlePhase.AwaitingPerk)
                {
                    ctl.Battle.ChoosePerk(0);
                    ctl.Modals.CloseAll();
                }
                yield return null;
            }
            Assert.That(ctl.Battle.TickCount, Is.GreaterThan(60));
            Assert.That(ctl.Battle.Wave, Is.GreaterThanOrEqualTo(1));

            // pausing stops the simulation completely
            if (ctl.Battle.Phase == BattlePhase.AwaitingPerk) { ctl.Battle.ChoosePerk(0); ctl.Modals.CloseAll(); yield return null; }
            ctl.Pause();
            yield return null;
            Assert.That(ctl.Modals.IsShowing("pause"), Is.True);
            Assert.That(ctl.IsPaused, Is.True);
            long ticks = ctl.Battle.TickCount;
            yield return new WaitForSecondsRealtime(0.3f);
            Assert.That(ctl.Battle.TickCount, Is.EqualTo(ticks));
            Assert.That(Time.timeScale, Is.EqualTo(0f));
            ctl.Resume();
            yield return null;
            Assert.That(ctl.Modals.IsShowing("pause"), Is.False);
            Assert.That(ctl.IsPaused, Is.False);

            // quitting ends the run; the result is applied exactly once
            ctl.Battle.Abandon();
            yield return new WaitForSecondsRealtime(2.2f);
            Assert.That(ctl.Modals.IsShowing("end"), Is.True);
            Assert.That(app.LastOutcome, Is.Not.Null);
            Assert.That(app.Meta.IsClaimed("run:" + ctl.Battle.RunId + ":result"), Is.True);
            var again = app.Meta.ApplyRunResult(app.LastOutcome.result, DateTime.UtcNow, DateTime.Now);
            Assert.That(again.alreadyApplied, Is.True);
        }

        [UnityTest]
        public IEnumerator EveryHubScreenBuilds()
        {
            var hub = new GameObject("HubController").AddComponent<HubController>();
            yield return null;
            yield return null;
            var screens = new HubScreen[]
            {
                new HomeScreen(), new MissionsScreen(), new LoadoutScreen("m01"), new StationsScreen(), new UpgradesScreen(),
                new DailyScreen(), new AchievementsScreen(), new RecordsScreen(), new ShopScreen(), new ProfileScreen(),
                new SettingsScreen(), new CreditsScreen(), new MoreScreen(),
            };
            foreach (var s in screens)
            {
                hub.Open(s, true);
                yield return null;
                Assert.That(hub.Current, Is.SameAs(s));
            }
        }

        [Test]
        public void SavingWritesAFileThatLoadsBack()
        {
            var app = GameApp.I;
            long before = app.Meta.Data.moonGold;
            app.Meta.Data.moonGold = before + 123;
            app.SaveNow();
            var loaded = new SaveManager(new FileSaveStore(_dir)).Load(DateTime.UtcNow);
            Assert.That(loaded.outcome, Is.EqualTo(LoadOutcome.Loaded));
            Assert.That(loaded.data.moonGold, Is.EqualTo(before + 123));
            app.Meta.Data.moonGold = before;
            app.SaveNow();
        }
    }
}
