using System;
using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Core;

namespace EvilCats.Sim
{
    public enum HitKind { Direct, Splash, Dot, Effect }

    public sealed partial class Battle
    {
        private int _deathDepth;

        /// <summary>
        /// DAMAGE ORDER (documented in BALANCE.md):
        ///  1. attacker damage (already includes upgrades, perks, permanent, tier, slot)
        ///  2. × (1 + Σ conditional bonuses: Static Mark, Falling Star, Brittle Armour, Executioner)
        ///  3. × critical multiplier (direct hits only, one roll per hit)
        ///  4. × mitigation: Physical uses armour (minus Armour Break, minus penetration);
        ///     elemental uses resist; True ignores both; each capped at 90%
        ///  5. × boss shield-stance reduction
        ///  6. applied to health; death triggers rewards and on-death effects.
        /// </summary>
        public float DealDamage(Enemy e, float amount, DamageType type, string source, HitKind kind, float armorPen = 0f)
        {
            if (e == null || !e.alive || amount <= 0f) return 0f;
            float bonus = 0f;
            if (type == DamageType.Arc && e.markTime > 0f)
                bonus += PerkP("arc_static_mark", "bonus", 0.12f) * PerkStack("arc_static_mark");
            if (e.recentlyPulledTime > 0f && HasPerk("gravity_falling_star"))
                bonus += PerkP("gravity_falling_star", "bonus", 0.15f) * PerkStack("gravity_falling_star");
            if (type == DamageType.Physical && e.IsChilled && HasPerk("frost_brittle_armour"))
                bonus += PerkP("frost_brittle_armour", "bonus", 0.2f);
            if (source == "bone_ballista" && HasPerk("bone_executioner") && e.HealthFraction < PerkP("bone_executioner", "threshold", 0.35f))
                bonus += PerkP("bone_executioner", "bonus", 0.4f) * PerkStack("bone_executioner");
            amount *= 1f + bonus;

            bool crit = false;
            if (kind == HitKind.Direct && _combatRng.Chance(Stats.hero.critChance))
            {
                crit = true;
                amount *= Stats.hero.critMultiplier;
            }

            switch (type)
            {
                case DamageType.Physical:
                {
                    float armor = Math.Max(0f, e.armor - e.armorBreakAmount) * (1f - MathX.Clamp01(armorPen));
                    amount *= 1f - MathX.Clamp(armor, 0f, 90f) / 100f;
                    break;
                }
                case DamageType.True:
                    break;
                default:
                    amount *= 1f - MathX.Clamp(e.resist, 0f, 90f) / 100f;
                    break;
            }
            if (e.isBoss && e.shieldTime > 0f)
            {
                float red = e.boss != null && e.bossDef != null ? ShieldReduction(e) : 0.7f;
                amount *= 1f - red;
            }
            if (amount <= 0f) return 0f;

            float applied = Math.Min(amount, e.hp);
            e.hp -= amount;
            RunStats.Add(RunStats.damageDealtBySource, source, applied);
            if (e.boss != null && e.boss.abilityStage == 1 && ActiveAbilityType(e) == "volley") e.boss.staggerDamage += applied;
            if (kind == HitKind.Dot)
            {
                e.dotNumberAcc += applied;
                if (e.dotNumberTimer <= 0f) e.dotNumberTimer = 0.5f;
            }
            else
            {
                Emit(SimEventType.EnemyHit, e.pos, amount, id: source, uid: e.uid, flags: crit ? SimEvent.FlagCrit : 0, value2: (int)type);
            }
            if (e.hp <= 0f) Kill(e, source, true);
            return applied;
        }

        private void Kill(Enemy e, string source, bool rewards)
        {
            if (!e.alive) return;
            bool wasFrozen = e.frozenTime > 0f;
            int burning = e.burnCount;
            float burnDps = 0f;
            for (int k = 0; k < e.burnCount; k++) burnDps = Math.Max(burnDps, e.burnDps[k]);
            MarkDead(e);
            if (rewards)
            {
                float xp = e.xp * Stats.econ.xpGain;
                float sparks = e.sparks * Stats.econ.sparkGain;
                _sparks += sparks;
                RunStats.AddKill(e.typeId, e.elite, e.isBoss);
                int flags = (e.elite ? SimEvent.FlagElite : 0) | (e.isBoss ? SimEvent.FlagBoss : 0);
                Emit(SimEventType.EnemyDied, e.pos, sparks, id: e.typeId, uid: e.uid, flags: flags, value2: xp, id2: source);
                AddXp(xp);
            }
            if (_deathDepth > 12) return;   // guard against runaway chain reactions
            _deathDepth++;
            try
            {
                if (e.isBoss) OnBossKilled(e);
                if (wasFrozen && HasPerk("frost_shatter")) Shatter(e.pos);
                if (burning > 0 && HasPerk("ember_cinder_spread")) CinderSpread(e, burnDps);
                if (e.typeId == "powder_rat") PowderDeathBlast(e);
            }
            finally
            {
                _deathDepth--;
            }
        }

