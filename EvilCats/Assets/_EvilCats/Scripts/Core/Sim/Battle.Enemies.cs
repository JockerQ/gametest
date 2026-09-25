using System;
using EvilCats.Content;
using EvilCats.Core;

namespace EvilCats.Sim
{
    public sealed partial class Battle
    {
        private void UpdateEnemies()
        {
            for (int i = 0; i < _enemies.Count; i++)
            {
                var e = _enemies[i];
                if (!e.alive) continue;
                e.prevPos = e.pos;
                UpdateStatuses(e);
                if (!e.alive) continue;
                if (e.isBoss) UpdateBoss(e);
                else UpdateEnemy(e);
                if (e.alive) e.pos = ClampToArena(e.pos);
            }
        }

        // ---- status effects ---------------------------------------------------------------------
        private void UpdateStatuses(Enemy e)
        {
            var ctl = C.Tuning.control;
            // damage over time
            float burn = 0f;
            for (int k = e.burnCount - 1; k >= 0; k--)
            {
                burn += e.burnDps[k] * Dt;
                e.burnTime[k] -= Dt;
                if (e.burnTime[k] <= 0f)
                {
                    e.burnCount--;
                    e.burnDps[k] = e.burnDps[e.burnCount];
                    e.burnTime[k] = e.burnTime[e.burnCount];
                }
            }
            float bleed = 0f;
            for (int k = e.bleedCount - 1; k >= 0; k--)
            {
                bleed += e.bleedDps[k] * Dt;
                e.bleedTime[k] -= Dt;
                if (e.bleedTime[k] <= 0f)
                {
                    e.bleedCount--;
                    e.bleedDps[k] = e.bleedDps[e.bleedCount];
                    e.bleedTime[k] = e.bleedTime[e.bleedCount];
                }
            }
            if (burn > 0f) DealDamage(e, burn, DamageType.Fire, "ember_burn", HitKind.Dot);
            if (!e.alive) return;
            if (bleed > 0f) DealDamage(e, bleed, DamageType.True, "bone_bleed", HitKind.Dot);
            if (!e.alive) return;
            if (e.dotNumberAcc > 0f)
            {
                e.dotNumberTimer -= Dt;
                if (e.dotNumberTimer <= 0f)
                {
                    Emit(SimEventType.EnemyHit, e.pos, e.dotNumberAcc, uid: e.uid, flags: SimEvent.FlagDot);
                    e.dotNumberAcc = 0f;
                    e.dotNumberTimer = 0.5f;
                }
            }

            // control and timers
            if (e.stunTime > 0f) e.stunTime = Math.Max(0f, e.stunTime - Dt);
            if (e.frozenTime > 0f)
            {
                e.frozenTime -= Dt;
                if (e.frozenTime <= 0f)
                {
                    e.frozenTime = 0f;
                    e.freezeImmuneTime = ctl.freezeImmunity;
                }
            }
            if (e.freezeImmuneTime > 0f) e.freezeImmuneTime -= Dt;
            if (e.slowFrostTime > 0f) { e.slowFrostTime -= Dt; if (e.slowFrostTime <= 0f) { e.slowFrost = 0f; e.chillStacks = 0; } }
            if (e.slowOtherTime > 0f) { e.slowOtherTime -= Dt; if (e.slowOtherTime <= 0f) e.slowOther = 0f; }
            if (e.markTime > 0f) e.markTime -= Dt;
            if (e.armorBreakTime > 0f) { e.armorBreakTime -= Dt; if (e.armorBreakTime <= 0f) e.armorBreakAmount = 0f; }
            if (e.recentlyPulledTime > 0f) e.recentlyPulledTime -= Dt;
            if (e.buffTime > 0f) { e.buffTime -= Dt; if (e.buffTime <= 0f) e.buffMult = 1f; }
            if (e.shieldTime > 0f) e.shieldTime -= Dt;
            if (e.fatigue > 0f && !e.IsControlled) e.fatigue = Math.Max(0f, e.fatigue - ctl.fatigueDecayPerSec * Dt);
            if (e.pulledTime > 0f)
            {
                e.pulledTime -= Dt;
                if (e.pulledTime <= 0f) ReleaseFromPull(e, null);
            }
        }

