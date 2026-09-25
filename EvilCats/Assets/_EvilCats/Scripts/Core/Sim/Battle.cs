using System;
using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Core;

namespace EvilCats.Sim
{
    /// <summary>
    /// The complete, deterministic combat simulation for one run.
    ///
    /// * Fixed time step (Dt = 1 / tickRate). The Unity layer calls Tick() once per step;
    ///   at 2× speed it simply calls Tick() twice as often, so outcomes, spawns, rewards and
    ///   cooldown ratios are identical at 1× and 2×.
    /// * No UnityEngine types. All randomness comes from seeded PCG32 streams, so a run can be
    ///   replayed, tested headlessly and checkpointed/resumed at wave boundaries.
    /// * The simulation never waits on the UI: when a decision is needed (perk choice, slot
    ///   module choice, revive) it switches Phase and stops advancing until the call arrives.
    /// </summary>
    public sealed partial class Battle
    {
        public readonly GameContent C;
        public readonly BattleSetup Setup;
        public readonly EncounterSpec Spec;
        public readonly RouteSet Routes;
        public readonly float Dt;
        public readonly string RunId;

        public BattlePhase Phase { get; private set; } = BattlePhase.Running;
        public bool IsOver => Phase == BattlePhase.Victory || Phase == BattlePhase.Defeat;
        public float Time { get; private set; }
        public long TickCount { get; private set; }

        // ---- citadel ------------------------------------------------------------------
        public float Hp { get; private set; }
        public float MaxHp => Stats.citadel.maxHealth;
        public readonly List<BarrierPool> Barriers = new List<BarrierPool>();
        public float BarrierTotal { get; private set; }
        public Vec2 Center => Vec2.Zero;

        // ---- economy / progression ------------------------------------------------------
        private float _sparks;
        public int Sparks => (int)Math.Floor(_sparks + 1e-4f);
        private float _xp;
        public int Level { get; private set; }
        public float Xp => _xp;
        public float XpNeeded => XpForLevel(Level);
        private readonly Dictionary<string, int> _upgradeLevels = new Dictionary<string, int>();
        private readonly Dictionary<string, int> _perkStacks = new Dictionary<string, int>();
        public IReadOnlyDictionary<string, int> UpgradeLevels => _upgradeLevels;
        public IReadOnlyDictionary<string, int> PerkStacks => _perkStacks;
        public DerivedStats Stats { get; private set; }
        public PerkOffer CurrentOffer { get; private set; }
        private int _pendingLevels;

        // ---- loadout ------------------------------------------------------------------------
        public readonly Dictionary<string, string> Loadout = new Dictionary<string, string>();
        public readonly List<string> UnlockedSlots = new List<string>();
        public TargetPriority Priority { get; private set; }
        public string PendingSlot { get; private set; }
        public readonly List<string> ModuleChoices = new List<string>();

        // ---- entities -----------------------------------------------------------------------
        private readonly List<Enemy> _enemies = new List<Enemy>(256);
        private readonly Stack<Enemy> _enemyPool = new Stack<Enemy>(256);
        private readonly List<Projectile> _projectiles = new List<Projectile>(256);
        private readonly Stack<Projectile> _projectilePool = new Stack<Projectile>(256);
        private readonly List<Zone> _zones = new List<Zone>(16);
        public IReadOnlyList<Enemy> Enemies => _enemies;
        public IReadOnlyList<Projectile> Projectiles => _projectiles;
        public IReadOnlyList<Zone> Zones => _zones;
        private int _nextUid = 1;

        // ---- rng streams ----------------------------------------------------------------------
        private readonly Rng _combatRng;
        private readonly Rng _perkRng;

        // ---- abilities --------------------------------------------------------------------------
        public float StormCooldown { get; private set; }
        public float WardCooldown { get; private set; }
        public float StormCooldownTotal => Stats.abilities.stormCooldown;
        public float WardCooldownTotal => Stats.abilities.wardCooldown;

        // ---- flags / bookkeeping ----------------------------------------------------------------
        public readonly RunStats RunStats = new RunStats();
        public readonly List<SimEvent> Events = new List<SimEvent>(512);
        private readonly bool _emit;
        private bool _reviveUsed;
        private bool _lastThreadUsed;
        public bool ReviveUsed => _reviveUsed;
        public bool LastThreadUsed => _lastThreadUsed;
        /// <summary>Set when a wave was cleared and a checkpoint should be saved (reset by TakeCheckpoint()).</summary>
        public bool CheckpointPending { get; private set; }

