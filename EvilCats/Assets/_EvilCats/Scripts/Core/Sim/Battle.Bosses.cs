using System;
using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Core;

namespace EvilCats.Sim
{
    /// <summary>
    /// Boss behaviour. Because the citadel cannot move, every boss attack has counterplay through
    /// the player's real tools: barriers (Nine-Lives Ward, Ward Lantern), interrupts (Arc Storm,
    /// Frost, Gravity), target choices (killing summons / sector crows) or burst damage (staggering
    /// Goldenfang's volley). Windups are always telegraphed with events the HUD shows.
    /// </summary>
    public sealed partial class Battle
    {
        public Enemy ActiveBoss { get; private set; }

        private void SpawnBoss(SpawnOrder o)
        {
            var def = C.Boss(o.enemyId);
            if (def == null) return;
            var e = NewEnemy();
            e.typeId = def.id;
            e.bossDef = def;
            e.isBoss = true;
            e.role = EnemyRole.Boss;
            e.flying = def.flying;
            e.displacementImmune = true;
            e.radius = def.radius;
            e.scale = 1f;
            float hpMult = _plan != null ? _plan.healthMult : 1f;
            float dmgMult = _plan != null ? _plan.damageMult : 1f;
            e.maxHp = e.hp = def.health * hpMult;
            e.armor = MathX.Clamp(def.armor + (_plan != null ? _plan.armorAdd : 0f), 0f, 90f);
            e.resist = MathX.Clamp(def.resist, 0f, 90f);
            e.speed = def.speed;
            e.damage = def.damage * dmgMult;
            e.attackInterval = def.attackInterval;
            e.attackRange = def.stopDistance > C.Tuning.arena.meleeRing + 0.8f ? def.stopDistance : 0f;
            e.projectileSpeed = 8f;
            e.controlResist = MathX.Clamp01(def.controlResist);
            e.xp = def.xp;
            e.sparks = def.sparks;
            e.route = MathX.Clamp(o.route, 0, Routes.routes.Count - 1);
            e.attackTimer = def.attackInterval;
            e.boss = new BossRuntime { abilityTimers = new float[def.abilities.Count] };
            for (int i = 0; i < def.abilities.Count; i++) e.boss.abilityTimers[i] = def.abilities[i].firstDelay;
            var route = Routes.routes[e.route];
            e.pos = e.prevPos = ClampToArena(route.Start);
            if (e.flying) { e.state = MoveState.Flying; e.goal = FlyGoal(e); }
            else e.state = MoveState.Route;
            e.lastGoalDist = float.MaxValue;
            _enemies.Add(e);
            AliveCount++;
            ActiveBoss = e;
            Emit(SimEventType.BossSpawned, e.pos, e.maxHp, id: def.id, uid: e.uid, flags: SimEvent.FlagBoss);
        }

        private float BossP(BossAbilityDef a, string key, float fallback) =>
            a.p != null && a.p.TryGetValue(key, out var v) ? v : fallback;

        private string ActiveAbilityType(Enemy e)
        {
            if (e.boss == null || e.boss.activeAbility < 0) return null;
            return e.bossDef.abilities[e.boss.activeAbility].type;
        }

        private float ShieldReduction(Enemy e)
        {
            foreach (var a in e.bossDef.abilities)
                if (a.type == "shield_stance") return BossP(a, "reduction", 0.7f);
            return 0.7f;
        }

        private BossPhaseDef PhaseDef(Enemy e)
        {
            BossPhaseDef best = null;
            foreach (var p in e.bossDef.phases)
                if (p.phase == e.boss.phase) best = p;
            return best;
        }

