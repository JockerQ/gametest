using System;
using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Core;

namespace EvilCats.Sim
{
    public sealed partial class Battle
    {
        public int Wave { get; private set; }
        public WavePlan CurrentPlan => _plan;
        public bool WaveActive => _waveActive;
        public float WaveTime => _waveTime;
        public float NextWaveIn => _waveActive ? 0f : Math.Max(0f, _waveStartDelay);
        public int NextWave => _nextWave;
        public int AliveCount { get; private set; }
        public int PendingSpawns => _plan == null ? 0 : _plan.orders.Count - _nextOrder;

        private int _nextWave;
        private float _waveStartDelay;
        private WavePlan _plan;
        private float _waveTime;
        private int _nextOrder;
        private bool _waveActive;
        private bool _checkpointAfterDecision;
        private bool _stallEnraged;

        // ---- ring slots: melee attackers spread evenly around the citadel -------------------
        private int[][] _ring;
        private float[] _ringRadius;

        private void InitRing()
        {
            var a = C.Tuning.arena;
            int layers = 3;
            _ring = new int[layers][];
            _ringRadius = new float[layers];
            for (int l = 0; l < layers; l++)
            {
                _ring[l] = new int[a.ringSlots + l * 6];
                _ringRadius[l] = a.meleeRing + l * a.outerRingStep;
            }
        }

        private Vec2 SlotPosition(int layer, int idx, float extra)
        {
            int n = _ring[layer].Length;
            float ang = idx * MathX.TwoPi / n;
            return Vec2.FromAngle(ang, _ringRadius[layer] + extra);
        }

        private bool AssignSlot(Enemy e)
        {
            FreeSlot(e);
            float angle = e.pos.Angle;
            if (angle < 0f) angle += MathX.TwoPi;
            float extra = Math.Max(0f, e.radius - 0.4f);
            for (int l = 0; l < _ring.Length; l++)
            {
                int n = _ring[l].Length;
                int ideal = MathX.RoundToInt(angle / MathX.TwoPi * n) % n;
                for (int k = 0; k <= n / 2; k++)
                {
                    for (int sign = 0; sign < 2; sign++)
                    {
                        int idx = ((ideal + (sign == 0 ? k : -k)) % n + n) % n;
                        if (_ring[l][idx] != 0) continue;
                        // only accept slots within ~70 degrees of the approach direction on inner layers
                        if (l < _ring.Length - 1 && k > n / 5) break;
                        _ring[l][idx] = e.uid;
                        e.ringLayer = l;
                        e.ringSlot = idx;
                        e.goal = SlotPosition(l, idx, extra);
                        return true;
                    }
                }
            }
            e.goal = e.pos.Normalized * (_ringRadius[_ring.Length - 1] + C.Tuning.arena.outerRingStep + extra);
            return false;
        }

        private void FreeSlot(Enemy e)
        {
            if (e.ringSlot >= 0 && e.ringLayer < _ring.Length && e.ringSlot < _ring[e.ringLayer].Length && _ring[e.ringLayer][e.ringSlot] == e.uid)
                _ring[e.ringLayer][e.ringSlot] = 0;
            e.ringSlot = -1;
        }