        /// <summary>
        /// Control duration multiplier. Every hard control adds "fatigue" that shortens the next
        /// control (diminishing returns), so no build can keep an enemy stunned forever.
        /// Bosses/elites additionally resist through controlResist.
        /// </summary>
        public float ControlMultiplier(Enemy e) => Math.Max(0f, (1f - e.fatigue) * (1f - e.controlResist));

        private void AddFatigue(Enemy e)
        {
            var ctl = C.Tuning.control;
            e.fatigue = Math.Min(ctl.fatigueMax, e.fatigue + ctl.fatiguePerControl);
        }

        public void ApplyStun(Enemy e, float duration)
        {
            if (!e.alive) return;
            float d = duration * ControlMultiplier(e);
            if (d < 0.05f) return;
            e.stunTime = Math.Max(e.stunTime, d);
            AddFatigue(e);
            InterruptPowder(e);
        }

        private float SlowCap(Enemy e)
        {
            var ctl = C.Tuning.control;
            if (e.isBoss) return ctl.bossSlowCap;
            if (e.elite) return ctl.eliteSlowCap;
            return ctl.slowCap;
        }

        /// <summary>Different slow sources do not add up: the strongest applies, capped.</summary>
        public float SlowFactor(Enemy e)
        {
            float s = 0f;
            if (e.slowFrostTime > 0f) s = Math.Max(s, e.slowFrost);
            if (e.slowOtherTime > 0f) s = Math.Max(s, e.slowOther);
            float cap = SlowCap(e);
            if (e.enraged) cap = Math.Min(cap, 0.3f);
            return MathX.Clamp(s, 0f, cap);
        }

        private float EffectiveSpeed(Enemy e)
        {
            float s = e.speed * (1f - SlowFactor(e));
            if (e.buffTime > 0f) s *= e.buffMult;
            if (e.enraged) s *= 1.6f;
            return s;
        }

        private void ApplyChill(Enemy e, float slow, float duration, int stacks, int stacksToFreeze, float freezeDuration)
        {
            if (!e.alive) return;
            e.slowFrost = e.slowFrostTime > 0f ? Math.Max(e.slowFrost, slow) : slow;
            e.slowFrostTime = Math.Max(e.slowFrostTime, duration);
            if (e.isBoss || e.frozenTime > 0f || e.freezeImmuneTime > 0f || stacks <= 0) return;
            e.chillStacks += stacks;
            if (e.chillStacks >= Math.Max(1, stacksToFreeze))
            {
                e.chillStacks = 0;
                float d = freezeDuration * ControlMultiplier(e);
                if (d < 0.05f) return;
                e.frozenTime = d;
                AddFatigue(e);
                InterruptPowder(e);
                RunStats.freezes++;
                Emit(SimEventType.Freeze, e.pos, d, uid: e.uid);
            }
        }

        // ---- movement / behaviour ----------------------------------------------------------------
        private void UpdateEnemy(Enemy e)
        {
            if (e.stunTime > 0f || e.frozenTime > 0f || e.pulledTime > 0f)
            {
                e.velocity = Vec2.Zero;
                return;
            }
            if (e.def != null && e.def.role == EnemyRole.Support) UpdatePriestHeal(e);
            if (e.typeId == "powder_rat" && UpdatePowder(e)) return;

            float speed = EffectiveSpeed(e);
            switch (e.state)
            {
                case MoveState.Route: MoveAlongRoute(e, speed); break;
                case MoveState.Approach: MoveApproach(e, speed); break;
                case MoveState.Flying: MoveFlying(e, speed); break;
                case MoveState.Holding: HoldAndAttack(e); break;
            }
            DetectStuck(e);
        }

        private void MoveAlongRoute(Enemy e, float speed)
        {
            var r = Routes.routes[e.route];
            e.routeDist += speed * Dt;
            // lateral offset narrows as the enemy nears the citadel so paths converge cleanly
            float lateral = e.lateral * MathX.Clamp01((r.Length - e.routeDist) / 3f + 0.25f);
            Vec2 np = r.SampleOffset(e.routeDist, lateral);
            e.velocity = (np - e.pos) / Dt;
            e.pos = np;
            if (IsRanged(e) && e.pos.Length <= e.attackRange)
            {
                e.state = MoveState.Holding;
                e.velocity = Vec2.Zero;
                return;
            }
            if (e.routeDist >= r.Length) EnterApproach(e);
        }

