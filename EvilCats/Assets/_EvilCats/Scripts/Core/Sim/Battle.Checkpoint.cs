using System;
using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Core;

namespace EvilCats.Sim
{
    public static class RunStatsExt
    {
        public static RunStats Clone(this RunStats s)
        {
            var c = new RunStats
            {
                kills = s.kills, eliteKills = s.eliteKills, bossKills = s.bossKills, wavesCleared = s.wavesCleared,
                burnsApplied = s.burnsApplied, freezes = s.freezes, pulls = s.pulls, powderInterrupts = s.powderInterrupts,
                barrierAbsorbed = s.barrierAbsorbed, healthDamageTaken = s.healthDamageTaken, healed = s.healed,
                maxChain = s.maxChain, stormUses = s.stormUses, wardUses = s.wardUses, upgradesBought = s.upgradesBought,
                perksTaken = s.perksTaken, minHealthFraction = s.minHealthFraction, timeSec = s.timeSec,
            };
            foreach (var kv in s.killsByType) c.killsByType[kv.Key] = kv.Value;
            foreach (var kv in s.damageTakenBySource) c.damageTakenBySource[kv.Key] = kv.Value;
            foreach (var kv in s.damageDealtBySource) c.damageDealtBySource[kv.Key] = kv.Value;
            c.bossesDefeated.AddRange(s.bossesDefeated);
            return c;
        }

        public static void CopyInto(this RunStats s, RunStats target)
        {
            var c = s.Clone();
            target.kills = c.kills; target.eliteKills = c.eliteKills; target.bossKills = c.bossKills; target.wavesCleared = c.wavesCleared;
            target.burnsApplied = c.burnsApplied; target.freezes = c.freezes; target.pulls = c.pulls; target.powderInterrupts = c.powderInterrupts;
            target.barrierAbsorbed = c.barrierAbsorbed; target.healthDamageTaken = c.healthDamageTaken; target.healed = c.healed;
            target.maxChain = c.maxChain; target.stormUses = c.stormUses; target.wardUses = c.wardUses; target.upgradesBought = c.upgradesBought;
            target.perksTaken = c.perksTaken; target.minHealthFraction = c.minHealthFraction; target.timeSec = c.timeSec;
            target.killsByType.Clear(); foreach (var kv in c.killsByType) target.killsByType[kv.Key] = kv.Value;
            target.damageTakenBySource.Clear(); foreach (var kv in c.damageTakenBySource) target.damageTakenBySource[kv.Key] = kv.Value;
            target.damageDealtBySource.Clear(); foreach (var kv in c.damageDealtBySource) target.damageDealtBySource[kv.Key] = kv.Value;
            target.bossesDefeated.Clear(); target.bossesDefeated.AddRange(c.bossesDefeated);
        }
    }

    public sealed partial class Battle
    {
        /// <summary>
        /// Snapshot taken between waves. On resume the run restarts at the beginning of the
        /// next wave with identical loadout, perks, currencies, health, cooldowns and RNG state.
        /// Progress inside an unfinished wave is intentionally not saved (the UI explains this).
        /// </summary>
        public RunCheckpoint TakeCheckpoint()
        {
            CheckpointPending = false;
            var cp = new RunCheckpoint
            {
                runId = RunId,
                mode = Spec.mode,
                missionId = Spec.missionId,
                seed = Setup.seed,
                nextWave = _nextWave,
                citadelHp = Hp,
                sparks = _sparks,
                xp = _xp,
                level = Level,
                combatRng = _combatRng.State,
                perkRng = _perkRng.State,
                reviveUsed = _reviveUsed,
                lastThreadUsed = _lastThreadUsed,
                priority = Priority,
                stormCooldown = StormCooldown,
                wardCooldown = WardCooldown,
                elapsed = Time,
                stats = RunStats.Clone(),
                routeLayout = Spec.routeLayout,
            };
            foreach (var kv in _perkStacks) cp.perks[kv.Key] = kv.Value;
            foreach (var kv in _upgradeLevels) cp.upgrades[kv.Key] = kv.Value;
            foreach (var kv in Loadout) cp.loadout[kv.Key] = kv.Value;
            cp.unlockedSlots.AddRange(UnlockedSlots);
            return cp;
        }

        private void RestoreCheckpoint(RunCheckpoint cp)
        {
            _upgradeLevels.Clear();
            foreach (var kv in cp.upgrades) _upgradeLevels[kv.Key] = kv.Value;
            _perkStacks.Clear();
            foreach (var kv in cp.perks) _perkStacks[kv.Key] = kv.Value;
            Loadout.Clear();
            foreach (var kv in cp.loadout) if (!string.IsNullOrEmpty(kv.Value)) Loadout[kv.Key] = kv.Value;
            UnlockedSlots.Clear();
            UnlockedSlots.AddRange(cp.unlockedSlots);
            RebuildStats();
            Hp = MathX.Clamp(cp.citadelHp, 1f, MaxHp);
            _sparks = cp.sparks;
            _xp = cp.xp;
            Level = cp.level;
            _combatRng.Restore(cp.combatRng);
            _perkRng.Restore(cp.perkRng);
            _reviveUsed = cp.reviveUsed;
            _lastThreadUsed = cp.lastThreadUsed;
            Priority = cp.priority;
            StormCooldown = cp.stormCooldown;
            WardCooldown = cp.wardCooldown;
            Time = cp.elapsed;
            if (cp.stats != null) cp.stats.CopyInto(RunStats);
            _nextWave = Math.Max(1, cp.nextWave);
            Wave = _nextWave - 1;
            _waveStartDelay = C.Tuning.waves.firstWaveDelay;
        }

        public RunResult BuildResult()
        {
            var r = new RunResult
            {
                runId = RunId,
                mode = Spec.mode,
                missionId = Spec.missionId,
                victory = Phase == BattlePhase.Victory,
                abandoned = _abandoned,
                wavesCleared = RunStats.wavesCleared,
                totalWaves = Spec.totalWaves,
                levelReached = Level,
                healthFraction = MaxHp > 0f ? Math.Max(0f, Hp / MaxHp) : 0f,
                stats = RunStats.Clone(),
                seed = Setup.seed,
            };
            r.principalDamageSource = PrincipalDamageSource(out r.principalDamageShare);
            foreach (var kv in _perkStacks)
                for (int i = 0; i < kv.Value; i++) r.perks.Add(kv.Key);
            foreach (var kv in Loadout) r.loadout[kv.Key] = kv.Value;
            r.unlockedSlots.AddRange(UnlockedSlots);
            r.score = ComputeScore(r);
            return r;
        }

        public static long ComputeScore(RunResult r)
        {
            long s = r.wavesCleared * 1000L + r.stats.kills * 5L;
            if (r.victory) s += 5000L;
            s += (long)(r.healthFraction * 1000f);
            return s;
        }
    }
}