        // ---- wave flow --------------------------------------------------------------------------
        private void UpdateWaveFlow()
        {
            if (Setup.sandbox) return;
            if (!_waveActive)
            {
                _waveStartDelay -= Dt;
                if (_waveStartDelay <= 0f) StartWave(_nextWave);
                return;
            }
            _waveTime += Dt;
            var arena = C.Tuning.arena;
            while (_nextOrder < _plan.orders.Count && _plan.orders[_nextOrder].time <= _waveTime)
            {
                if (AliveCount >= arena.maxAlive) break;   // cap: excess spawns wait for space
                SpawnOrderNow(_plan.orders[_nextOrder]);
                _nextOrder++;
            }
            if (_nextOrder >= _plan.orders.Count && AliveCount > 0)
            {
                float t = _waveTime - _plan.release;
                if (!_stallEnraged && t > C.Tuning.waves.stallSeconds)
                {
                    // Stall recovery: stragglers stop hesitating and rush the citadel.
                    _stallEnraged = true;
                    foreach (var e in _enemies)
                        if (e.alive && !e.isBoss) { e.enraged = true; if (e.state == MoveState.Route) EnterApproach(e); }
                    Emit(SimEventType.StallRecovered, value: 1f);
                }
                if (t > C.Tuning.waves.hardStallSeconds)
                {
                    // Hard cap (should never happen in normal play): remove unreachable stragglers without rewards.
                    foreach (var e in _enemies)
                        if (e.alive && !e.isBoss) { KillSilently(e); Emit(SimEventType.EnemyFled, e.pos, id: e.typeId, uid: e.uid); }
                    Emit(SimEventType.StallRecovered, value: 2f);
                }
            }
        }

        private void StartWave(int w)
        {
            Wave = w;
            _plan = WavePlanner.Plan(C, Spec, Routes, w, Setup.seed);
            _waveTime = 0f;
            _nextOrder = 0;
            _waveActive = true;
            _stallEnraged = false;
            Emit(SimEventType.WaveStarted, value: w, value2: Spec.totalWaves, id: _plan.bossId);
            foreach (var a in _plan.announce) Emit(SimEventType.IncomingAnnounce, id: a, value: w);
            if (Spec.slotUnlocks != null)
                foreach (var su in Spec.slotUnlocks)
                    if (su.wave == w) UnlockSlotEvent(su);
        }

        private void UnlockSlotEvent(SlotUnlockDef su)
        {
            // Replays: a slot that is already unlocked does not trigger the event again.
            if (UnlockedSlots.Contains(su.slot)) return;
            UnlockedSlots.Add(su.slot);
            bool filled = Loadout.TryGetValue(su.slot, out var existing) && !string.IsNullOrEmpty(existing);
            // A granted module that is already equipped in another slot is never duplicated: the
            // player chooses a module for the new slot instead.
            string grant = !filled && !string.IsNullOrEmpty(su.grantModule) && !Loadout.ContainsValue(su.grantModule) ? su.grantModule : null;
            Emit(SimEventType.SlotUnlocked, id: su.slot, id2: grant);
            if (filled) return;
            if (grant != null)
            {
                EquipModule(su.slot, grant);
                return;
            }
            ModuleChoices.Clear();
            foreach (var m in Setup.availableModules)
                if (!Loadout.ContainsValue(m) && C.Module(m) != null) ModuleChoices.Add(m);
            if (ModuleChoices.Count == 0) return;
            PendingSlot = su.slot;
            Phase = BattlePhase.AwaitingModuleChoice;
            Emit(SimEventType.ModuleChoiceRequired, id: su.slot);
        }

        private void CheckWaveCleared()
        {
            if (Setup.sandbox || !_waveActive || IsOver) return;
            if (_nextOrder < _plan.orders.Count || AliveCount > 0) return;
            _waveActive = false;
            RunStats.wavesCleared = Wave;
            var econ = C.Tuning.economy;
            float bonus = (econ.waveClearSparksBase + econ.waveClearSparksPerWave * Wave) * Stats.econ.sparkGain;
            _sparks += bonus;
            Emit(SimEventType.WaveCleared, value: Wave, value2: bonus);
            if (Spec.totalWaves > 0 && Wave >= Spec.totalWaves)
            {
                CurrentOffer = null;
                _pendingLevels = 0;
                SetVictory();
                return;
            }
            _nextWave = Wave + 1;
            _waveStartDelay = C.Tuning.waves.intermission;
            if (Phase == BattlePhase.Running && CurrentOffer == null && _pendingLevels == 0)
            {
                CheckpointPending = true;
                Emit(SimEventType.CheckpointReady, value: _nextWave);
            }
            else _checkpointAfterDecision = true;
        }