        private void UpdateBoss(Enemy e)
        {
            var b = e.boss;
            var def = e.bossDef;
            // phase transitions by health
            int phase = 1;
            foreach (var p in def.phases)
                if (e.HealthFraction <= p.healthBelow && p.phase > phase) phase = p.phase;
            if (phase > b.phase)
            {
                b.phase = phase;
                Emit(SimEventType.BossPhase, e.pos, phase, id: def.id, uid: e.uid);
            }
            // stun/freeze delays everything, including windups (bosses have high control resist)
            if (e.stunTime > 0f || e.frozenTime > 0f)
            {
                e.velocity = Vec2.Zero;
                return;
            }
            var pd = PhaseDef(e);
            float cdMult = pd != null ? pd.cooldownMult : 1f;
            float atkMult = pd != null ? pd.attackSpeedMult : 1f;

            if (b.activeAbility >= 0)
            {
                UpdateBossAbility(e, def.abilities[b.activeAbility]);
                return;
            }

            // tick ability timers; start the first ready one that is legal in this phase
            for (int i = 0; i < def.abilities.Count; i++)
            {
                var a = def.abilities[i];
                if (b.phase < a.minPhase || b.phase > a.maxPhase) continue;
                b.abilityTimers[i] -= Dt;
            }
            bool arrived = e.state == MoveState.Holding;
            for (int i = 0; i < def.abilities.Count; i++)
            {
                var a = def.abilities[i];
                if (b.phase < a.minPhase || b.phase > a.maxPhase || b.abilityTimers[i] > 0f) continue;
                if (!arrived && a.type != "summon" && a.type != "decree") continue;
                StartBossAbility(e, i);
                b.abilityTimers[i] = a.cooldown * cdMult;
                return;
            }

            // normal movement and basic attacks
            float speed = EffectiveSpeed(e);
            switch (e.state)
            {
                case MoveState.Route: MoveAlongRoute(e, speed); break;
                case MoveState.Approach: MoveApproach(e, speed); break;
                case MoveState.Flying: MoveFlying(e, speed); break;
                case MoveState.Holding:
                    if (e.flying) OrbitHover(e);
                    e.attackTimer -= Dt * atkMult * AttackRate(e);
                    if (e.attackTimer <= 0f)
                    {
                        e.attackTimer += e.attackInterval;
                        if (IsRanged(e)) FireEnemyProjectile(e, def.flying ? ProjectileKind.Feather : ProjectileKind.ScepterBolt, e.damage, def.id);
                        else
                        {
                            Emit(SimEventType.EnemyAttack, e.pos, e.damage, id: def.id, uid: e.uid, flags: SimEvent.FlagBoss);
                            DamageCitadel(e.damage, e, def.id);
                        }
                    }
                    break;
            }
            DetectStuck(e);
        }

        private void OrbitHover(Enemy e)
        {
            // Mother Carrion drifts slowly around the citadel so her marked sector changes
            float ang = e.pos.Angle + 0.07f * Dt;
            float r = e.bossDef.stopDistance;
            e.pos = Vec2.FromAngle(ang, r);
        }

        private void StartBossAbility(Enemy e, int index)
        {
            var b = e.boss;
            var a = e.bossDef.abilities[index];
            switch (a.type)
            {
                case "summon":
                    DoSummon(e, a);
                    Emit(SimEventType.BossAbility, e.pos, id: a.id, uid: e.uid, id2: a.type);
                    return; // instant
                case "decree":
                {
                    float buff = BossP(a, "buff", 0.2f);
                    float dur = BossP(a, "duration", 6f);
                    foreach (var o in _enemies)
                        if (o.alive && !o.isBoss) { o.buffMult = 1f + buff; o.buffTime = dur; }
                    Emit(SimEventType.BossAbility, e.pos, dur, id: a.id, uid: e.uid, id2: a.type);
                    return;
                }
            }
            b.activeAbility = index;
            b.abilityStage = 1;
            b.stageTimer = a.windup;
            b.staggerDamage = 0f;
            switch (a.type)
            {
                case "shield_stance":
                    Emit(SimEventType.BossTelegraph, e.pos, a.windup, id: a.id, uid: e.uid, id2: a.type);
                    break;
                case "charge":
                {
                    // step back first, then a long visible windup toward the citadel
                    b.abilityStage = 0;
                    float retreat = BossP(a, "retreat", 5.5f);
                    Vec2 dir = e.pos.SqrLength > 1e-3f ? e.pos.Normalized : Vec2.Up;
                    b.chargeFrom = ClampToArena(dir * retreat);
                    b.chargeTo = dir * (C.Tuning.arena.meleeRing + Math.Max(0f, e.radius - 0.4f));
                    FreeSlot(e);
                    break;
                }
                case "sector_barrage":
                {
                    b.sectorAngle = e.pos.Angle;
                    float half = BossP(a, "halfAngle", 32f) * MathX.Deg2Rad;
                    Emit(SimEventType.BossTelegraph, e.pos, a.windup, id: a.id, uid: e.uid, id2: a.type,
                        value2: half, pos2: Vec2.FromAngle(b.sectorAngle, 1f));
                    break;
                }
                case "volley":
                    Emit(SimEventType.BossTelegraph, e.pos, a.windup, id: a.id, uid: e.uid, id2: a.type,
                        value2: BossP(a, "staggerFraction", 0.08f) * e.maxHp);
                    break;
                default:
                    Emit(SimEventType.BossTelegraph, e.pos, a.windup, id: a.id, uid: e.uid, id2: a.type);
                    break;
            }
        }

