using System;
using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Core;

namespace EvilCats.Sim
{
    public enum BattlePhase { Running, AwaitingPerk, AwaitingModuleChoice, AwaitingRevive, Victory, Defeat }

    public enum MoveState { Route, Approach, Holding, Flying }

    public enum PowderState { Walking, Fuse, Charge, Dazed }

    /// <summary>A live enemy (or boss) in the simulation. Instances are pooled.</summary>
    public sealed class Enemy
    {
        public int uid;
        public bool alive;
        public string typeId;            // enemy id or boss id
        public EnemyDef def;             // null for bosses
        public BossDef bossDef;          // null for ordinary enemies
        public EnemyRole role;
        public bool isBoss, elite, flying, displacementImmune, summoned;
        public int summonerUid;

        public Vec2 pos, prevPos, velocity;
        public float radius, scale = 1f;
        public float hp, maxHp, armor, resist;
        public float speed, damage, attackInterval, attackTimer, attackRange, projectileSpeed;
        public float controlResist;
        public int xp, sparks;

        // movement
        public MoveState state;
        public int route;
        public float routeDist, lateral;
        public int ringSlot = -1, ringLayer;
        public Vec2 goal;
        public float wobble;
        public float stuckTimer, lastGoalDist;
        public bool enraged;

        // status effects
        public float slowFrost, slowFrostTime;     // frost chill slow
        public float slowOther, slowOtherTime;     // event horizon etc.
        public int chillStacks;
        public float frozenTime, freezeImmuneTime, stunTime, fatigue;
        public readonly float[] burnDps = new float[6];
        public readonly float[] burnTime = new float[6];
        public int burnCount;
        public readonly float[] bleedDps = new float[4];
        public readonly float[] bleedTime = new float[4];
        public int bleedCount;
        public float markTime;
        public float armorBreakTime, armorBreakAmount;
        public float pulledTime, recentlyPulledTime;
        public Vec2 pullCenter;
        public int pullZoneUid;
        public float buffTime, buffMult = 1f;       // King Goldenfang's decree
        public float dotNumberAcc, dotNumberTimer;  // aggregate DoT damage numbers

        // specials
        public PowderState powder;
        public float powderTimer;
        public float healTimer;
        public float shieldTime;                    // boss shield stance
        public BossRuntime boss;

        public bool IsControlled => stunTime > 0f || frozenTime > 0f || pulledTime > 0f;
        public bool IsChilled => slowFrostTime > 0f;
        public bool IsSlowed => (slowFrostTime > 0f && slowFrost > 0f) || (slowOtherTime > 0f && slowOther > 0f);
        public bool IsBurning => burnCount > 0;
        public bool IsRangedThreat => role == EnemyRole.Ranged || role == EnemyRole.Support;
        public float HealthFraction => maxHp > 0f ? hp / maxHp : 0f;

        public void Reset()
        {
            alive = false; def = null; bossDef = null; boss = null; typeId = null;
            isBoss = elite = flying = displacementImmune = summoned = enraged = false;
            summonerUid = 0; velocity = Vec2.Zero; scale = 1f;
            ringSlot = -1; ringLayer = 0; stuckTimer = 0f; lastGoalDist = float.MaxValue;
            slowFrost = slowFrostTime = slowOther = slowOtherTime = 0f; chillStacks = 0;
            frozenTime = freezeImmuneTime = stunTime = fatigue = 0f;
            burnCount = 0; bleedCount = 0; markTime = 0f; armorBreakTime = armorBreakAmount = 0f;
            pulledTime = recentlyPulledTime = 0f; pullZoneUid = 0; buffTime = 0f; buffMult = 1f;
            dotNumberAcc = dotNumberTimer = 0f;
            powder = PowderState.Walking; powderTimer = 0f; healTimer = 0f; shieldTime = 0f;
        }
    }