        // ---- spawning --------------------------------------------------------------------------
        private void SpawnOrderNow(SpawnOrder o)
        {
            if (o.boss)
            {
                SpawnBoss(o);
                return;
            }
            var def = C.Enemy(o.enemyId);
            if (def == null) return;
            int count = Math.Max(1, def.swarmCount);
            var unit = string.IsNullOrEmpty(def.unitId) ? def : (C.Enemy(def.unitId) ?? def);
            for (int i = 0; i < count; i++)
            {
                float lat = o.lateral;
                if (count > 1) lat += (i - (count - 1) * 0.5f) * 0.32f;
                SpawnEnemy(unit, o.route, lat, o.elite, null, false, 0, i * 0.18f);
            }
        }

        private Enemy NewEnemy()
        {
            var e = _enemyPool.Count > 0 ? _enemyPool.Pop() : new Enemy();
            e.Reset();
            e.uid = NewUid();
            e.alive = true;
            return e;
        }

        /// <summary>Spawns an ordinary enemy on a route edge, or at a validated summon point.</summary>
        private Enemy SpawnEnemy(EnemyDef def, int routeIdx, float lateral, bool elite, Vec2? at, bool summoned, int summonerUid, float routeLead = 0f)
        {
            var el = C.Tuning.elite;
            var e = NewEnemy();
            e.typeId = def.id;
            e.def = def;
            e.role = def.role;
            e.elite = elite;
            e.flying = def.flying;
            e.displacementImmune = def.displacementImmune;
            e.radius = def.radius * (elite ? el.scale : 1f);
            e.scale = elite ? el.scale : 1f;
            float hpMult = _plan != null ? _plan.healthMult : 1f;
            float dmgMult = _plan != null ? _plan.damageMult : 1f;
            float spdMult = _plan != null ? _plan.speedMult : 1f;
            float armorAdd = _plan != null ? _plan.armorAdd : 0f;
            e.maxHp = e.hp = Math.Max(1f, def.health * hpMult * (elite ? el.healthMult : 1f));
            e.armor = MathX.Clamp(def.armor + armorAdd, 0f, 90f);
            e.resist = MathX.Clamp(def.resist, 0f, 90f);
            e.speed = def.speed * spdMult;
            e.damage = def.damage * dmgMult * (elite ? el.damageMult : 1f);
            e.attackInterval = Math.Max(0.2f, def.attackInterval);
            e.attackRange = def.attackRange;
            e.projectileSpeed = def.projectileSpeed;
            e.controlResist = MathX.Clamp(def.controlResist + (elite ? el.controlResistAdd : 0f), 0f, 0.95f);
            e.xp = MathX.RoundToInt(def.xp * (elite ? el.rewardMult : 1f));
            e.sparks = MathX.RoundToInt(def.sparks * (elite ? el.rewardMult : 1f));
            e.summoned = summoned;
            e.summonerUid = summonerUid;
            e.route = MathX.Clamp(routeIdx, 0, Routes.routes.Count - 1);
            e.lateral = lateral;
            e.wobble = _combatRng.Range(0f, MathX.TwoPi);
            e.attackTimer = e.attackInterval * _combatRng.Range(0.3f, 1f);
            e.healTimer = P(def, "healInterval", 3.5f) * _combatRng.Range(0.4f, 0.9f);
            var route = Routes.routes[e.route];
            if (at.HasValue)
            {
                e.pos = ClampToArena(at.Value);
                if (e.flying) { e.state = MoveState.Flying; e.goal = FlyGoal(e); }
                else EnterApproach(e);
            }
            else
            {
                e.routeDist = routeLead;
                e.pos = ClampToArena(route.SampleOffset(e.routeDist, e.lateral));
                if (e.flying)
                {
                    e.state = MoveState.Flying;
                    e.goal = FlyGoal(e);
                }
                else e.state = MoveState.Route;
            }
            e.prevPos = e.pos;
            e.lastGoalDist = float.MaxValue;
            _enemies.Add(e);
            AliveCount++;
            Emit(SimEventType.EnemySpawned, e.pos, id: e.typeId, uid: e.uid, flags: elite ? SimEvent.FlagElite : 0, value: e.scale);
            return e;
        }