        private bool IsRanged(Enemy e) => e.attackRange > 0.1f && (e.role == EnemyRole.Ranged || e.role == EnemyRole.Support || e.isBoss && e.attackRange > C.Tuning.arena.meleeRing + 0.8f);

        private void EnterApproach(Enemy e)
        {
            if (e.flying)
            {
                e.state = MoveState.Flying;
                e.goal = FlyGoal(e);
                return;
            }
            if (IsRanged(e))
            {
                float d = e.pos.Length;
                if (d <= e.attackRange)
                {
                    e.state = MoveState.Holding;
                    return;
                }
                e.goal = e.pos.Normalized * e.attackRange;
                e.state = MoveState.Approach;
                return;
            }
            if (e.typeId == "powder_rat")
            {
                e.goal = e.pos.Normalized * (C.Tuning.arena.citadelRadius + e.radius);
                e.state = MoveState.Approach;
                return;
            }
            AssignSlot(e);
            e.state = MoveState.Approach;
            e.lastGoalDist = float.MaxValue;
        }

        private void MoveApproach(Enemy e, float speed)
        {
            Vec2 np = Vec2.MoveTowards(e.pos, e.goal, speed * Dt);
            e.velocity = (np - e.pos) / Dt;
            e.pos = np;
            if (Vec2.SqrDistance(e.pos, e.goal) < 0.0009f)
            {
                e.state = MoveState.Holding;
                e.velocity = Vec2.Zero;
            }
        }

        private void MoveFlying(Enemy e, float speed)
        {
            Vec2 to = e.goal - e.pos;
            float dist = to.Length;
            if (dist < 0.12f)
            {
                e.state = MoveState.Holding;
                e.velocity = Vec2.Zero;
                return;
            }
            Vec2 dir = to / dist;
            float wob = MathF.Sin(Time * 3.1f + e.wobble) * 0.45f * Math.Min(1f, dist / 2f);
            Vec2 step = dir * (speed * Dt) + dir.Perp * (wob * speed * Dt);
            if (step.Length > dist) step = to;
            e.velocity = step / Dt;
            e.pos += step;
        }

        /// <summary>Slows also slow attacks (same caps as movement), so control matters at the wall.</summary>
        private float AttackRate(Enemy e)
        {
            float rate = e.buffTime > 0f ? e.buffMult : 1f;
            return rate * (1f - SlowFactor(e));
        }

        private void HoldAndAttack(Enemy e)
        {
            e.velocity = Vec2.Zero;
            e.attackTimer -= Dt * AttackRate(e);
            if (e.attackTimer > 0f) return;
            e.attackTimer += e.attackInterval;
            if (IsRanged(e))
            {
                FireEnemyProjectile(e, e.role == EnemyRole.Support ? ProjectileKind.Arrow : ProjectileKind.Arrow, e.damage * (e.buffTime > 0f ? e.buffMult : 1f), e.typeId);
            }
            else
            {
                Emit(SimEventType.EnemyAttack, e.pos, e.damage, id: e.typeId, uid: e.uid);
                DamageCitadel(e.damage * (e.buffTime > 0f ? e.buffMult : 1f), e, e.typeId);
            }
        }

        private void FireEnemyProjectile(Enemy e, ProjectileKind kind, float damage, string sourceId)
        {
            var p = NewProjectile();
            p.kind = kind;
            p.fromEnemy = true;
            p.ownerEnemyUid = e.uid;
            p.sourceId = sourceId;
            p.pos = p.prevPos = p.start = e.pos;
            p.target = Vec2.Zero;
            p.dir = (-e.pos).Normalized;
            p.speed = e.projectileSpeed > 0f ? e.projectileSpeed : 9f;
            p.damage = damage;
            p.type = DamageType.Physical;
            Emit(SimEventType.EnemyAttack, e.pos, damage, id: e.typeId, uid: e.uid, flags: 1);
            Emit(SimEventType.ProjectileSpawned, p.pos, p.speed, id: kind.ToString(), uid: p.uid, pos2: p.target);
        }