    public sealed class BossRuntime
    {
        public int phase = 1;
        public float[] abilityTimers;
        public int activeAbility = -1;
        public int abilityStage;          // 0 idle, 1 windup, 2 active
        public float stageTimer;
        public float sectorAngle;
        public float staggerDamage;
        public int feathersLeft;
        public float featherTimer;
        public Vec2 chargeFrom, chargeTo;
        public bool introShown;
    }

    public enum ProjectileKind { Shell, Bolt, Arrow, Feather, ScepterBolt }

    public sealed class Projectile
    {
        public int uid;
        public bool alive;
        public ProjectileKind kind;
        public Vec2 pos, prevPos, start, target, dir;
        public float speed, damage, radius, maxDist, traveled, armorPen;
        public int pierceLeft;
        public int ownerEnemyUid;         // enemy shots: who fired (for reflect)
        public string sourceId;           // module id / enemy id / ability id
        public DamageType type;
        public bool fromEnemy;
        public int shotIndex;
        public readonly List<int> hits = new List<int>(8);
    }

    public enum ZoneKind { GravityWell }

    public sealed class Zone
    {
        public int uid;
        public bool alive;
        public ZoneKind kind;
        public Vec2 pos;
        public float radius, time, duration, pullSpeed;
        public string sourceId;
    }

    public sealed class BarrierPool
    {
        public float amount, timeLeft;
        public string source;
    }

    public enum SimEventType
    {
        WaveStarted, WaveCleared, IncomingAnnounce, EnemySpawned, EnemyDied, EnemyHit, EnemyAttack, EnemyFled,
        CitadelDamaged, BarrierGained, BarrierAbsorbed, BarrierExpired, Healed,
        HeroAttack, ChainHop, ThunderclapBurst, ArcStormCast, ArcStormStrike, WardCast,
        StationFired, ProjectileSpawned, ProjectileHit, Explosion, FrostPulse, WinterRing, Freeze, Shatter,
        GravityWell, GravityWellEnd, BurnApplied, CinderSpread, FurnaceHeart, Reflect, LastThread,
        LevelUp, PerkOffered, PerkChosen, UpgradeBought, SparksGained, XpGained,
        PowderFuse, PowderInterrupted, PowderExploded, PriestHeal,
        BossSpawned, BossPhase, BossTelegraph, BossAbility, BossStaggered, BossDefeated,
        SlotUnlocked, ModuleChoiceRequired, ModuleEquipped, Bark, StallRecovered,
        ReviveOffered, Revived, Victory, Defeat, CheckpointReady
    }

    /// <summary>A presentation event emitted by the simulation (the Unity layer turns these into visuals/audio).</summary>
    public struct SimEvent
    {
        public SimEventType type;
        public int uid;
        public int uid2;
        public Vec2 pos;
        public Vec2 pos2;
        public float value;
        public float value2;
        public int flags;         // bit0 = crit, bit1 = elite, bit2 = boss, bit3 = barrier
        public string id;
        public string id2;

        public const int FlagCrit = 1, FlagElite = 2, FlagBoss = 4, FlagBarrier = 8, FlagDot = 16;
    }

    public enum AbilityResult { Cast, OnCooldown, NoTargets, NotRunning }

    public enum PurchaseResult { Bought, NotEnoughSparks, MaxLevel, Unknown, NotRunning }

    /// <summary>What the player chose before the run, plus permanent progression snapshot.</summary>
    public sealed class BattleSetup
    {
        public string runId = Guid.NewGuid().ToString("N");
        public BattleMode mode = BattleMode.Campaign;
        public string missionId;
        public ulong seed = 1;
        public Dictionary<string, string> loadout = new Dictionary<string, string>(); // slotId -> moduleId
        public List<string> unlockedSlots = new List<string>();                       // slots usable at start
        public List<string> availableModules = new List<string>();                    // for slot-unlock choices
        public Dictionary<string, int> nodeLevels = new Dictionary<string, int>();
        public Dictionary<string, int> moduleTiers = new Dictionary<string, int>();
        public TargetPriority priority = TargetPriority.Nearest;
        public bool reviveAllowed;
        public bool ignorePermanent;
        public List<string> extraModifiers = new List<string>();  // daily challenge modifiers
        public string dailyBoss;
        public RunCheckpoint resume;                               // resume from a wave checkpoint
        public string heroSkin = "arc_light_cat";
        /// <summary>Player setting "Battlefield paths" (routes_3 / routes_5). Null = the mission's own layout.
        /// Ignored by the daily challenge so every player gets the same battlefield.</summary>
        public string routeLayout;
        public bool emitEvents = true;                             // headless sims can turn this off
        public int endlessStartWave = 1;
        /// <summary>Tests/tools only: no waves are started and the battle never ends by itself.</summary>
        public bool sandbox;
    }