        private Vec2 FlyGoal(Enemy e)
        {
            float hover = e.isBoss ? e.bossDef.stopDistance : (e.def != null ? P(e.def, "hoverRadius", C.Tuning.arena.meleeRing - 0.15f) : 2.5f);
            Vec2 dir = e.pos.SqrLength > 1e-4f ? e.pos.Normalized : Vec2.Up;
            return dir * hover;
        }

        private Vec2 ClampToArena(Vec2 p)
        {
            var a = C.Tuning.arena;
            float hw = a.width * 0.5f - a.spawnInset, hh = a.height * 0.5f - a.spawnInset;
            return new Vec2(MathX.Clamp(p.x, -hw, hw), MathX.Clamp(p.y, -hh, hh));
        }

        /// <summary>A safe place near `near` for summons: outside the citadel, inside the arena.</summary>
        private Vec2 SafeSummonPoint(Vec2 near, float spread)
        {
            var a = C.Tuning.arena;
            Vec2 p = near + Vec2.FromAngle(_combatRng.Range(0f, MathX.TwoPi), _combatRng.Range(0.3f, spread));
            float d = p.Length;
            if (d < a.minSummonDistance) p = (d > 1e-3f ? p / d : Vec2.Up) * a.minSummonDistance;
            return ClampToArena(p);
        }

        private static float P(EnemyDef d, string key, float fallback) =>
            d != null && d.p != null && d.p.TryGetValue(key, out var v) ? v : fallback;

        private void KillSilently(Enemy e)
        {
            if (!e.alive) return;
            MarkDead(e);
        }

        private void MarkDead(Enemy e)
        {
            e.alive = false;
            e.hp = 0f;
            FreeSlot(e);
            AliveCount = Math.Max(0, AliveCount - 1);
        }

        private void RemoveDead()
        {
            int alive = 0;
            for (int i = _enemies.Count - 1; i >= 0; i--)
            {
                var e = _enemies[i];
                if (e.alive) { alive++; continue; }
                FreeSlot(e);
                _enemies.RemoveAt(i);
                _enemyPool.Push(e);
            }
            AliveCount = alive;
            for (int i = _projectiles.Count - 1; i >= 0; i--)
            {
                if (_projectiles[i].alive) continue;
                _projectilePool.Push(_projectiles[i]);
                _projectiles.RemoveAt(i);
            }
            for (int i = _zones.Count - 1; i >= 0; i--)
                if (!_zones[i].alive) _zones.RemoveAt(i);
        }
    
        // ---- sandbox helpers (tests, tools and the editor's debug scene; not used by gameplay) ----
        /// <summary>Spawns an enemy at an exact position (sandbox/tests). Uses wave-1 scaling.</summary>
        public Enemy DebugSpawn(string enemyId, Vec2 pos, bool elite = false)
        {
            if (_plan == null) _plan = new WavePlan { wave = 1 };
            var def = C.Enemy(enemyId);
            if (def != null) return SpawnEnemy(def, 0, 0f, elite, pos, false, 0);
            var bdef = C.Boss(enemyId);
            if (bdef == null) return null;
            SpawnBoss(new SpawnOrder { enemyId = enemyId, boss = true, route = 0 });
            var b = _enemies[_enemies.Count - 1];
            b.pos = b.prevPos = pos;
            b.state = MoveState.Holding;
            return b;
        }

        public void DebugSetHp(float hp) => Hp = Math.Max(0f, Math.Min(MaxHp, hp));

        public void DebugAddSparks(float amount) => _sparks += amount;

        public void DebugAddPerk(string id)
        {
            float oldMax = MaxHp;
            _perkStacks[id] = PerkStack(id) + 1;
            RebuildStats();
            ApplyMaxHealthChange(oldMax);
        }
    }
}
