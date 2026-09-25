using System;
using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Core;

namespace EvilCats.Sim
{
    public sealed partial class Battle
    {
        private float _heroTimer;
        private readonly List<int> _chainHits = new List<int>(16);

        /// <summary>Arc Light Cat's automatic Arc Bolt. No tapping required.</summary>
        private void UpdateHero()
        {
            if (StormCooldown > 0f) StormCooldown = Math.Max(0f, StormCooldown - Dt);
            if (WardCooldown > 0f) WardCooldown = Math.Max(0f, WardCooldown - Dt);

            _heroTimer -= Dt;
            if (_heroTimer > 0f) return;
            var h = Stats.hero;
            var target = Targeting.Select(_enemies, Center, h.range, Priority);
            if (target == null)
            {
                _heroTimer = 0f;   // ready to fire the moment something enters range
                return;
            }
            _heroTimer = Math.Max(0f, _heroTimer) + h.interval;
            Emit(SimEventType.HeroAttack, target.pos, uid: target.uid);
            DealDamage(target, h.damage, DamageType.Arc, "hero", HitKind.Direct);
            ApplyStaticMark(target);
            ArcChain(target, h.damage, h.chainTargets, h.chainRange, h.chainFalloff, "hero");
        }

        private void ApplyStaticMark(Enemy e)
        {
            if (!e.alive || !HasPerk("arc_static_mark")) return;
            e.markTime = PerkP("arc_static_mark", "duration", 4f);
        }

        /// <summary>
        /// Chain lightning from `first`. Each hop picks the nearest enemy not yet hit by THIS chain
        /// (no enemy is ever hit twice by one chain). Damage falls off per hop. Conductive Chill
        /// extends range and damage toward slowed enemies; Thunderclap bursts on the final hop.
        /// </summary>
        private void ArcChain(Enemy first, float baseDamage, int extraTargets, float range, float falloff, string source)
        {
            _chainHits.Clear();
            _chainHits.Add(first.uid);
            int hops = 0;
            if (extraTargets > 0)
            {
                bool conductive = HasPerk("arc_conductive_chill");
                float slowedRange = conductive ? PerkP("arc_conductive_chill", "rangeMult", 1.5f) : 1f;
                float slowedBonus = conductive ? PerkP("arc_conductive_chill", "damageBonus", 0.25f) : 0f;
                Vec2 from = first.pos;
                float dmg = baseDamage;
                Enemy last = first;
                float lastHopDamage = 0f;
                for (int k = 0; k < extraTargets; k++)
                {
                    var next = Targeting.NearestExcluding(_enemies, from, range, _chainHits, slowedRange);
                    if (next == null) break;
                    dmg *= falloff;
                    float hop = dmg * (next.IsSlowed ? 1f + slowedBonus : 1f);
                    Emit(SimEventType.ChainHop, from, hop, id: source, uid: next.uid, pos2: next.pos);
                    _chainHits.Add(next.uid);
                    from = next.pos;
                    last = next;
                    lastHopDamage = hop;
                    hops++;
                    DealDamage(next, hop, DamageType.Arc, source, HitKind.Direct);
                    if (source == "hero") ApplyStaticMark(next);
                }
                if (hops > 0 && HasPerk("arc_thunderclap"))
                {
                    int stacks = PerkStack("arc_thunderclap");
                    float pct = PerkP("arc_thunderclap", "burstPct", 0.35f) * stacks;
                    float radius = PerkP("arc_thunderclap", "radius", 1.3f);
                    Emit(SimEventType.ThunderclapBurst, from, radius, id: source);
                    float r2 = radius * radius;
                    // the burst never re-hits enemies already struck by this chain
                    for (int i = 0; i < _enemies.Count; i++)
                    {
                        var e = _enemies[i];
                        if (!e.alive || _chainHits.Contains(e.uid)) continue;
                        if (Vec2.SqrDistance(e.pos, from) <= r2)
                            DealDamage(e, lastHopDamage * pct, DamageType.Arc, source, HitKind.Splash);
                    }
                }
            }
            if (hops + 1 > RunStats.maxChain) RunStats.maxChain = hops + 1;
        }

        // ---- abilities --------------------------------------------------------------------------
        /// <summary>The preview location used when the player taps Arc Storm twice (densest threat cluster).</summary>
        public Vec2? DefaultStormTarget()
        {
            if (Targeting.BestCluster(_enemies, Center, 99f, Stats.abilities.stormRadius, false, false, out var p, out _))
                return p;
            return null;
        }

        public int StormTargetsAt(Vec2 point)
        {
            float r2 = Stats.abilities.stormRadius * Stats.abilities.stormRadius;
            int n = 0;
            foreach (var e in _enemies) if (e.alive && Vec2.SqrDistance(e.pos, point) <= r2) n++;
            return Math.Min(n, Stats.abilities.stormTargets);
        }

        /// <summary>Arc Storm: strike up to N enemies in the area for 3× Arc Bolt damage and interrupt them.
        /// Casting on an empty area is refused and does NOT consume the cooldown.</summary>
        public AbilityResult CastArcStorm(Vec2? point)
        {
            if (Phase != BattlePhase.Running) return AbilityResult.NotRunning;
            if (StormCooldown > 0f) return AbilityResult.OnCooldown;
            Vec2? at = point ?? DefaultStormTarget();
            if (!at.HasValue) return AbilityResult.NoTargets;
            var ab = Stats.abilities;
            float r2 = ab.stormRadius * ab.stormRadius;
            var hits = new List<Enemy>();
            foreach (var e in _enemies)
                if (e.alive && Vec2.SqrDistance(e.pos, at.Value) <= r2) hits.Add(e);
            if (hits.Count == 0) return AbilityResult.NoTargets;
            Vec2 c = at.Value;
            hits.Sort((a, b) =>
            {
                int k = Vec2.SqrDistance(a.pos, c).CompareTo(Vec2.SqrDistance(b.pos, c));
                return k != 0 ? k : a.uid.CompareTo(b.uid);
            });
            StormCooldown = ab.stormCooldown;
            RunStats.stormUses++;
            Emit(SimEventType.ArcStormCast, c, ab.stormRadius, value2: Math.Min(hits.Count, ab.stormTargets));
            float dmg = Stats.hero.damage * ab.stormDamageMult;
            for (int i = 0; i < hits.Count && i < ab.stormTargets; i++)
            {
                var e = hits[i];
                Emit(SimEventType.ArcStormStrike, e.pos, dmg, uid: e.uid);
                DealDamage(e, dmg, DamageType.Arc, "arc_storm", HitKind.Direct);
                if (e.alive)
                {
                    ApplyStaticMark(e);
                    ApplyStun(e, ab.stormStun);
                }
            }
            return AbilityResult.Cast;
        }

        /// <summary>Nine-Lives Ward: a barrier worth 20% of max health for 5 s (not a revive).</summary>
        public AbilityResult CastWard()
        {
            if (Phase != BattlePhase.Running) return AbilityResult.NotRunning;
            if (WardCooldown > 0f) return AbilityResult.OnCooldown;
            var ab = Stats.abilities;
            float amount = AddBarrier(MaxHp * ab.wardFraction, ab.wardDuration, "ward");
            WardCooldown = ab.wardCooldown;
            RunStats.wardUses++;
            Emit(SimEventType.WardCast, value: amount, value2: ab.wardDuration);
            return AbilityResult.Cast;
        }
    }
}