        public Battle(GameContent content, BattleSetup setup)
        {
            C = content ?? throw new ArgumentNullException(nameof(content));
            Setup = setup ?? throw new ArgumentNullException(nameof(setup));
            Dt = 1f / Math.Max(10f, C.Tuning.tickRate);
            _emit = setup.emitEvents;
            Spec = BuildSpec(content, setup);
            if (!C.LayoutById.TryGetValue(Spec.routeLayout ?? "", out var layout))
                throw new ArgumentException("Unknown route layout " + Spec.routeLayout);
            Routes = new RouteSet(layout);
            RunId = setup.resume != null ? setup.resume.runId : setup.runId;
            _combatRng = new Rng(Rng.Mix(setup.seed, 0xC0FFEEUL), 3u);
            _perkRng = new Rng(Rng.Mix(setup.seed, 0x9E7C5UL), 5u);
            Priority = setup.priority;
            InitRing();

            foreach (var kv in setup.loadout)
                if (!string.IsNullOrEmpty(kv.Value)) Loadout[kv.Key] = kv.Value;
            UnlockedSlots.AddRange(setup.unlockedSlots);
            foreach (var slot in C.Tuning.slots)
                if (Loadout.ContainsKey(slot.id) && !UnlockedSlots.Contains(slot.id)) UnlockedSlots.Add(slot.id);

            RebuildStats();
            Hp = MaxHp;
            _sparks = Stats.econ.startSparks;
            _waveStartDelay = C.Tuning.waves.firstWaveDelay;
            _nextWave = 1;

            if (setup.resume != null) RestoreCheckpoint(setup.resume);
            else if (Spec.mode == BattleMode.Endless && setup.endlessStartWave > 1) _nextWave = setup.endlessStartWave;
        }

        private static EncounterSpec BuildSpec(GameContent c, BattleSetup s)
        {
            switch (s.mode)
            {
                case BattleMode.Endless:
                    return EncounterSpec.ForEndless(c.Endless);
                case BattleMode.Daily:
                {
                    string biome = (s.seed % 2UL == 0UL) ? "gravewood" : "moonfall";
                    return EncounterSpec.ForDaily(c.Daily, s.extraModifiers, s.dailyBoss, biome);
                }
                default:
                {
                    var m = c.Mission(s.missionId) ?? throw new ArgumentException("Unknown mission " + s.missionId);
                    var spec = EncounterSpec.ForMission(m);
                    foreach (var extra in s.extraModifiers) if (!spec.modifiers.Contains(extra)) spec.modifiers.Add(extra);
                    return spec;
                }
            }
        }

        // ==================================================================================
        // Main loop
        // ==================================================================================

        /// <summary>Advance the simulation by exactly one fixed step (no-op while a decision is pending).</summary>
        public void Tick()
        {
            if (Phase != BattlePhase.Running) return;
            TickCount++;
            Time += Dt;
            RunStats.timeSec += Dt;

            UpdateWaveFlow();
            if (Phase != BattlePhase.Running) return;
            UpdateCitadel();
            UpdateEnemies();
            UpdateZones();
            UpdateHero();
            UpdateModules();
            UpdatePerkEffects();
            UpdateProjectiles();
            RemoveDead();
            CheckWaveCleared();
        }

        /// <summary>Run up to maxTicks steps (convenience for headless simulation and tests).</summary>
        public int RunTicks(int maxTicks)
        {
            int n = 0;
            while (n < maxTicks && Phase == BattlePhase.Running)
            {
                Tick();
                n++;
            }
            return n;
        }

        public void DrainEvents(List<SimEvent> into)
        {
            if (into != null) into.AddRange(Events);
            Events.Clear();
        }

        private void Emit(SimEventType type, Vec2 pos = default, float value = 0f, string id = null, int uid = 0,
            int flags = 0, Vec2 pos2 = default, int uid2 = 0, string id2 = null, float value2 = 0f)
        {
            if (!_emit) return;
            Events.Add(new SimEvent
            {
                type = type, pos = pos, value = value, id = id, uid = uid, flags = flags,
                pos2 = pos2, uid2 = uid2, id2 = id2, value2 = value2,
            });
        }

        private int NewUid() => _nextUid++;

        // ==================================================================================
        // Player commands
        // ==================================================================================

        public void SetPriority(TargetPriority p) => Priority = p;

        public int UpgradeLevel(string id) => _upgradeLevels.TryGetValue(id, out var l) ? l : 0;

        public int UpgradeCost(string id)
        {
            if (!C.UpgradeById.TryGetValue(id, out var def)) return int.MaxValue;
            return UpgradeCostAt(def, UpgradeLevel(id), C.Tuning.economy.upgradeCostGrowth);
        }

        /// <summary>ceil(baseCost × growth^level)</summary>
        public static int UpgradeCostAt(RunUpgradeDef def, int level, float growth)
        {
            return MathX.CeilToInt(def.baseCost * Math.Pow(growth, level));
        }

        public bool UpgradeMaxed(string id) =>
            C.UpgradeById.TryGetValue(id, out var def) && UpgradeLevel(id) >= def.maxLevel;