        private void Shatter(Vec2 at)
        {
            float radius = PerkP("frost_shatter", "radius", 1.5f);
            float dmg = PerkP("frost_shatter", "damage", 30f) * Stats.dmgAll * Stats.dmgFrost;
            Emit(SimEventType.Shatter, at, radius);
            var fm = Stats.Module("frost_whisker");
            AreaDamage(at, radius, dmg, DamageType.Frost, "frost_shatter", 0, e2 =>
            {
                if (fm != null) ApplyChill(e2, fm.P("slow", 0.3f), fm.P("slowDuration", 2.5f), 1, (int)fm.P("freezeStacks", 3f), fm.P("freezeDuration", 1f));
            });
        }

        private void CinderSpread(Enemy dead, float burnDps)
        {
            var m = Stats.Module("ember_maw");
            if (m == null) return;
            float pct = PerkP("ember_cinder_spread", "potency", 0.5f);
            float radius = PerkP("ember_cinder_spread", "radius", 2f);
            int maxTargets = (int)PerkP("ember_cinder_spread", "targets", 2f);
            var exclude = new List<int> { dead.uid };
            for (int i = 0; i < maxTargets; i++)
            {
                var t = Targeting.NearestExcluding(_enemies, dead.pos, radius, exclude);
                if (t == null) break;
                exclude.Add(t.uid);
                ApplyBurn(t, burnDps * pct, BurnDuration(m), (int)m.P("burnStacks", 3f));
                Emit(SimEventType.CinderSpread, dead.pos, pos2: t.pos, uid: t.uid);
            }
        }

        private void PowderDeathBlast(Enemy e)
        {
            float radius = P(e.def, "deathBlastRadius", 1.3f);
            float dmg = P(e.def, "deathBlastDamage", 25f);
            Emit(SimEventType.Explosion, e.pos, radius, id: "powder_keg");
            AreaDamage(e.pos, radius, dmg, DamageType.Fire, "powder_keg", e.uid, null);
        }

        /// <summary>Damage every enemy within radius (enemy radius counts). Returns the number hit.</summary>
        private int AreaDamage(Vec2 at, float radius, float damage, DamageType type, string source, int excludeUid, Action<Enemy> onHit)
        {
            int n = 0;
            for (int i = 0; i < _enemies.Count; i++)
            {
                var e = _enemies[i];
                if (!e.alive || e.uid == excludeUid) continue;
                float r = radius + e.radius * 0.5f;
                if (Vec2.SqrDistance(e.pos, at) > r * r) continue;
                n++;
                DealDamage(e, damage, type, source, HitKind.Splash);
                if (e.alive) onHit?.Invoke(e);
            }
            return n;
        }

        // ---- citadel ----------------------------------------------------------------------------
        private void UpdateCitadel()
        {
            // barriers expire
            float total = 0f;
            for (int i = Barriers.Count - 1; i >= 0; i--)
            {
                var b = Barriers[i];
                b.timeLeft -= Dt;
                if (b.timeLeft <= 0f || b.amount <= 0.01f)
                {
                    if (b.amount > 0.01f) Emit(SimEventType.BarrierExpired, value: b.amount, id: b.source);
                    Barriers.RemoveAt(i);
                    continue;
                }
                total += b.amount;
            }
            BarrierTotal = total;
            // regeneration + Ward Lantern repair (healing never exceeds max health)
            float heal = Stats.citadel.regen * Dt;
            var ward = Stats.Module("ward_lantern");
            if (ward != null) heal += ward.P("repair", 0f) * Stats.citadel.healMult * Dt;
            if (heal > 0f && Hp < MaxHp)
            {
                float before = Hp;
                Hp = Math.Min(MaxHp, Hp + heal);
                RunStats.healed += Hp - before;
            }
        }

        /// <summary>Adds a barrier pool (scaled by barrier bonuses, capped at 60% of max health total).
        /// Returns the amount actually added.</summary>
        public float AddBarrier(float amount, float duration, string source)
        {
            amount *= Stats.citadel.barrierMult;
            float cap = MaxHp * C.Tuning.control.barrierCapFraction;
            float current = 0f;
            foreach (var b in Barriers) current += b.amount;
            amount = Math.Min(amount, Math.Max(0f, cap - current));
            if (amount <= 0.01f) return 0f;
            Barriers.Add(new BarrierPool { amount = amount, timeLeft = duration, source = source });
            BarrierTotal = current + amount;
            Emit(SimEventType.BarrierGained, value: amount, value2: duration, id: source);
            return amount;
        }

