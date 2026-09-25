using System;
using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Core;

namespace EvilCats.Sim
{
    /// <summary>Per-station runtime state (timers). Stats live in ModuleStats and are rebuilt on change.</summary>
    public sealed class ModuleRuntime
    {
        public string moduleId;
        public string slotId;
        public ModuleStats stats;
        public float timer;
        public int shots;
        public float heat;
        public float hasteTime;
        public Vec2 origin;
    }

    public sealed partial class Battle
    {
        private readonly List<ModuleRuntime> _modules = new List<ModuleRuntime>(3);
        public IReadOnlyList<ModuleRuntime> ModuleRuntimes => _modules;
        private float _winterTimer = 2f;

        private void SyncModuleRuntimes()
        {
            var old = new Dictionary<string, ModuleRuntime>();
            foreach (var m in _modules) old[m.moduleId] = m;
            _modules.Clear();
            foreach (var ms in Stats.modules)
            {
                if (!old.TryGetValue(ms.moduleId, out var rt))
                    rt = new ModuleRuntime { moduleId = ms.moduleId, timer = Math.Min(1f, ms.interval * 0.5f) };
                rt.stats = ms;
                rt.slotId = ms.slotId;
                rt.origin = SlotOrigin(ms.slotId);
                _modules.Add(rt);
            }
        }

        public Vec2 SlotOrigin(string slotId)
        {
            if (slotId != null && C.SlotById.TryGetValue(slotId, out var s)) return new Vec2(s.x, s.y);
            return Vec2.Zero;
        }

        private void UpdateModules()
        {
            for (int i = 0; i < _modules.Count; i++)
            {
                var rt = _modules[i];
                var m = rt.stats;
                float rate = 1f;
                if (rt.hasteTime > 0f)
                {
                    rt.hasteTime -= Dt;
                    rate += PerkP("ember_furnace_heart", "haste", 0.4f);
                }
                if (m.synergyValues.TryGetValue("barrierHaste", out var bh) && BarrierTotal > 0f) rate += bh;
                rt.timer -= Dt * rate;
                switch (m.def.behavior)
                {
                    case "chain": TickArcCoil(rt); break;
                    case "shell": TickEmberMaw(rt); break;
                    case "frost_pulse": TickFrostWhisker(rt); break;
                    case "piercing": TickBallista(rt); break;
                    case "ward": TickWardLantern(rt); break;
                    case "gravity": TickGravityPaw(rt); break;
                }
                if (Phase != BattlePhase.Running) return;
            }
        }

        private bool Ready(ModuleRuntime rt) => rt.timer <= 0f;

        private void Rearm(ModuleRuntime rt) => rt.timer = Math.Max(0f, rt.timer) + rt.stats.interval;

        private void Idle(ModuleRuntime rt) => rt.timer = 0f;

        // ---- Arc Coil: chains between clustered enemies ---------------------------------------
        private void TickArcCoil(ModuleRuntime rt)
        {
            if (!Ready(rt)) return;
            var m = rt.stats;
            float chainRange = m.P("chainRange", 2.6f);
            var primary = Targeting.ClusterTarget(_enemies, Center, m.range, chainRange, Priority);
            if (primary == null) { Idle(rt); return; }
            Rearm(rt);
            rt.shots++;
            Emit(SimEventType.StationFired, rt.origin, id: m.moduleId, id2: m.slotId, pos2: primary.pos, uid: primary.uid);
            Emit(SimEventType.ChainHop, rt.origin, m.damage, id: m.moduleId, uid: primary.uid, pos2: primary.pos);
            DealDamage(primary, m.damage, DamageType.Arc, m.moduleId, HitKind.Direct);
            ArcChain(primary, m.damage, m.targets - 1, chainRange, m.P("falloff", 0.9f), m.moduleId);
        }

        // ---- Ember Maw: slow lobbed shells, splash + capped burning -----------------------------
        private void TickEmberMaw(ModuleRuntime rt)
        {
            if (!Ready(rt)) return;
            var m = rt.stats;
            var target = Targeting.Select(_enemies, Center, m.range, Priority);
            if (target == null) { Idle(rt); return; }
            Rearm(rt);
            rt.shots++;
            float speed = Math.Max(1f, m.projectileSpeed);
            float t = Vec2.Distance(rt.origin, target.pos) / speed;
            Vec2 lead = target.IsControlled ? target.pos : target.pos + target.velocity * t;
            var p = NewProjectile();
            p.kind = ProjectileKind.Shell;
            p.pos = p.prevPos = p.start = rt.origin;
            p.target = ClampToArena(lead);
            p.speed = speed;
            p.damage = m.damage;
            p.radius = m.radius;
            p.sourceId = m.moduleId;
            p.type = DamageType.Fire;
            Emit(SimEventType.StationFired, rt.origin, id: m.moduleId, id2: m.slotId, pos2: p.target, uid: target.uid);
            Emit(SimEventType.ProjectileSpawned, p.pos, speed, id: "Shell", uid: p.uid, pos2: p.target);
        }