    /// <summary>Everything needed to restart a run at the beginning of a wave.</summary>
    [Serializable]
    public sealed class RunCheckpoint
    {
        public int version = 1;
        public string runId;
        public BattleMode mode;
        public string missionId;
        public ulong seed;
        public int nextWave;                      // 1-based wave that will start on resume
        public float citadelHp;
        public float sparks;
        public float xp;
        public int level;
        public Dictionary<string, int> perks = new Dictionary<string, int>();
        public Dictionary<string, int> upgrades = new Dictionary<string, int>();
        public Dictionary<string, string> loadout = new Dictionary<string, string>();
        public List<string> unlockedSlots = new List<string>();
        public RngState combatRng;
        public RngState perkRng;
        public bool reviveUsed;
        public bool lastThreadUsed;
        public TargetPriority priority;
        public float stormCooldown;
        public float wardCooldown;
        public float elapsed;
        public RunStats stats = new RunStats();
        public List<string> offeredFallbackHistory = new List<string>();
        public string routeLayout;                 // layout the run started with (kept on resume)
        public string savedAtUtc;
    }

    /// <summary>Counters used for achievements, daily objectives, the defeat explanation and records.</summary>
    [Serializable]
    public sealed class RunStats
    {
        public int kills, eliteKills, bossKills, wavesCleared;
        public Dictionary<string, int> killsByType = new Dictionary<string, int>();
        public Dictionary<string, float> damageTakenBySource = new Dictionary<string, float>();
        public Dictionary<string, float> damageDealtBySource = new Dictionary<string, float>();
        public int burnsApplied, freezes, pulls, powderInterrupts;
        public float barrierAbsorbed, healthDamageTaken, healed;
        public int maxChain, stormUses, wardUses, upgradesBought, perksTaken;
        public float minHealthFraction = 1f;
        public float timeSec;
        public List<string> bossesDefeated = new List<string>();

        public void AddKill(string type, bool elite, bool boss)
        {
            kills++;
            if (elite) eliteKills++;
            if (boss) bossKills++;
            killsByType.TryGetValue(type, out int n);
            killsByType[type] = n + 1;
        }

        public static void Add(Dictionary<string, float> d, string key, float v)
        {
            if (string.IsNullOrEmpty(key) || v <= 0f) return;
            d.TryGetValue(key, out float n);
            d[key] = n + v;
        }
    }

    public sealed class PerkChoice
    {
        public string perkId;       // null when this is a fallback reward
        public string fallbackId;
        public int currentStacks;
        public int maxStacks;
    }

    public sealed class PerkOffer
    {
        public int level;
        public readonly List<PerkChoice> choices = new List<PerkChoice>();
    }

    /// <summary>Final outcome of a run, consumed by the meta layer (rewards, records, achievements).</summary>
    [Serializable]
    public sealed class RunResult
    {
        public string runId;
        public BattleMode mode;
        public string missionId;
        public bool victory;
        public bool abandoned;
        public int wavesCleared;
        public int totalWaves;
        public int levelReached;
        public float healthFraction;
        public RunStats stats = new RunStats();
        public string principalDamageSource;
        public float principalDamageShare;
        public List<string> perks = new List<string>();
        public Dictionary<string, string> loadout = new Dictionary<string, string>();
        public List<string> unlockedSlots = new List<string>();
        public long score;
        public ulong seed;
    }
}