        /// <summary>
        /// Citadel damage order: Ward Lantern aura reduction → Last Thread check → barriers
        /// (soonest-expiring first; Reflective Fur reflects part of what they absorb) → health.
        /// </summary>
        private void DamageCitadel(float amount, Enemy attacker, string sourceId)
        {
            if (amount <= 0f || IsOver) return;
            var ward = Stats.Module("ward_lantern");
            if (ward != null && attacker != null && attacker.alive)
            {
                float aura = ward.P("auraRadius", 3.4f);
                if (attacker.pos.SqrLength <= aura * aura) amount *= 1f - ward.P("auraReduction", 0.12f);
            }
            // Last Thread: once per run, an emergency barrier appears before health would fall below 20%.
            if (!_lastThreadUsed && HasPerk("ward_last_thread"))
            {
                float threshold = PerkP("ward_last_thread", "threshold", 0.2f);
                if ((Hp + BarrierTotal - amount) / MaxHp < threshold)
                {
                    _lastThreadUsed = true;
                    AddBarrier(MaxHp * PerkP("ward_last_thread", "barrier", 0.3f), PerkP("ward_last_thread", "duration", 6f), "last_thread");
                    Emit(SimEventType.LastThread, value: BarrierTotal);
                }
            }
            float absorbed = 0f;
            if (Barriers.Count > 0)
            {
                // soonest-expiring pools absorb first
                Barriers.Sort((a, b) => a.timeLeft.CompareTo(b.timeLeft));
                float remaining = amount;
                for (int i = 0; i < Barriers.Count && remaining > 0f; i++)
                {
                    float take = Math.Min(remaining, Barriers[i].amount);
                    Barriers[i].amount -= take;
                    remaining -= take;
                    absorbed += take;
                }
                for (int i = Barriers.Count - 1; i >= 0; i--)
                    if (Barriers[i].amount <= 0.01f) Barriers.RemoveAt(i);
                BarrierTotal = 0f;
                foreach (var b in Barriers) BarrierTotal += b.amount;
                if (absorbed > 0f)
                {
                    RunStats.barrierAbsorbed += absorbed;
                    Emit(SimEventType.BarrierAbsorbed, value: absorbed, id: sourceId, flags: SimEvent.FlagBarrier, value2: BarrierTotal);
                    if (BarrierTotal <= 0.01f) Emit(SimEventType.BarrierExpired, value: 0f, id: "broken");
                    if (attacker != null && attacker.alive && HasPerk("ward_reflective_fur"))
                    {
                        float refl = Math.Min(absorbed * PerkP("ward_reflective_fur", "pct", 0.4f), PerkP("ward_reflective_fur", "cap", 30f));
                        Emit(SimEventType.Reflect, attacker.pos, refl, uid: attacker.uid);
                        DealDamage(attacker, refl, DamageType.True, "ward_reflect", HitKind.Effect);
                    }
                }
            }
            float rest = amount - absorbed;
            if (rest <= 0f) return;
            Hp -= rest;
            RunStats.healthDamageTaken += rest;
            RunStats.Add(RunStats.damageTakenBySource, sourceId, rest);
            float frac = Math.Max(0f, Hp / MaxHp);
            if (frac < RunStats.minHealthFraction) RunStats.minHealthFraction = frac;
            Emit(SimEventType.CitadelDamaged, attacker != null ? attacker.pos : Vec2.Zero, rest, id: sourceId, value2: Hp);
            if (Hp <= 0f)
            {
                Hp = 0f;
                if (Setup.reviveAllowed && !_reviveUsed)
                {
                    Phase = BattlePhase.AwaitingRevive;
                    Emit(SimEventType.ReviveOffered);
                }
                else SetDefeat();
            }
        }

        public string PrincipalDamageSource(out float share)
        {
            string best = null;
            float bestV = 0f, total = 0f;
            foreach (var kv in RunStats.damageTakenBySource)
            {
                total += kv.Value;
                if (kv.Value > bestV || (kv.Value == bestV && string.CompareOrdinal(kv.Key, best) < 0))
                {
                    best = kv.Key;
                    bestV = kv.Value;
                }
            }
            share = total > 0f ? bestV / total : 0f;
            return best;
        }