        public PurchaseResult BuyUpgrade(string id)
        {
            if (!C.UpgradeById.TryGetValue(id, out var def)) return PurchaseResult.Unknown;
            if (Phase != BattlePhase.Running) return PurchaseResult.NotRunning;
            int level = UpgradeLevel(id);
            if (level >= def.maxLevel) return PurchaseResult.MaxLevel;
            int cost = UpgradeCostAt(def, level, C.Tuning.economy.upgradeCostGrowth);
            if (Sparks < cost) return PurchaseResult.NotEnoughSparks;
            _sparks -= cost;
            float oldMax = MaxHp;
            _upgradeLevels[id] = level + 1;
            RebuildStats();
            ApplyMaxHealthChange(oldMax);
            RunStats.upgradesBought++;
            Emit(SimEventType.UpgradeBought, value: level + 1, id: id, value2: cost);
            return PurchaseResult.Bought;
        }

        /// <summary>
        /// HEALING RULE for max-health changes: when maximum health rises, current health
        /// rises by the same amount; when it falls, current health is clamped to the new
        /// maximum. Documented in BALANCE.md.
        /// </summary>
        private void ApplyMaxHealthChange(float oldMax)
        {
            float newMax = MaxHp;
            if (newMax > oldMax) Hp += newMax - oldMax;
            Hp = Math.Min(Hp, newMax);
        }

        public void RebuildStats()
        {
            var src = new StatSources
            {
                loadout = Loadout,
                upgradeLevels = _upgradeLevels,
                perkStacks = _perkStacks,
                nodeLevels = Setup.nodeLevels,
                moduleTiers = Setup.moduleTiers,
                ignorePermanent = Setup.ignorePermanent,
            };
            Stats = StatsBuilder.Build(C, src);
            SyncModuleRuntimes();
        }

        public int PerkStack(string id) => _perkStacks.TryGetValue(id, out var n) ? n : 0;

        private float PerkP(string perkId, string key, float fallback = 0f)
        {
            var def = C.Perk(perkId);
            return def != null && def.p.TryGetValue(key, out var v) ? v : fallback;
        }

        public bool HasPerk(string id) => PerkStack(id) > 0;

        /// <summary>Called by the UI after the player chooses the module for a newly unlocked slot.</summary>
        public bool ChooseModuleForSlot(string moduleId)
        {
            if (Phase != BattlePhase.AwaitingModuleChoice || PendingSlot == null) return false;
            if (!string.IsNullOrEmpty(moduleId))
            {
                if (!ModuleChoices.Contains(moduleId)) return false;
                EquipModule(PendingSlot, moduleId);
            }
            PendingSlot = null;
            ModuleChoices.Clear();
            Phase = BattlePhase.Running;
            ContinueAfterDecision();
            return true;
        }

        private void EquipModule(string slot, string moduleId)
        {
            Loadout[slot] = moduleId;
            RebuildStats();
            Emit(SimEventType.ModuleEquipped, id: moduleId, id2: slot);
        }

        /// <summary>Revive after a verified rewarded ad (the meta layer checks ad completion first).</summary>
        public bool Revive()
        {
            if (Phase != BattlePhase.AwaitingRevive || _reviveUsed) return false;
            _reviveUsed = true;
            Hp = MaxHp * C.Tuning.economy.reviveHealthPercent / 100f;
            AddBarrier(MaxHp * 0.2f, 4f, "revive");
            foreach (var e in _enemies)
            {
                if (!e.alive) continue;
                float d = e.pos.Length;
                if (d < 4.5f && !e.isBoss) ApplyStun(e, 1.5f);
            }
            Phase = BattlePhase.Running;
            Emit(SimEventType.Revived, value: Hp);
            return true;
        }

        public void DeclineRevive()
        {
            if (Phase != BattlePhase.AwaitingRevive) return;
            SetDefeat();
        }

        /// <summary>Player quits the run from the pause menu.</summary>
        public void Abandon()
        {
            if (IsOver) return;
            _abandoned = true;
            SetDefeat();
        }

        private bool _abandoned;

        private void SetDefeat()
        {
            Phase = BattlePhase.Defeat;
            Emit(SimEventType.Defeat, value: Wave, id: PrincipalDamageSource(out _));
        }

        private void SetVictory()
        {
            Phase = BattlePhase.Victory;
            Emit(SimEventType.Victory, value: Wave);
        }

        private void ContinueAfterDecision()
        {
            if (_pendingLevels > 0 && CurrentOffer == null) OfferNextPerk();
            if (Phase == BattlePhase.Running && _checkpointAfterDecision)
            {
                _checkpointAfterDecision = false;
                CheckpointPending = true;
                Emit(SimEventType.CheckpointReady, value: _nextWave);
            }
        }
    }
}