        private void EmberExplosion(Projectile p)
        {
            var m = Stats.Module("ember_maw");
            float radius = p.radius;
            Emit(SimEventType.Explosion, p.target, radius, id: "ember_maw");
            if (m == null) return;
            float splash = m.P("splash", 0.7f);
            float burnDps = m.P("burnDps", 4f) * (m.damage / Math.Max(0.01f, m.def.damage));
            float burnDur = BurnDuration(m);
            int cap = (int)m.P("burnStacks", 3f);
            // the enemy nearest the impact takes the full hit; the rest take splash damage
            Enemy primary = null;
            float bestD = float.MaxValue;
            for (int i = 0; i < _enemies.Count; i++)
            {
                var e = _enemies[i];
                if (!e.alive) continue;
                float r = radius + e.radius * 0.5f;
                float d2 = Vec2.SqrDistance(e.pos, p.target);
                if (d2 > r * r) continue;
                if (d2 < bestD || (d2 == bestD && primary != null && e.uid < primary.uid)) { bestD = d2; primary = e; }
            }
            bool furnace = HasPerk("ember_furnace_heart");
            ModuleRuntime rt = null;
            foreach (var x in _modules) if (x.moduleId == "ember_maw") rt = x;
            for (int i = 0; i < _enemies.Count; i++)
            {
                var e = _enemies[i];
                if (!e.alive) continue;
                float r = radius + e.radius * 0.5f;
                if (Vec2.SqrDistance(e.pos, p.target) > r * r) continue;
                bool wasBurning = e.IsBurning;
                float dmg = e == primary ? p.damage : p.damage * splash;
                DealDamage(e, dmg, DamageType.Fire, "ember_maw", e == primary ? HitKind.Direct : HitKind.Splash);
                if (!e.alive) continue;
                ApplyBurn(e, burnDps, burnDur, cap);
                if (furnace && wasBurning && rt != null)
                {
                    rt.heat += 1f;
                    if (rt.heat >= PerkP("ember_furnace_heart", "heat", 8f))
                    {
                        rt.heat = 0f;
                        rt.hasteTime = PerkP("ember_furnace_heart", "duration", 5f);
                        Emit(SimEventType.FurnaceHeart, rt.origin, rt.hasteTime);
                    }
                }
            }
        }

        // ---- Frost Whisker: ice bell pulses that slow groups and build to freezes --------------
        private void TickFrostWhisker(ModuleRuntime rt)
        {
            if (!Ready(rt)) return;
            var m = rt.stats;
            if (!Targeting.BestCluster(_enemies, Center, m.range, m.radius, false, false, out var point, out _)) { Idle(rt); return; }
            Rearm(rt);
            rt.shots++;
            Emit(SimEventType.StationFired, rt.origin, id: m.moduleId, id2: m.slotId, pos2: point);
            FrostPulse(point, m.radius, m.damage, m, "frost_whisker", false);
        }

        private void FrostPulse(Vec2 at, float radius, float damage, ModuleStats frost, string source, bool winterRing)
        {
            Emit(winterRing ? SimEventType.WinterRing : SimEventType.FrostPulse, at, radius, id: source);
            float slow = frost != null ? frost.P("slow", 0.3f) : 0.3f;
            float slowDur = frost != null ? frost.P("slowDuration", 2.5f) : 2.5f;
            int stacksToFreeze = frost != null ? (int)Math.Round(frost.P("freezeStacks", 3f)) : 3;
            float freezeDur = frost != null ? frost.P("freezeDuration", 1f) : 1f;
            float r2base = radius;
            for (int i = 0; i < _enemies.Count; i++)
            {
                var e = _enemies[i];
                if (!e.alive) continue;
                float r = r2base + e.radius * 0.5f;
                if (Vec2.SqrDistance(e.pos, at) > r * r) continue;
                if (damage > 0f) DealDamage(e, damage, DamageType.Frost, source, HitKind.Splash);
                if (e.alive) ApplyChill(e, slow, slowDur, 1, stacksToFreeze, freezeDur);
            }
        }