        private void UpdatePriestHeal(Enemy e)
        {
            e.healTimer -= Dt;
            if (e.healTimer > 0f) return;
            var d = e.def;
            e.healTimer = P(d, "healInterval", 3.5f);
            float radius = P(d, "healRadius", 2.8f);
            float pct = P(d, "healPct", 0.12f);
            float r2 = radius * radius;
            int healed = 0;
            float bossFrac = C.Tuning.control.bellHealBossFraction;
            foreach (var o in _enemies)
            {
                if (!o.alive || o.hp >= o.maxHp) continue;
                if (Vec2.SqrDistance(o.pos, e.pos) > r2) continue;
                float amount = o.maxHp * (o.isBoss ? bossFrac : pct);
                o.hp = Math.Min(o.maxHp, o.hp + amount);
                healed++;
            }
            if (healed > 0) Emit(SimEventType.PriestHeal, e.pos, radius, uid: e.uid, value2: healed);
        }

        /// <returns>true when the powder logic fully handled this tick's movement.</returns>
        private bool UpdatePowder(Enemy e)
        {
            var d = e.def;
            switch (e.powder)
            {
                case PowderState.Walking:
                    if (e.pos.Length <= P(d, "fuseDistance", 4.2f))
                    {
                        e.powder = PowderState.Fuse;
                        e.powderTimer = P(d, "fuseTime", 1.4f);
                        e.velocity = Vec2.Zero;
                        Emit(SimEventType.PowderFuse, e.pos, e.powderTimer, uid: e.uid);
                        return true;
                    }
                    return false;
                case PowderState.Fuse:
                    e.velocity = Vec2.Zero;
                    e.powderTimer -= Dt;
                    if (e.powderTimer <= 0f)
                    {
                        e.powder = PowderState.Charge;
                        FreeSlot(e);
                    }
                    return true;
                case PowderState.Charge:
                {
                    float speed = P(d, "chargeSpeed", 3.8f) * (1f - SlowFactor(e));
                    float target = C.Tuning.arena.citadelRadius + e.radius * 0.5f;
                    Vec2 goal = e.pos.Normalized * target;
                    Vec2 np = Vec2.MoveTowards(e.pos, goal, speed * Dt);
                    e.velocity = (np - e.pos) / Dt;
                    e.pos = np;
                    if (e.pos.Length <= target + 0.02f)
                    {
                        float dmg = P(d, "explodeDamage", 70f) * (_plan != null ? _plan.damageMult : 1f) * (e.elite ? C.Tuning.elite.damageMult : 1f);
                        Emit(SimEventType.PowderExploded, e.pos, dmg, uid: e.uid);
                        MarkDead(e);
                        DamageCitadel(dmg, null, "powder_rat");
                    }
                    return true;
                }
                case PowderState.Dazed:
                    e.velocity = Vec2.Zero;
                    e.powderTimer -= Dt;
                    if (e.powderTimer <= 0f)
                    {
                        e.powder = PowderState.Walking;
                        if (e.state == MoveState.Holding) EnterApproach(e);
                    }
                    return true;
            }
            return false;
        }

        private void InterruptPowder(Enemy e)
        {
            if (e.typeId != "powder_rat") return;
            if (e.powder != PowderState.Fuse && e.powder != PowderState.Charge) return;
            e.powder = PowderState.Dazed;
            e.powderTimer = P(e.def, "dazeTime", 1.0f);
            RunStats.powderInterrupts++;
            Emit(SimEventType.PowderInterrupted, e.pos, uid: e.uid);
        }

        private void DetectStuck(Enemy e)
        {
            if (e.state == MoveState.Holding) { e.stuckTimer = 0f; return; }
            float dist = e.state == MoveState.Route ? Routes.routes[e.route].Length - e.routeDist : Vec2.Distance(e.pos, e.goal);
            if (dist < e.lastGoalDist - 0.02f)
            {
                e.lastGoalDist = dist;
                e.stuckTimer = 0f;
                return;
            }
            // being slowed to a crawl is not "stuck"
            if (EffectiveSpeed(e) < 0.05f) return;
            e.stuckTimer += Dt;
            if (e.stuckTimer < C.Tuning.arena.stuckSeconds) return;
            e.stuckTimer = 0f;
            e.lastGoalDist = float.MaxValue;
            if (e.state == MoveState.Route) e.routeDist += 1f;
            else if (e.state == MoveState.Approach) { if (!IsRanged(e)) AssignSlot(e); e.pos = Vec2.MoveTowards(e.pos, e.goal, 0.5f); }
            else e.pos = Vec2.MoveTowards(e.pos, e.goal, 0.5f);
            Emit(SimEventType.StallRecovered, e.pos, 0f, uid: e.uid);
        }
    }
}
