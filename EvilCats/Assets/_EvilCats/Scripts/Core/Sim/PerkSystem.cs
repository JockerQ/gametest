using System;
using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Core;

namespace EvilCats.Sim
{
    /// <summary>Everything perk eligibility depends on (so it can be unit-tested without a battle).</summary>
    public sealed class PerkContext
    {
        public HashSet<string> equippedModules = new HashSet<string>();
        public Dictionary<string, int> stacks = new Dictionary<string, int>();
        public int heroChainTargets;

        public int Stack(string id) => stacks.TryGetValue(id, out var n) ? n : 0;
    }

    public static class PerkSystem
    {
        public static readonly Dictionary<string, string> FamilyModule = new Dictionary<string, string>
        {
            { "ember", "ember_maw" }, { "frost", "frost_whisker" }, { "bone", "bone_ballista" },
            { "ward", "ward_lantern" }, { "gravity", "gravity_paw" },
        };

        /// <summary>
        /// A perk is offered only if it can matter right now:
        ///  • Arc perks are always relevant (Arc Light Cat always attacks); other families need
        ///    their module equipped ("exclude irrelevant module perks").
        ///  • All requiresModules equipped; at least one of requiresAnyModule/requiresAnyPerk.
        ///  • Condition "chain": some Arc chain source exists; "slow": some slow source exists.
        ///  • Not already at its stack cap.
        /// </summary>
        public static bool IsEligible(PerkDef p, PerkContext ctx, out string reason)
        {
            reason = null;
            if (ctx.Stack(p.id) >= Math.Max(1, p.maxStacks)) { reason = "max_stacks"; return false; }
            if (p.family != "arc" && FamilyModule.TryGetValue(p.family, out var mod) && !ctx.equippedModules.Contains(mod))
            {
                reason = "module_missing:" + mod;
                return false;
            }
            foreach (var m in p.requiresModules)
                if (!ctx.equippedModules.Contains(m)) { reason = "module_missing:" + m; return false; }
            if (p.requiresAnyModule.Count > 0 || p.requiresAnyPerk.Count > 0)
            {
                bool any = false;
                foreach (var m in p.requiresAnyModule) if (ctx.equippedModules.Contains(m)) any = true;
                foreach (var q in p.requiresAnyPerk) if (ctx.Stack(q) > 0) any = true;
                if (!any) { reason = "requirement"; return false; }
            }
            switch (p.requiresCondition)
            {
                case null:
                case "":
                    break;
                case "chain":
                    if (ctx.heroChainTargets <= 0 && !ctx.equippedModules.Contains("arc_coil") && ctx.Stack("arc_forked_bolt") <= 0)
                    { reason = "no_chain"; return false; }
                    break;
                case "slow":
                    if (!ctx.equippedModules.Contains("frost_whisker") && ctx.Stack("gravity_event_horizon") <= 0)
                    { reason = "no_slow"; return false; }
                    break;
                default:
                    reason = "unknown_condition";
                    return false;
            }
            return true;
        }

        public static float RarityWeight(GameContent c, string rarity)
        {
            var t = c.Tuning.perkOffer;
            switch (rarity)
            {
                case "rare": return t.rareWeight;
                case "epic": return t.epicWeight;
                default: return t.commonWeight;
            }
        }

        /// <summary>Three distinct choices; fallbacks (Spark Cache / Stormheart Mend) fill gaps so a
        /// level-up is never wasted and no offer contains duplicates.</summary>
        public static PerkOffer Generate(GameContent c, PerkContext ctx, Rng rng, int level)
        {
            var offer = new PerkOffer { level = level };
            int count = Math.Max(1, c.Tuning.perkOffer.choices);
            var pool = new List<PerkDef>();
            var weights = new List<float>();
            foreach (var p in c.Perks)
            {
                if (!IsEligible(p, ctx, out _)) continue;
                pool.Add(p);
                weights.Add(RarityWeight(c, p.rarity));
            }
            while (offer.choices.Count < count && pool.Count > 0)
            {
                int idx = rng.WeightedIndex(weights);
                if (idx < 0) break;
                var p = pool[idx];
                offer.choices.Add(new PerkChoice { perkId = p.id, currentStacks = ctx.Stack(p.id), maxStacks = p.maxStacks });
                pool.RemoveAt(idx);
                weights.RemoveAt(idx);
            }
            int f = 0;
            while (offer.choices.Count < count && f < c.Fallbacks.Count)
            {
                offer.choices.Add(new PerkChoice { fallbackId = c.Fallbacks[f].id });
                f++;
            }
            return offer;
        }
    }

    public sealed partial class Battle
    {
        public static float XpRequirement(GameContent c, int level)
        {
            var x = c.Tuning.xp;
            return x.a + x.b * level + x.c * level * level;
        }

        private float XpForLevel(int level) => XpRequirement(C, level);

        private void AddXp(float amount)
        {
            if (amount <= 0f || IsOver) return;
            _xp += amount;
            while (_xp >= XpForLevel(Level))
            {
                _xp -= XpForLevel(Level);
                Level++;
                _pendingLevels++;
                Emit(SimEventType.LevelUp, value: Level);
            }
            if (_pendingLevels > 0 && CurrentOffer == null && Phase == BattlePhase.Running) OfferNextPerk();
        }

        public PerkContext BuildPerkContext()
        {
            var ctx = new PerkContext { heroChainTargets = Stats.hero.chainTargets };
            foreach (var kv in Loadout) if (!string.IsNullOrEmpty(kv.Value)) ctx.equippedModules.Add(kv.Value);
            foreach (var kv in _perkStacks) ctx.stacks[kv.Key] = kv.Value;
            return ctx;
        }

        private void OfferNextPerk()
        {
            if (_pendingLevels <= 0 || IsOver) return;
            _pendingLevels--;
            CurrentOffer = PerkSystem.Generate(C, BuildPerkContext(), _perkRng, Level);
            Phase = BattlePhase.AwaitingPerk;
            Emit(SimEventType.PerkOffered, value: Level);
        }

        public bool ChoosePerk(int index)
        {
            if (Phase != BattlePhase.AwaitingPerk || CurrentOffer == null) return false;
            if (index < 0 || index >= CurrentOffer.choices.Count) return false;
            var choice = CurrentOffer.choices[index];
            if (choice.perkId != null)
            {
                var def = C.Perk(choice.perkId);
                if (def == null) return false;
                float oldMax = MaxHp;
                _perkStacks[choice.perkId] = PerkStack(choice.perkId) + 1;
                RebuildStats();
                ApplyMaxHealthChange(oldMax);
                RunStats.perksTaken++;
                Emit(SimEventType.PerkChosen, id: choice.perkId, value: PerkStack(choice.perkId));
            }
            else
            {
                ApplyFallback(choice.fallbackId);
                Emit(SimEventType.PerkChosen, id: choice.fallbackId, value: 0);
            }
            CurrentOffer = null;
            Phase = BattlePhase.Running;
            ContinueAfterDecision();
            return true;
        }

        private void ApplyFallback(string id)
        {
            foreach (var f in C.Fallbacks)
            {
                if (f.id != id) continue;
                if (f.kind == "sparks") _sparks += f.value * (1f + 0.25f * Level);
                else if (f.kind == "heal") Hp = Math.Min(MaxHp, Hp + MaxHp * f.value);
                else if (f.kind == "barrier") AddBarrier(MaxHp * f.value, 8f, "stormheart_shield");
            }
        }
    }
}