        // ---- Bone Ballista: piercing bolts, armour penetration ------------------------------------
        private void TickBallista(ModuleRuntime rt)
        {
            if (!Ready(rt)) return;
            var m = rt.stats;
            var target = Targeting.Select(_enemies, Center, m.range, Priority);
            if (target == null) { Idle(rt); return; }
            Rearm(rt);
            rt.shots++;
            FireBolt(rt, target);
            if (HasPerk("bone_double_nock") && rt.shots % (int)PerkP("bone_double_nock", "every", 3f) == 0)
            {
                var second = Targeting.Select(_enemies, Center, m.range, Priority, target.uid);
                if (second != null) FireBolt(rt, second);
            }
        }

        private void FireBolt(ModuleRuntime rt, Enemy target)
        {
            var m = rt.stats;
            float speed = Math.Max(4f, m.projectileSpeed);
            float t = Vec2.Distance(rt.origin, target.pos) / speed;
            Vec2 aim = target.IsControlled ? target.pos : target.pos + target.velocity * t;
            var p = NewProjectile();
            p.kind = ProjectileKind.Bolt;
            p.pos = p.prevPos = p.start = rt.origin;
            p.dir = (aim - rt.origin).Normalized;
            if (p.dir.SqrLength < 0.5f) p.dir = Vec2.Up;
            p.target = rt.origin + p.dir * (m.range + 2f);
            p.speed = speed;
            p.damage = m.damage;
            p.radius = m.P("boltRadius", 0.3f);
            p.maxDist = m.range + 2f;
            p.pierceLeft = Math.Max(1, m.targets);
            p.armorPen = m.P("armorPen", 0.6f);
            p.sourceId = m.moduleId;
            p.type = DamageType.Physical;
            p.shotIndex = rt.shots;
            Emit(SimEventType.StationFired, rt.origin, id: m.moduleId, id2: m.slotId, pos2: p.target, uid: target.uid);
            Emit(SimEventType.ProjectileSpawned, p.pos, speed, id: "Bolt", uid: p.uid, pos2: p.target);
        }

        private void BallistaHit(Projectile p, Enemy e)
        {
            Emit(SimEventType.ProjectileHit, e.pos, p.damage, id: "Bolt", uid: e.uid);
            DealDamage(e, p.damage, DamageType.Physical, "bone_ballista", HitKind.Direct, p.armorPen);
            if (!e.alive) return;
            if (HasPerk("bone_barbed_bolts"))
            {
                float dps = PerkP("bone_barbed_bolts", "dps", 4f) * PerkStack("bone_barbed_bolts") * Stats.dmgAll * Stats.dmgPhysical;
                ApplyBleed(e, dps, PerkP("bone_barbed_bolts", "duration", 3f), (int)PerkP("bone_barbed_bolts", "maxStacks", 3f));
            }
            if (HasPerk("bone_armour_break"))
            {
                e.armorBreakAmount = Math.Max(e.armorBreakAmount, PerkP("bone_armour_break", "armor", 20f));
                e.armorBreakTime = PerkP("bone_armour_break", "duration", 4f);
            }
        }

        // ---- Ward Lantern: barriers + slow repair + a damage-reducing aura --------------------------
        private void TickWardLantern(ModuleRuntime rt)
        {
            // repair is applied continuously in UpdateCitadel()
            if (!Ready(rt)) return;
            var m = rt.stats;
            Rearm(rt);
            rt.shots++;
            float amount = AddBarrier(MaxHp * m.P("barrierFraction", 0.06f), m.P("barrierDuration", 6f), "ward_lantern");
            Emit(SimEventType.StationFired, rt.origin, amount, id: m.moduleId, id2: m.slotId);
        }

        // ---- Gravity Paw: pull ordinary enemies together and interrupt their approach -------------
        private void TickGravityPaw(ModuleRuntime rt)
        {
            if (!Ready(rt)) return;
            var m = rt.stats;
            if (!Targeting.BestCluster(_enemies, Center, m.range, m.radius, true, true, out var point, out int count) || count < 1)
            {
                Idle(rt);
                return;
            }
            Rearm(rt);
            rt.shots++;
            Emit(SimEventType.StationFired, rt.origin, id: m.moduleId, id2: m.slotId, pos2: point);
            var z = new Zone
            {
                uid = NewUid(), alive = true, kind = ZoneKind.GravityWell, pos = point, radius = m.radius,
                duration = Math.Max(0.2f, m.duration), pullSpeed = m.P("pullSpeed", 3f), sourceId = m.moduleId,
            };
            _zones.Add(z);
            Emit(SimEventType.GravityWell, point, m.radius, uid: z.uid, value2: z.duration);
            if (m.damage > 0f)
            {
                // Targets that cannot be pulled (golems, bosses) are crushed instead: extra damage.
                float anchored = m.P("anchoredDamageMult", 1f);
                float r2 = m.radius * m.radius;
                for (int i = 0; i < _enemies.Count; i++)
                {
                    var e = _enemies[i];
                    if (!e.alive || Vec2.SqrDistance(e.pos, point) > (m.radius + e.radius * 0.5f) * (m.radius + e.radius * 0.5f)) continue;
                    bool immovable = e.isBoss || e.displacementImmune;
                    DealDamage(e, m.damage * (immovable ? anchored : 1f), DamageType.Gravity, m.moduleId, HitKind.Splash);
                }
            }
        }

