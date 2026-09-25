using System;
using System.Collections;
using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Meta;
using EvilCats.Sim;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace EvilCats.Game
{
    /// <summary>
    /// Persistent application root (DontDestroyOnLoad). Owns the loaded content, the player's
    /// save/progression, sprites, audio and the (optional) online-service adapters. Scene
    /// controllers (Boot, Hub, Battle) read everything from here.
    /// </summary>
    public sealed class GameApp : MonoBehaviour
    {
        public static GameApp I { get; private set; }

        public GameContent Content { get; private set; }
        public GameMeta Meta { get; private set; }
        public SaveManager Saves { get; private set; }
        public LoadResult SaveLoad { get; private set; }
        public SpriteLibrary Sprites { get; private set; }
        public AudioManager Audio { get; private set; }
        public Haptics Haptics { get; private set; }
        public ServiceHub Services { get; private set; }
        public bool IsBooted { get; private set; }
        public readonly List<string> BootProblems = new List<string>();

        /// <summary>Battle to start when the Battle scene loads.</summary>
        public BattleSetup PendingBattle;
        /// <summary>Filled by the battle for the Hub's results screen (null when none).</summary>
        public BattleOutcome LastOutcome;
        /// <summary>Hub screen to open after returning from a battle (e.g. "upgrades").</summary>
        public string HubStartScreen;

        public const string Version = "0.9.0";

        public static DateTime UtcNow => DateTime.UtcNow;
        public static DateTime LocalNow => DateTime.Now;

        public static GameApp Ensure()
        {
            if (I != null) return I;
            var go = new GameObject("[GameApp]");
            DontDestroyOnLoad(go);
            I = go.AddComponent<GameApp>();
            return I;
        }

        private void Awake()
        {
            if (I != null && I != this)
            {
                Destroy(gameObject);
                return;
            }
            I = this;
            DontDestroyOnLoad(gameObject);
            Application.targetFrameRate = 60;
            QualitySettings.vSyncCount = 0;
            Screen.sleepTimeout = SleepTimeout.NeverSleep;
            Screen.orientation = ScreenOrientation.Portrait;
            if (GetComponent<BackButton>() == null) gameObject.AddComponent<BackButton>();
        }

        // ------------------------------------------------------------------------------
        // Boot: each step reports real progress (no fake percentages).
        // ------------------------------------------------------------------------------
        public sealed class BootStep
        {
            public string key;
            public Action run;
        }

        public List<BootStep> BootSteps()
        {
            return new List<BootStep>
            {
                new BootStep { key = "ui.boot.content", run = LoadContent },
                new BootStep { key = "ui.boot.validate", run = ValidateContent },
                new BootStep { key = "ui.boot.save", run = LoadSave },
                new BootStep { key = "ui.boot.art", run = LoadArt },
                new BootStep { key = "ui.boot.audio", run = LoadAudio },
                new BootStep { key = "ui.boot.settings", run = ApplySettings },
            };
        }

        /// <summary>Runs every boot step over several frames, reporting (stepIndex, stepCount, key).</summary>
        public IEnumerator BootRoutine(Action<int, int, string> progress)
        {
            if (IsBooted) yield break;
            var steps = BootSteps();
            for (int i = 0; i < steps.Count; i++)
            {
                progress?.Invoke(i, steps.Count, steps[i].key);
                yield return null;
                try { steps[i].run(); }
                catch (Exception e)
                {
                    BootProblems.Add(steps[i].key + ": " + e.Message);
                    Debug.LogException(e);
                }
            }
            IsBooted = Content != null && Meta != null;
            progress?.Invoke(steps.Count, steps.Count, IsBooted ? "ui.boot.done" : "ui.boot.error");
        }

        /// <summary>Synchronous boot for when a scene is opened directly in the editor.</summary>
        public void BootImmediate()
        {
            if (IsBooted) return;
            foreach (var s in BootSteps())
            {
                try { s.run(); }
                catch (Exception e) { BootProblems.Add(s.key + ": " + e.Message); Debug.LogException(e); }
            }
            IsBooted = Content != null && Meta != null;
        }

        private void LoadContent()
        {
            Content = GameContent.Load(new ResourcesContentSource(), strict: true);
            foreach (var e in Content.LoadErrors) BootProblems.Add(e);
            L.Use(Content.Strings);
        }

        private void ValidateContent()
        {
            var report = ContentValidator.Validate(Content);
            if (!report.Ok)
            {
                foreach (var e in report.Errors) BootProblems.Add(e);
                Debug.LogError("[EvilCats] Content validation failed:\n" + report);
            }
            else if (report.Warnings.Count > 0) Debug.LogWarning("[EvilCats] Content warnings:\n" + report);
        }

        private void LoadSave()
        {
            Saves = new SaveManager(new FileSaveStore(Application.persistentDataPath));
            SaveLoad = Saves.Load(UtcNow);
            Meta = new GameMeta(Content, SaveLoad.data, Saves);
            Meta.EnsureDaily(LocalNow);
            if (SaveLoad.outcome == LoadOutcome.Migrated || SaveLoad.outcome == LoadOutcome.RecoveredFromBackup || SaveLoad.outcome == LoadOutcome.ResetAfterCorruption)
                Meta.Save(UtcNow);
            Services = ServiceHub.CreateDefault();
            Haptics = new Haptics();
        }

        private void LoadArt()
        {
            Sprites = new SpriteLibrary();
            Sprites.LoadAll();
            foreach (var p in Sprites.Problems) BootProblems.Add(p);
        }

        private void LoadAudio()
        {
            if (Audio == null) Audio = gameObject.AddComponent<AudioManager>();
            Audio.Init();
        }

        public void ApplySettings()
        {
            if (Meta == null) return;
            var s = Meta.Data.settings;
            if (Audio != null) Audio.SetVolumes(s.music, s.sfx);
            if (Haptics != null) Haptics.Enabled = s.vibration;
        }

        // ------------------------------------------------------------------------------
        // Scene flow
        // ------------------------------------------------------------------------------
        public const string BootScene = "Boot", HubScene = "Hub", BattleScene = "Battle";

        public void GoTo(string scene)
        {
            Time.timeScale = 1f;
            if (Application.CanStreamedLevelBeLoaded(scene)) SceneManager.LoadScene(scene);
            else SceneAttach.SwapInPlace(scene);   // scenes not in Build Settings yet: still playable
        }

        public void StartBattle(BattleSetup setup)
        {
            PendingBattle = setup;
            LastOutcome = null;
            GoTo(BattleScene);
        }

        public void SaveNow()
        {
            if (Meta != null) Meta.Save(UtcNow);
        }

        private void OnApplicationPause(bool paused)
        {
            if (paused) SaveNow();
            if (Audio != null) Audio.OnAppPaused(paused);
        }

        private void OnApplicationFocus(bool focus)
        {
            if (!focus) SaveNow();
        }

        private void OnApplicationQuit() => SaveNow();
    }

    /// <summary>What the battle hands back to the Hub's results screen.</summary>
    public sealed class BattleOutcome
    {
        public RunResult result;
        public RewardSummary rewards;
        public BattleSetup setup;
    }
}