        // ---- projectiles ------------------------------------------------------------------------
        private Projectile NewProjectile()
        {
            var p = _projectilePool.Count > 0 ? _projectilePool.Pop() : new Projectile();
            p.uid = NewUid();
            p.alive = true;
            p.hits.Clear();
            p.traveled = 0f;
            p.armorPen = 0f;
            p.pierceLeft = 1;
            p.fromEnemy = false;
            p.ownerEnemyUid = 0;
            p.radius = 0f;
            p.shotIndex = 0;
            _projectiles.Add(p);
            return p;
        }

        private readonly List<(Enemy e, float t)> _boltHits = new List<(Enemy, float)>(16);

        private void UpdateProjectiles()
        {
            for (int i = 0; i < _projectiles.Count; i++)
            {
                var p = _projectiles[i];
                if (!p.alive) continue;
                p.prevPos = p.pos;
                float step = p.speed * Dt;
                switch (p.kind)
                {
                    case ProjectileKind.Shell:
                    {
                        p.pos = Vec2.MoveTowards(p.pos, p.target, step);
                        if (Vec2.SqrDistance(p.pos, p.target) < 1e-4f)
                        {
                            p.alive = false;
                            EmberExplosion(p);
                        }
                        break;
                    }
                    case ProjectileKind.Bolt:
                    {
                        Vec2 np = p.pos + p.dir * step;
                        p.traveled += step;
                        _boltHits.Clear();
                        for (int k = 0; k < _enemies.Count; k++)
                        {
                            var e = _enemies[k];
                            if (!e.alive || p.hits.Contains(e.uid)) continue;
                            float r = p.radius + e.radius;
                            if (Vec2.SqrDistanceToSegment(e.pos, p.pos, np) > r * r) continue;
                            _boltHits.Add((e, Vec2.Dot(e.pos - p.pos, p.dir)));
                        }
                        _boltHits.Sort((a, b) => a.t != b.t ? a.t.CompareTo(b.t) : a.e.uid.CompareTo(b.e.uid));
                        foreach (var h in _boltHits)
                        {
                            if (p.pierceLeft <= 0) break;
                            p.hits.Add(h.e.uid);
                            p.pierceLeft--;
                            BallistaHit(p, h.e);
                        }
                        p.pos = np;
                        if (p.pierceLeft <= 0 || p.traveled >= p.maxDist) p.alive = false;
                        break;
                    }
                    default:
                    {
                        // enemy shots fly at the citadel
                        p.pos = Vec2.MoveTowards(p.pos, p.target, step);
                        if (p.pos.Length <= C.Tuning.arena.citadelRadius)
                        {
                            p.alive = false;
                            Enemy owner = FindEnemy(p.ownerEnemyUid);
                            Emit(SimEventType.ProjectileHit, p.pos, p.damage, id: p.kind.ToString(), uid: p.uid);
                            DamageCitadel(p.damage, owner, p.sourceId);
                            if (IsOver || Phase != BattlePhase.Running) return;
                        }
                        break;
                    }
                }
            }
        }

        private Enemy FindEnemy(int uid)
        {
            if (uid == 0) return null;
            for (int i = 0; i < _enemies.Count; i++) if (_enemies[i].uid == uid && _enemies[i].alive) return _enemies[i];
            return null;
        }

        // ---- status application helpers -----------------------------------------------------------
        private float BurnDuration(ModuleStats m) => m.P("burnDuration", 3f);

        private void ApplyBurn(Enemy e, float dps, float duration, int cap)
        {
            if (!e.alive || dps <= 0f) return;
            cap = MathX.Clamp(cap, 1, e.burnDps.Length);
            if (e.burnCount < cap)
            {
                e.burnDps[e.burnCount] = dps;
                e.burnTime[e.burnCount] = duration;
                e.burnCount++;
            }
            else
            {
                // at the cap: refresh the weakest-remaining stack (capped burning)
                int idx = 0;
                for (int k = 1; k < e.burnCount; k++) if (e.burnTime[k] < e.burnTime[idx]) idx = k;
                e.burnDps[idx] = Math.Max(e.burnDps[idx], dps);
                e.burnTime[idx] = duration;
            }
            RunStats.burnsApplied++;
        }

        private void ApplyBleed(Enemy e, float dps, float duration, int cap)
        {
            if (!e.alive || dps <= 0f) return;
            cap = MathX.Clamp(cap, 1, e.bleedDps.Length);
            if (e.bleedCount < cap)
            {
                e.bleedDps[e.bleedCount] = dps;
                e.bleedTime[e.bleedCount] = duration;
                e.bleedCount++;
            }
            else
            {
                int idx = 0;
                for (int k = 1; k < e.bleedCount; k++) if (e.bleedTime[k] < e.bleedTime[idx]) idx = k;
                e.bleedTime[idx] = duration;
            }
        }
    }
}