        private void UpdateZones()
        {
            for (int zi = 0; zi < _zones.Count; zi++)
            {
                var z = _zones[zi];
                if (!z.alive) continue;
                z.time += Dt;
                float r2 = z.radius * z.radius;
                for (int i = 0; i < _enemies.Count; i++)
                {
                    var e = _enemies[i];
                    if (!e.alive || e.isBoss || e.displacementImmune) continue;
                    if (e.pullZoneUid != z.uid)
                    {
                        if (e.pulledTime > 0f) continue;              // already held by another well
                        if (Vec2.SqrDistance(e.pos, z.pos) > r2) continue;
                        float d = (z.duration - z.time) * ControlMultiplier(e);
                        if (d < 0.1f) continue;
                        e.pulledTime = d;
                        e.pullZoneUid = z.uid;
                        e.pullCenter = z.pos;
                        AddFatigue(e);
                        FreeSlot(e);
                        InterruptPowder(e);
                        RunStats.pulls++;
                    }
                    if (e.pulledTime > 0f)
                    {
                        float speed = z.pullSpeed * (e.elite ? 0.5f : 1f);
                        Vec2 target = z.pos;
                        if (Vec2.Distance(e.pos, target) > 0.25f)
                        {
                            Vec2 np = Vec2.MoveTowards(e.pos, target, speed * Dt);
                            e.velocity = (np - e.pos) / Dt;
                            e.pos = np;
                        }
                    }
                }
                if (z.time >= z.duration) EndWell(z);
            }
        }

        private void EndWell(Zone z)
        {
            z.alive = false;
            Emit(SimEventType.GravityWellEnd, z.pos, z.radius, uid: z.uid);
            if (HasPerk("gravity_crushing_centre"))
            {
                float dmg = PerkP("gravity_crushing_centre", "damage", 25f) * PerkStack("gravity_crushing_centre") * Stats.dmgAll * Stats.dmgGravity;
                AreaDamage(z.pos, PerkP("gravity_crushing_centre", "radius", 0.9f), dmg, DamageType.Gravity, "gravity_crush", 0, null);
            }
            for (int i = 0; i < _enemies.Count; i++)
            {
                var e = _enemies[i];
                if (e.alive && e.pullZoneUid == z.uid) ReleaseFromPull(e, z);
            }
        }

        private void ReleaseFromPull(Enemy e, Zone z)
        {
            e.pulledTime = 0f;
            e.pullZoneUid = 0;
            if (HasPerk("gravity_event_horizon"))
            {
                e.slowOther = Math.Max(e.slowOther, PerkP("gravity_event_horizon", "slow", 0.35f));
                e.slowOtherTime = Math.Max(e.slowOtherTime, PerkP("gravity_event_horizon", "duration", 2f));
            }
            if (HasPerk("gravity_falling_star")) e.recentlyPulledTime = PerkP("gravity_falling_star", "window", 3f);
            // they were displaced off their route: head straight for the citadel again
            if (!e.flying) EnterApproach(e);
            else { e.state = MoveState.Flying; e.goal = FlyGoal(e); }
        }

        // ---- timed perk effects ---------------------------------------------------------------------
        private void UpdatePerkEffects()
        {
            if (!HasPerk("frost_winter_ring")) return;
            _winterTimer -= Dt;
            if (_winterTimer > 0f) return;
            int stacks = PerkStack("frost_winter_ring");
            _winterTimer = Math.Max(2f, PerkP("frost_winter_ring", "interval", 6f) - PerkP("frost_winter_ring", "intervalPerStack", 1.5f) * (stacks - 1));
            float radius = PerkP("frost_winter_ring", "radius", 3.2f) + PerkP("frost_winter_ring", "radiusPerStack", 0.4f) * (stacks - 1);
            float dmg = PerkP("frost_winter_ring", "damage", 8f) * Stats.dmgAll * Stats.dmgFrost;
            FrostPulse(Center, radius, dmg, Stats.Module("frost_whisker"), "frost_winter_ring", true);
        }
    }
}
