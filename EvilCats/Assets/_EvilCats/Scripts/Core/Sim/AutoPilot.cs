using System;
using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Core;

namespace EvilCats.Sim
{
    /// <summary>
    /// A simple rule-based player used by balance simulations and automated tests. It only
    /// uses the same public commands a human has (buy upgrades, pick perks, cast abilities,
    /// set target priority), so simulated results reflect the real rules. It is NOT meant to
    /// play optimally, and simulation results do not prove the game is fun.
    /// </summary>
    public sealed class AutoPilot
    {
        public string Name = "default";
        /// <summary>Relative spending weights per upgrade id (higher = buys more of it).</summary>
        public Dictionary<string, float> UpgradeWeights = new Dictionary<string, float>
        {
            { "damage", 1.0f }, { "attack_speed", 0.8f }, { "max_health", 0.55f }, { "regen", 0.3f }, { "crit", 0.35f }, { "collection", 0.45f },
        };
        /// <summary>Perk family preference (build identity). Missing families score 0.5.</summary>
        public Dictionary<string, float> FamilyWeights = new Dictionary<string, float>();
        public TargetPriority Priority = TargetPriority.Nearest;
        public bool UseAbilities = true;
        public bool BuyUpgrades = true;
        public bool SmartPriority = true;   // switch to Ranged Threat when archers/priests pile up
        public float SkillReaction = 1.0f;  // 1 = reacts to telegraphs, 0 = ignores them
        /// <summary>Casts Nine-Lives Ward whenever it is ready and enemies are attacking (a more active
        /// player). Off by default: the balance baseline assumes a player who saves it for emergencies.</summary>
        public bool WardOnCooldown;
        private readonly Rng _rng;

        public AutoPilot(ulong seed = 1) { _rng = new Rng(seed, 1234u); }

        public static AutoPilot Build(string build, ulong seed = 1)
        {
            var a = new AutoPilot(seed) { Name = build };
            switch (build)
            {
                case "chain_control":
                    a.FamilyWeights["arc"] = 1.0f; a.FamilyWeights["frost"] = 0.9f; a.FamilyWeights["gravity"] = 0.6f;
                    break;
                case "fire_gravity":
                    a.FamilyWeights["ember"] = 1.0f; a.FamilyWeights["gravity"] = 0.9f; a.FamilyWeights["arc"] = 0.5f;
                    break;
                case "ballista_ward":
                    a.FamilyWeights["bone"] = 1.0f; a.FamilyWeights["ward"] = 0.9f; a.FamilyWeights["arc"] = 0.5f;
                    a.Priority = TargetPriority.Strongest;
                    break;
                case "passive":
                    a.UseAbilities = false; a.BuyUpgrades = false; a.SmartPriority = false; a.SkillReaction = 0f;
                    break;
            }
            return a;
        }

        public void Step(Battle b)
        {
            switch (b.Phase)
            {
                case BattlePhase.AwaitingPerk: ChoosePerk(b); return;
                case BattlePhase.AwaitingModuleChoice:
                    b.ChooseModuleForSlot(b.ModuleChoices.Count > 0 ? PickModule(b) : null);
                    return;
                case BattlePhase.AwaitingRevive: b.DeclineRevive(); return;
                case BattlePhase.Running: break;
                default: return;
            }
            if (b.TickCount % 6 != 0) return;   // think 5 times per second like a quick human
            if (SmartPriority) UpdatePriority(b);
            else if (b.Priority != Priority) b.SetPriority(Priority);
            if (BuyUpgrades) Spend(b);
            if (UseAbilities) Abilities(b);
        }

        private string PickModule(Battle b)
        {
            string best = b.ModuleChoices[0];
            float bestScore = -1f;
            foreach (var m in b.ModuleChoices)
            {
                var def = b.C.Module(m);
                float s = def != null && FamilyWeights.TryGetValue(def.family, out var w) ? w : 0.5f;
                if (s > bestScore) { bestScore = s; best = m; }
            }
            return best;
        }

        private void ChoosePerk(Battle b)
        {
            var offer = b.CurrentOffer;
            int best = 0;
            float bestScore = float.MinValue;
            for (int i = 0; i < offer.choices.Count; i++)
            {
                var ch = offer.choices[i];
                float s;
                if (ch.perkId == null) s = ch.fallbackId == "stormheart_mend" && b.Hp < b.MaxHp * 0.5f ? 0.9f : 0.2f;
                else
                {
                    var p = b.C.Perk(ch.perkId);
                    s = FamilyWeights.TryGetValue(p.family, out var w) ? w : 0.5f;
                    if (p.rarity == "rare") s += 0.1f;
                    if (p.tradeoff) s -= 0.05f;
                    s += _rng.Range(0f, 0.15f);
                }
                if (s > bestScore) { bestScore = s; best = i; }
            }
            b.ChoosePerk(best);
        }