        private void UpdateBossAbility(Enemy e, BossAbilityDef a)
        {
            var b = e.boss;
            float dmgMult = _plan != null ? _plan.damageMult : 1f;
            switch (a.type)
            {
                case "shield_stance":
                    if (b.abilityStage == 1)
                    {
                        b.stageTimer -= Dt;
                        if (b.stageTimer <= 0f)
                        {
                            b.abilityStage = 2;
                            b.stageTimer = a.duration;
                            e.shieldTime = a.duration;
                            DoSummon(e, a);
                            Emit(SimEventType.BossAbility, e.pos, a.duration, id: a.id, uid: e.uid, id2: a.type);
                        }
                    }
                    else
                    {
                        b.stageTimer -= Dt;
                        if (b.stageTimer <= 0f) EndBossAbility(e);
                    }
                    break;

                case "charge":
                    if (b.abilityStage == 0)
                    {
                        // retreat
                        e.pos = Vec2.MoveTowards(e.pos, b.chargeFrom, 3.2f * Dt);
                        e.velocity = (e.pos - e.prevPos) / Dt;
                        if (Vec2.SqrDistance(e.pos, b.chargeFrom) < 0.01f)
                        {
                            b.abilityStage = 1;
                            b.stageTimer = a.windup;
                            Emit(SimEventType.BossTelegraph, e.pos, a.windup, id: a.id, uid: e.uid, id2: a.type, pos2: b.chargeTo);
                        }
                    }
                    else if (b.abilityStage == 1)
                    {
                        e.velocity = Vec2.Zero;
                        b.stageTimer -= Dt;
                        if (b.stageTimer <= 0f) b.abilityStage = 2;
                    }
                    else
                    {
                        float speed = BossP(a, "speed", 12f);
                        e.pos = Vec2.MoveTowards(e.pos, b.chargeTo, speed * Dt);
                        e.velocity = (e.pos - e.prevPos) / Dt;
                        if (Vec2.SqrDistance(e.pos, b.chargeTo) < 0.01f)
                        {
                            float dmg = BossP(a, "damage", 160f) * dmgMult;
                            Emit(SimEventType.BossAbility, e.pos, dmg, id: a.id, uid: e.uid, id2: "charge_impact");
                            DamageCitadel(dmg, e, a.id);
                            EndBossAbility(e);
                            if (e.alive) { AssignSlot(e); e.state = MoveState.Approach; }
                        }
                    }
                    break;

                case "sector_barrage":
                    if (b.abilityStage == 1)
                    {
                        b.stageTimer -= Dt;
                        if (b.stageTimer <= 0f)
                        {
                            // Counterplay: every ranged minion still alive in the marked sector adds feathers.
                            float half = BossP(a, "halfAngle", 32f) * MathX.Deg2Rad;
                            int inSector = 0;
                            foreach (var o in _enemies)
                            {
                                if (!o.alive || o.isBoss || !o.IsRangedThreat) continue;
                                if (Math.Abs(MathX.WrapAngle(o.pos.Angle - b.sectorAngle)) <= half) inSector++;
                            }
                            b.feathersLeft = (int)BossP(a, "baseCount", 8f) + (int)BossP(a, "perMinion", 3f) * inSector;
                            b.featherTimer = 0f;
                            b.abilityStage = 2;
                            b.stageTimer = Math.Max(0.3f, a.duration);
                            Emit(SimEventType.BossAbility, e.pos, b.feathersLeft, id: a.id, uid: e.uid, id2: a.type, value2: inSector);
                        }
                    }
                    else
                    {
                        float interval = Math.Max(0.05f, a.duration / Math.Max(1, b.feathersLeft));
                        b.featherTimer -= Dt;
                        while (b.featherTimer <= 0f && b.feathersLeft > 0)
                        {
                            b.featherTimer += interval;
                            b.feathersLeft--;
                            float half = BossP(a, "halfAngle", 32f) * MathX.Deg2Rad;
                            float ang = b.sectorAngle + _combatRng.Range(-half, half);
                            var p = NewProjectile();
                            p.kind = ProjectileKind.Feather;
                            p.fromEnemy = true;
                            p.ownerEnemyUid = e.uid;
                            p.sourceId = a.id;
                            p.pos = p.prevPos = p.start = Vec2.FromAngle(ang, 7f);
                            p.target = Vec2.Zero;
                            p.speed = 10f;
                            p.damage = BossP(a, "damage", 14f) * dmgMult;
                            p.type = DamageType.Physical;
                            Emit(SimEventType.ProjectileSpawned, p.pos, p.speed, id: "Feather", uid: p.uid, pos2: p.target);
                        }
                        if (b.feathersLeft <= 0) EndBossAbility(e);
                    }
                    break;

                case "volley":
                    b.stageTimer -= Dt;
                    if (b.stageTimer <= 0f)
                    {
                        float dmg = BossP(a, "damage", 260f) * dmgMult;
                        bool staggered = b.staggerDamage >= BossP(a, "staggerFraction", 0.08f) * e.maxHp;
                        if (staggered)
                        {
                            dmg *= BossP(a, "staggerMult", 0.5f);
                            Emit(SimEventType.BossStaggered, e.pos, b.staggerDamage, id: a.id, uid: e.uid);
                        }
                        Emit(SimEventType.BossAbility, e.pos, dmg, id: a.id, uid: e.uid, id2: a.type, flags: staggered ? 1 : 0);
                        DamageCitadel(dmg, e, a.id);
                        EndBossAbility(e);
                    }
                    break;

                default:
                    EndBossAbility(e);
                    break;
            }
        }