        private void UpdatePriority(Battle b)
        {
            var boss = b.ActiveBoss;
            TargetPriority want = Priority;
            int threats = 0;
            foreach (var e in b.Enemies) if (e.alive && Targeting.IsThreat(e) && !e.isBoss) threats++;
            if (threats >= 2) want = TargetPriority.RangedThreat;
            else if (boss != null && boss.alive && Priority != TargetPriority.RangedThreat) want = TargetPriority.Strongest;
            if (b.Priority != want) b.SetPriority(want);
        }

        private void Spend(Battle b)
        {
            // Buy the affordable upgrade with the best weight / cost ratio; keep a small reserve late.
            string pick = null;
            float bestRatio = 0f;
            foreach (var up in b.C.Upgrades)
            {
                if (!UpgradeWeights.TryGetValue(up.id, out var w) || w <= 0f || b.UpgradeMaxed(up.id)) continue;
                int cost = b.UpgradeCost(up.id);
                if (cost > b.Sparks) continue;
                float urgency = 1f;
                if ((up.id == "max_health" || up.id == "regen") && b.Hp < b.MaxHp * 0.6f) urgency = 2f;
                if (up.id == "collection" && b.Wave > 12) urgency = 0.3f;
                float ratio = w * urgency / (1f + b.UpgradeLevel(up.id) * 0.35f);
                if (ratio > bestRatio) { bestRatio = ratio; pick = up.id; }
            }
            if (pick != null) b.BuyUpgrade(pick);
        }

        private void Abilities(Battle b)
        {
            // Nine-Lives Ward: save it for telegraphed heavy attacks, or use when health is dropping.
            if (b.WardCooldown <= 0f)
            {
                bool bigHitSoon = SkillReaction > 0f && HeavyAttackImminent(b);
                bool lowAndPressured = b.Hp < b.MaxHp * 0.45f && b.AliveCount > 3;
                bool noBoss = b.ActiveBoss == null;
                bool active = WardOnCooldown && b.AliveCount >= 6 && b.Hp < b.MaxHp * 0.95f;
                if (bigHitSoon || active || (lowAndPressured && (noBoss || b.Hp < b.MaxHp * 0.25f))) b.CastWard();
            }
            // Arc Storm: hit the best cluster, preferring powder rats that have lit their fuse.
            if (b.StormCooldown <= 0f)
            {
                Vec2? target = null;
                foreach (var e in b.Enemies)
                    if (e.alive && e.typeId == "powder_rat" && (e.powder == PowderState.Fuse || e.powder == PowderState.Charge)) { target = e.pos; break; }
                if (target == null)
                {
                    var t = b.DefaultStormTarget();
                    if (t.HasValue && b.StormTargetsAt(t.Value) >= 3) target = t;
                }
                if (target.HasValue) b.CastArcStorm(target);
            }
        }

        private static bool HeavyAttackImminent(Battle b)
        {
            var boss = b.ActiveBoss;
            if (boss == null || !boss.alive || boss.boss == null || boss.boss.activeAbility < 0) return false;
            var a = boss.bossDef.abilities[boss.boss.activeAbility];
            var st = boss.boss;
            switch (a.type)
            {
                case "charge": return st.abilityStage == 2 || (st.abilityStage == 1 && st.stageTimer < 0.8f);
                case "volley": return st.stageTimer < 1.0f;
                case "sector_barrage": return st.abilityStage == 2 || st.stageTimer < 0.5f;
            }
            return false;
        }

        /// <summary>Plays a whole run headlessly. Returns the result.</summary>
        public static RunResult Play(Battle b, AutoPilot pilot, int maxTicks = 30 * 60 * 40)
        {
            int guard = 0;
            while (!b.IsOver && guard++ < maxTicks)
            {
                pilot.Step(b);
                if (b.Phase == BattlePhase.Running) b.Tick();
                if (b.CheckpointPending) b.TakeCheckpoint();
            }
            if (!b.IsOver) b.Abandon();
            return b.BuildResult();
        }
    }
}