        private void EndBossAbility(Enemy e)
        {
            e.boss.activeAbility = -1;
            e.boss.abilityStage = 0;
            e.boss.stageTimer = 0f;
        }

        private void DoSummon(Enemy boss, BossAbilityDef a)
        {
            if (a.summons == null) return;
            int phaseBonus = boss.boss.phase >= 2 ? (int)BossP(a, "phase2Extra", 0f) : 0;
            foreach (var s in a.summons)
            {
                var def = C.Enemy(s.enemy);
                if (def == null) continue;
                int count = s.count + phaseBonus;
                for (int i = 0; i < count; i++)
                {
                    if (AliveCount >= C.Tuning.arena.maxAlive) return;
                    int units = Math.Max(1, def.swarmCount);
                    var unit = string.IsNullOrEmpty(def.unitId) ? def : (C.Enemy(def.unitId) ?? def);
                    if (s.at == "edge")
                    {
                        int route = _combatRng.Range(0, Routes.routes.Count);
                        for (int u = 0; u < units; u++)
                            SpawnEnemy(unit, route, (u - (units - 1) * 0.5f) * 0.32f, s.elite, null, true, boss.uid, u * 0.18f);
                    }
                    else
                    {
                        Vec2 at = SafeSummonPoint(boss.pos, 1.6f);
                        for (int u = 0; u < units; u++)
                            SpawnEnemy(unit, 0, 0f, s.elite, SafeSummonPoint(at, 0.5f), true, boss.uid);
                    }
                }
            }
        }

        private void OnBossKilled(Enemy boss)
        {
            if (!RunStats.bossesDefeated.Contains(boss.typeId)) RunStats.bossesDefeated.Add(boss.typeId);
            Emit(SimEventType.BossDefeated, boss.pos, id: boss.typeId, uid: boss.uid, flags: SimEvent.FlagBoss);
            if (ActiveBoss == boss) ActiveBoss = null;
            // the boss's summoned troops scatter (they still count as defeated and pay out)
            for (int i = 0; i < _enemies.Count; i++)
            {
                var o = _enemies[i];
                if (o.alive && o.summoned && o.summonerUid == boss.uid)
                {
                    Emit(SimEventType.EnemyFled, o.pos, id: o.typeId, uid: o.uid);
                    Kill(o, "scatter", true);
                }
            }
        }
    }
}
