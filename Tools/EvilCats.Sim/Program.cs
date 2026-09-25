using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.Linq;
using System.Text;
using EvilCats.Content;
using EvilCats.Core;
using EvilCats.Meta;
using EvilCats.Sim;
using EvilCats.Tests;

namespace EvilCats.SimTool
{
    /// <summary>
    /// Evil Cats headless simulator. Usage:
    ///   dotnet run -c Release -- mission m06 --build chain_control --seed 3 --perm mid
    ///   dotnet run -c Release -- sweep --seeds 6
    ///   dotnet run -c Release -- campaign --build fire_gravity --seeds 3
    ///   dotnet run -c Release -- routes
    ///   dotnet run -c Release -- stress
    /// Results are simulations with a rule-based bot. They measure numbers, not fun.
    /// </summary>
    public static class Program
    {
        static GameContent C;

        public static int Main(string[] args)
        {
            CultureInfo.DefaultThreadCurrentCulture = CultureInfo.InvariantCulture;
            C = TestContent.Load();
            var rep = ContentValidator.Validate(C);
            if (!rep.Ok) { Console.WriteLine(rep); return 1; }
            string cmd = args.Length > 0 ? args[0] : "sweep";
            var opt = ParseOpts(args);
            switch (cmd)
            {
                case "mission": RunMission(args.Length > 1 ? args[1] : "m01", opt); break;
                case "sweep": Sweep(opt); break;
                case "campaign": Campaign(opt); break;
                case "routes": Routes(opt); break;
                case "stress": Stress(opt); break;
                case "speed": SpeedInvariance(opt); break;
                case "calibrate": Calibrate(opt); break;
                case "probe": Probe(opt); break;
                case "calibrate2": Calibrate2(opt); break;
                case "trace": Trace(opt); break;
                default: Console.WriteLine("unknown command " + cmd); return 1;
            }
            return 0;
        }

        static Dictionary<string, string> ParseOpts(string[] args)
        {
            var d = new Dictionary<string, string>();
            for (int i = 0; i < args.Length; i++)
                if (args[i].StartsWith("--") && i + 1 < args.Length) { d[args[i].Substring(2)] = args[i + 1]; i++; }
            return d;
        }

        static string Opt(Dictionary<string, string> o, string k, string def) => o.TryGetValue(k, out var v) ? v : def;

        // ---- permanent progression presets (what a typical player owns when reaching a mission) ----
        public static SaveData ProfileFor(string preset, string build, int missionIndex)
        {
            var d = SaveManager.NewProfile(DateTime.UtcNow);
            d.modulesUnlocked = new List<string> { "arc_coil", "ember_maw" };
            if (missionIndex > 1) d.modulesUnlocked.Add("frost_whisker");
            if (missionIndex > 3) d.modulesUnlocked.Add("bone_ballista");
            if (missionIndex > 5) d.modulesUnlocked.Add("ward_lantern");
            if (missionIndex > 7) d.modulesUnlocked.Add("gravity_paw");
            d.slotsUnlocked = missionIndex <= 1 ? new List<string> { "middle" } : missionIndex == 2 ? new List<string> { "middle", "crown" } : new List<string> { "crown", "middle", "base" };
            int lv(double perMission) => (int)Math.Min(5, Math.Floor(perMission * (missionIndex - 1)));
            if (preset != "none")
            {
                double k = preset == "low" ? 0.25 : preset == "high" ? 0.6 : 0.42;
                foreach (var n in new[] { "pm_arc_power", "pm_walls", "pm_station_power", "pm_moon_gold" }) d.nodes[n] = lv(k);
                foreach (var n in new[] { "pm_mend", "pm_station_speed", "pm_start_sparks" }) d.nodes[n] = lv(k * 0.8);
                foreach (var n in new[] { "pm_arc_storm", "pm_ward", "pm_xp" }) d.nodes[n] = Math.Min(3, lv(k * 0.45));
                if (missionIndex >= 6 && preset != "low") d.nodes["pm_arc_chain"] = 1;
                foreach (var m in d.modulesUnlocked) d.moduleTiers[m] = Math.Max(1, Math.Min(5, 1 + lv(k * 0.7)));
            }
            d.loadout = LoadoutFor(build, d);
            return d;
        }

        public static Dictionary<string, string> LoadoutFor(string build, SaveData d)
        {
            string[] want = build switch
            {
                "chain_control" => new[] { "arc_coil", "frost_whisker", "gravity_paw", "ember_maw", "bone_ballista" },
                "fire_gravity" => new[] { "ember_maw", "gravity_paw", "arc_coil", "frost_whisker", "bone_ballista" },
                "ballista_ward" => new[] { "bone_ballista", "ward_lantern", "arc_coil", "frost_whisker", "ember_maw" },
                _ => new[] { "arc_coil", "ember_maw", "frost_whisker", "bone_ballista", "ward_lantern" },
            };
            var mods = want.Where(m => d.modulesUnlocked.Contains(m)).ToList();
            var slots = new List<string>();
            // pairs that synergise go in adjacent slots: first two in crown+middle, third in base
            foreach (var s in new[] { "middle", "crown", "base" }) if (d.slotsUnlocked.Contains(s)) slots.Add(s);
            var lo = new Dictionary<string, string>();
            for (int i = 0; i < slots.Count && i < mods.Count; i++) lo[slots[i]] = mods[i];
            return lo;
        }

        static (RunResult r, Battle b, long ticks, double ms) Play(string missionId, string build, ulong seed, string perm, string layout = null)
        {
            var m = C.Mission(missionId);
            var save = ProfileFor(perm, build, m.index);
            var meta = new GameMeta(C, save);
            var setup = meta.CreateCampaignSetup(missionId, seed, false);
            setup.emitEvents = false;
            GameContent content = C;
            if (layout != null) { content = TestContent.Fresh(); content.Mission(missionId).routeLayout = layout; }
            var b = new Battle(content, setup);
            var pilot = AutoPilot.Build(build, seed);
            var sw = Stopwatch.StartNew();
            var r = AutoPilot.Play(b, pilot);
            sw.Stop();
            return (r, b, b.TickCount, sw.Elapsed.TotalMilliseconds);
        }

        static void RunMission(string id, Dictionary<string, string> o)
        {
            string build = Opt(o, "build", "default");
            ulong seed = ulong.Parse(Opt(o, "seed", "1"));
            string perm = Opt(o, "perm", "mid");
            var (r, b, ticks, ms) = Play(id, build, seed, perm);
            Console.WriteLine($"mission {id} build={build} seed={seed} perm={perm}");
            Console.WriteLine($"  result: {(r.victory ? "VICTORY" : "DEFEAT")} waves {r.wavesCleared}/{r.totalWaves}  time {TextFormat.Duration(r.stats.timeSec)}  level {r.levelReached} ({r.stats.perksTaken} perks)");
            Console.WriteLine($"  kills {r.stats.kills} (elite {r.stats.eliteKills})  hp {r.healthFraction:P0} min {r.stats.minHealthFraction:P0}  sparks left {b.Sparks}  upgrades {r.stats.upgradesBought}");
            Console.WriteLine($"  storms {r.stats.stormUses} wards {r.stats.wardUses} maxChain {r.stats.maxChain} freezes {r.stats.freezes} burns {r.stats.burnsApplied} pulls {r.stats.pulls} barrier {r.stats.barrierAbsorbed:0}");
            Console.WriteLine($"  principal damage: {r.principalDamageSource} ({r.principalDamageShare:P0})  sim {ticks} ticks in {ms:0} ms");
            Console.WriteLine("  damage taken: " + string.Join(", ", r.stats.damageTakenBySource.OrderByDescending(kv => kv.Value).Take(6).Select(kv => $"{kv.Key} {kv.Value:0}")));
            Console.WriteLine("  damage dealt: " + string.Join(", ", r.stats.damageDealtBySource.OrderByDescending(kv => kv.Value).Take(8).Select(kv => $"{kv.Key} {kv.Value:0}")));
            Console.WriteLine("  perks: " + string.Join(", ", r.perks) + "   upgrades: " + string.Join(", ", b.UpgradeLevels.Select(kv => kv.Key + ":" + kv.Value)));
        }

        static void Sweep(Dictionary<string, string> o)
        {
            int seeds = int.Parse(Opt(o, "seeds", "4"));
            string perm = Opt(o, "perm", "mid");
            string only = Opt(o, "missions", "");
            var builds = Opt(o, "builds", "default,chain_control,fire_gravity,ballista_ward").Split(',');
            Console.WriteLine($"Sweep: perm={perm}, seeds={seeds}  (win% | avg waves | avg time | avg perks | min hp)");
            Console.Write("mission".PadRight(9));
            foreach (var bd in builds) Console.Write(bd.PadRight(34));
            Console.WriteLine();
            foreach (var m in C.Missions)
            {
                if (only != "" && !only.Split(',').Contains(m.id)) continue;
                Console.Write(m.id.PadRight(9));
                foreach (var build in builds)
                {
                    int wins = 0; double waves = 0, time = 0, perks = 0, minhp = 0;
                    for (int s = 1; s <= seeds; s++)
                    {
                        var (r, _, _, _) = Play(m.id, build, (ulong)(s * 7919), perm);
                        if (r.victory) wins++;
                        waves += r.wavesCleared; time += r.stats.timeSec; perks += r.stats.perksTaken; minhp += r.stats.minHealthFraction;
                    }
                    Console.Write($"{100 * wins / seeds,3}% {waves / seeds,5:0.0}w {TextFormat.Duration((float)(time / seeds)),5} {perks / seeds,4:0.0}p {minhp / seeds,4:P0}".PadRight(34));
                }
                Console.WriteLine();
            }
        }

        /// <summary>Plays the campaign from a fresh save with a spending policy, retrying on defeat.</summary>
        static void Campaign(Dictionary<string, string> o)
        {
            string build = Opt(o, "build", "default");
            int seeds = int.Parse(Opt(o, "seeds", "2"));
            for (int s = 1; s <= seeds; s++)
            {
                var now = new DateTime(2026, 1, 1, 12, 0, 0, DateTimeKind.Utc);
                var save = SaveManager.NewProfile(now);
                var meta = new GameMeta(C, save);
                int totalRuns = 0;
                double totalMinutes = 0;
                Console.WriteLine($"--- campaign build={build} seed={s} ---");
                foreach (var m in C.Missions)
                {
                    int attempts = 0;
                    RunResult r = null;
                    while (attempts < 12)
                    {
                        attempts++;
                        totalRuns++;
                        foreach (var id in new List<string>(meta.Data.modulesAvailable)) meta.UnlockModule(id, now);
                        meta.Data.loadout = LoadoutFor(build, meta.Data);
                        var setup = meta.CreateCampaignSetup(m.id, (ulong)(s * 1000 + totalRuns), false);
                        setup.emitEvents = false;
                        var b = new Battle(C, setup);
                        r = AutoPilot.Play(b, AutoPilot.Build(build, (ulong)totalRuns));
                        totalMinutes += r.stats.timeSec / 60.0;
                        var sum = meta.ApplyRunResult(r, now, now);
                        foreach (var a in C.Progression.achievements) meta.ClaimAchievement(a.id, now);
                        SpendPermanent(meta, build, now);
                        now = now.AddMinutes(10);
                        if (r.victory) break;
                    }
                    Console.WriteLine($"{m.id} attempts {attempts,2}  {(r.victory ? "WIN " : "LOSS")} waves {r.wavesCleared,2}/{r.totalWaves}  MG {meta.Data.moonGold,5}  shards {meta.Data.stormShards}  permLv {meta.TotalNodeLevels(),2}  tiers {string.Join("/", meta.Data.moduleTiers.Values)}  minHP {r.stats.minHealthFraction:P0}  t {TextFormat.Duration(r.stats.timeSec)}");
                    if (!r.victory) { Console.WriteLine("  stuck (grind wall) - stopping"); break; }
                }
                Console.WriteLine($"total runs {totalRuns}, total play {totalMinutes:0} min");
            }
        }

        static void SpendPermanent(GameMeta meta, string build, DateTime now)
        {
            // Cheapest-first across a sensible priority list (a typical player's behaviour).
            var order = new[] { "pm_arc_power", "pm_walls", "pm_station_power", "pm_mend", "pm_station_speed", "pm_start_sparks",
                "pm_moon_gold", "pm_arc_storm", "pm_ward", "pm_arc_chain", "pm_xp", "pm_ward_haste", "pm_arc_crit", "pm_synergy", "pm_offline" };
            for (int guard = 0; guard < 40; guard++)
            {
                string best = null; int bestCost = int.MaxValue;
                foreach (var n in order)
                    if (meta.CanBuyNode(n) == MetaResult.Ok && meta.NodeCost(n) < bestCost) { best = n; bestCost = meta.NodeCost(n); }
                // module tiers for equipped stations compete with nodes
                string tierPick = null; int tierCost = int.MaxValue;
                foreach (var kv in meta.Data.loadout)
                {
                    int c = meta.TierCost(kv.Value);
                    if (c < tierCost && c <= meta.Data.moonGold) { tierCost = c; tierPick = kv.Value; }
                }
                if (tierPick != null && tierCost < bestCost) { meta.UpgradeModuleTier(tierPick, now); continue; }
                if (best == null) break;
                meta.BuyNode(best, now);
            }
        }

        static void Routes(Dictionary<string, string> o)
        {
            int seeds = int.Parse(Opt(o, "seeds", "4"));
            foreach (var layout in new[] { "routes_3", "routes_5" })
            {
                Console.WriteLine($"== {layout}");
                foreach (var mid in new[] { "m02", "m05", "m08" })
                {
                    int wins = 0; double minhp = 0, time = 0, spread = 0, overlap = 0;
                    for (int s = 1; s <= seeds; s++)
                    {
                        var (r, b, _, _) = PlayWithMetrics(mid, (ulong)(s * 31), layout, out double angSpread, out double crowd);
                        if (r.victory) wins++;
                        minhp += r.stats.minHealthFraction; time += r.stats.timeSec; spread += angSpread; overlap += crowd;
                    }
                    Console.WriteLine($"  {mid}: win {100 * wins / seeds}%  minHP {minhp / seeds:P0}  time {TextFormat.Duration((float)(time / seeds))}  attack-angle coverage {spread / seeds:P0}  sprite crowding {overlap / seeds:0.00}");
                }
            }
        }

        /// <summary>Also measures how evenly attackers surround the citadel (coverage of 12 angular
        /// sectors) and how crowded enemies get (mean neighbours within 0.6m) - proxies for readability.</summary>
        static (RunResult, Battle, long, double) PlayWithMetrics(string mid, ulong seed, string layout, out double coverage, out double crowd)
        {
            var content = TestContent.Fresh();
            content.Mission(mid).routeLayout = layout;
            var m = content.Mission(mid);
            var save = ProfileFor("mid", "default", m.index);
            var meta = new GameMeta(content, save);
            var setup = meta.CreateCampaignSetup(mid, seed, false);
            setup.emitEvents = false;
            var b = new Battle(content, setup);
            var pilot = AutoPilot.Build("default", seed);
            var sectors = new int[12];
            long samples = 0; double crowdSum = 0;
            while (!b.IsOver && b.TickCount < 30 * 60 * 30)
            {
                pilot.Step(b);
                if (b.Phase == BattlePhase.Running) b.Tick();
                if (b.CheckpointPending) b.TakeCheckpoint();
                if (b.TickCount % 30 == 0)
                {
                    var alive = b.Enemies.Where(e => e.alive).ToList();
                    foreach (var e in alive)
                    {
                        if (e.state == MoveState.Holding)
                        {
                            float a = e.pos.Angle; if (a < 0) a += MathX.TwoPi;
                            sectors[(int)(a / MathX.TwoPi * 12) % 12]++;
                        }
                        int n = 0;
                        foreach (var x in alive) if (x != e && Vec2.SqrDistance(x.pos, e.pos) < 0.36f) n++;
                        crowdSum += n; samples++;
                    }
                }
            }
            int covered = sectors.Count(v => v > 0);
            coverage = covered / 12.0;
            crowd = samples > 0 ? crowdSum / samples : 0;
            return (b.BuildResult(), b, b.TickCount, 0);
        }

        static void Stress(Dictionary<string, string> o)
        {
            var content = TestContent.Fresh();
            content.Tuning.arena.maxAlive = 220;
            var save = ProfileFor("high", "default", 12);
            var meta = new GameMeta(content, save);
            var setup = meta.CreateCampaignSetup("m12", 5, false);
            var b = new Battle(content, setup);
            // Force a crowd: spawn waves of cheap enemies by running the endless-style budget.
            var spec = b.Spec;
            spec.budget = 150; spec.budgetGrowth = 1.0f; spec.healthScale = 40f;
            var pilot = AutoPilot.Build("default", 1);
            pilot.UseAbilities = false;
            var sw = new Stopwatch();
            long ticks = 0; double worst = 0; int maxAlive = 0, maxProj = 0;
            var events = new List<SimEvent>();
            while (!b.IsOver && ticks < 30 * 90)
            {
                pilot.Step(b);
                sw.Restart();
                if (b.Phase == BattlePhase.Running) b.Tick();
                sw.Stop();
                b.DrainEvents(events); events.Clear();
                ticks++;
                worst = Math.Max(worst, sw.Elapsed.TotalMilliseconds);
                maxAlive = Math.Max(maxAlive, b.AliveCount);
                maxProj = Math.Max(maxProj, b.Projectiles.Count);
            }
            Console.WriteLine($"stress: {ticks} ticks, peak alive {maxAlive}, peak projectiles {maxProj}, worst tick {worst:0.00} ms (desktop CPU, .NET 8; a phone is several times slower)");
        }

        /// <summary>
        /// Searches each mission's healthScale so the average lowest-health point of the four builds
        /// (with typical permanent progression) matches a target difficulty curve, then prints the values.
        /// </summary>
        static void Calibrate(Dictionary<string, string> o)
        {
            int seeds = int.Parse(Opt(o, "seeds", "3"));
            var builds = new[] { "default", "chain_control", "fire_gravity", "ballista_ward" };
            // target average lowest-health fraction for the bot per mission index (1..12)
            double[] target = { 0, 0.80, 0.66, 0.60, 0.56, 0.52, 0.48, 0.50, 0.46, 0.43, 0.41, 0.39, 0.34 };
            var work = TestContent.Fresh();
            var outLines = new List<string>();
            foreach (var m in work.Missions)
            {
                double lo = 0.3, hi = 12.0;
                double best = m.healthScale; double bestErr = 9;
                for (int it = 0; it < 11; it++)
                {
                    double mid = Math.Sqrt(lo * hi);
                    m.healthScale = (float)mid;
                    double hp = 0; int n = 0; double worstWin = 1;
                    foreach (var bd in builds)
                    {
                        int wins = 0;
                        for (int s = 1; s <= seeds; s++)
                        {
                            var r = PlayContent(work, m.id, bd, (ulong)(s * 104729));
                            hp += r.stats.minHealthFraction; if (r.victory) wins++; n++;
                        }
                        worstWin = Math.Min(worstWin, wins / (double)seeds);
                    }
                    hp /= n;
                    // pass = every build still wins >= 2/3 of runs AND average lowest health >= target
                    bool pass = worstWin >= 0.66 && hp >= target[m.index];
                    if (pass) { best = mid; bestErr = hp - target[m.index]; lo = mid; } else hi = mid;
                }
                // conservative: 5% safety margin, rounded DOWN to 0.05 (the sim is chaotic near the edge)
                m.healthScale = (float)(Math.Floor(best * 0.95 * 20) / 20);
                var per = new StringBuilder();
                foreach (var bd in builds)
                {
                    double hp = 0; int wins = 0;
                    for (int s = 1; s <= seeds; s++) { var r = PlayContent(work, m.id, bd, (ulong)(s * 104729)); hp += r.stats.minHealthFraction; if (r.victory) wins++; }
                    per.Append($" {bd}:{100 * wins / seeds}%/{hp / seeds:P0}");
                }
                Console.WriteLine($"{m.id}: healthScale {m.healthScale:0.00} (err {bestErr:0.00}) |{per}");
                outLines.Add($"{m.id}={m.healthScale.ToString(CultureInfo.InvariantCulture)}");
            }
            System.IO.File.WriteAllLines("calibration.txt", outLines);
        }

        /// <summary>
        /// Two-stage calibration. Stage 1: enemy health scale -> target mission duration (health
        /// mostly controls how long waves take). Stage 2: enemy damage scale -> target difficulty,
        /// requiring every build to keep winning >= 2/3 of runs (damage mostly controls danger).
        /// </summary>
        static void Calibrate2(Dictionary<string, string> o)
        {
            int seeds = int.Parse(Opt(o, "seeds", "3"));
            var builds = new[] { "default", "chain_control", "fire_gravity", "ballista_ward" };
            double[] targetHp = { 0, 0.80, 0.66, 0.60, 0.56, 0.52, 0.48, 0.50, 0.46, 0.43, 0.41, 0.39, 0.34 };
            double[] targetMin = { 0, 3.6, 8.0, 8.2, 8.4, 8.6, 9.0, 8.6, 8.8, 9.3, 9.0, 9.0, 9.8 };
            var work = TestContent.Fresh();
            var outLines = new List<string>();
            foreach (var m in work.Missions)
            {
                // ---- stage 1: health for duration (at neutral damage) ----
                m.damageScale = 1f;
                double lo = 0.3, hi = 10;
                for (int it = 0; it < 10; it++)
                {
                    double mid = Math.Sqrt(lo * hi);
                    m.healthScale = (float)mid;
                    double minutes = 0; int n = 0;
                    foreach (var bd in builds)
                        for (int s = 1; s <= seeds; s++) { var r = PlayContent(work, m.id, bd, (ulong)(s * 104729)); minutes += r.stats.timeSec / 60.0; n++; }
                    minutes /= n;
                    if (minutes < targetMin[m.index]) lo = mid; else hi = mid;
                }
                m.healthScale = (float)(Math.Round(Math.Sqrt(lo * hi) * 20) / 20);
                // ---- stage 2: damage for difficulty, kept in a sane band [0.6, 3.0]; if even 3.0 is
                // too easy, raise health (longer mission) rather than make single hits brutal ----
                double bestD = 0.6;
                for (int round = 0; round < 5; round++)
                {
                    double dlo = 0.6, dhi = 3.0; bestD = 0.6; bool anyPass = false;
                    for (int it = 0; it < 9; it++)
                    {
                        double mid = Math.Sqrt(dlo * dhi);
                        m.damageScale = (float)mid;
                        double hp = 0; int n = 0; double worstWin = 1;
                        foreach (var bd in builds)
                        {
                            int wins = 0;
                            for (int s = 1; s <= seeds; s++) { var r = PlayContent(work, m.id, bd, (ulong)(s * 104729)); hp += r.stats.minHealthFraction; if (r.victory) wins++; n++; }
                            worstWin = Math.Min(worstWin, wins / (double)seeds);
                        }
                        hp /= n;
                        if (worstWin >= 0.66 && hp >= targetHp[m.index]) { bestD = mid; dlo = mid; anyPass = true; } else dhi = mid;
                    }
                    if (!anyPass) { m.healthScale = (float)(m.healthScale * 0.9); continue; }       // too hard even at 0.6
                    if (bestD > 2.9) { m.healthScale = (float)(m.healthScale * 1.12); continue; }  // too easy even at 3.0
                    break;
                }
                m.damageScale = (float)(Math.Floor(bestD * 0.95 * 20) / 20);
                var per = new StringBuilder();
                double avgMin = 0;
                foreach (var bd in builds)
                {
                    double hp = 0, mins = 0; int wins = 0;
                    for (int s = 1; s <= seeds; s++) { var r = PlayContent(work, m.id, bd, (ulong)(s * 104729)); hp += r.stats.minHealthFraction; mins += r.stats.timeSec / 60.0; if (r.victory) wins++; }
                    avgMin += mins / seeds;
                    per.Append($" {bd}:{100 * wins / seeds}%/{hp / seeds:P0}/{mins / seeds:0.0}m");
                }
                Console.WriteLine($"{m.id}: hp {m.healthScale:0.00} dmg {m.damageScale:0.00} avg {avgMin / builds.Length:0.0} min |{per}");
                outLines.Add($"{m.id}={m.healthScale.ToString(CultureInfo.InvariantCulture)},{m.damageScale.ToString(CultureInfo.InvariantCulture)}");
            }
            System.IO.File.WriteAllLines("calibration2.txt", outLines);
        }

        /// <summary>Per-wave trace: duration, spawned HP, damage dealt/taken, upgrades, level.</summary>
        static void Trace(Dictionary<string, string> o)
        {
            string mid = Opt(o, "mission", "m05");
            string build = Opt(o, "build", "default");
            ulong seed = ulong.Parse(Opt(o, "seed", "104729"));
            var content = TestContent.Load();
            var m = content.Mission(mid);
            var save = ProfileFor(Opt(o, "perm", "mid"), build, m.index);
            var meta = new GameMeta(content, save);
            var setup = meta.CreateCampaignSetup(mid, seed, false);
            var b = new Battle(content, setup);
            var pilot = AutoPilot.Build(build, seed);
            var ev = new List<SimEvent>();
            int wave = 0; float waveStart = 0, taken = 0, dealtAtStart = 0, hpMin = 1; int spawned = 0; float spawnedHp = 0;
            Console.WriteLine("wave  dur   spawned  spawnHP   dealt/s  taken   minHP  lvl  upg  sparks");
            float Dealt() { float t = 0; foreach (var kv in b.RunStats.damageDealtBySource) t += kv.Value; return t; }
            while (!b.IsOver && b.TickCount < 30 * 60 * 30)
            {
                pilot.Step(b);
                if (b.Phase == BattlePhase.Running) b.Tick();
                if (b.CheckpointPending) b.TakeCheckpoint();
                b.DrainEvents(ev);
                foreach (var e in ev)
                {
                    if (e.type == SimEventType.WaveStarted) { wave = (int)e.value; waveStart = b.Time; taken = 0; spawned = 0; spawnedHp = 0; dealtAtStart = Dealt(); hpMin = b.Hp / b.MaxHp; }
                    if (e.type == SimEventType.EnemySpawned) { spawned++; foreach (var en in b.Enemies) if (en.uid == e.uid) spawnedHp += en.maxHp; }
                    if (e.type == SimEventType.CitadelDamaged) taken += e.value;
                    if (e.type == SimEventType.WaveCleared || e.type == SimEventType.Victory || e.type == SimEventType.Defeat)
                    {
                        float dur = b.Time - waveStart;
                        Console.WriteLine($"{wave,4} {dur,5:0.0}s {spawned,6} {spawnedHp,8:0} {(Dealt() - dealtAtStart) / Math.Max(1, dur),9:0} {taken,7:0} {Math.Min(hpMin, b.Hp / b.MaxHp),6:P0} {b.Level,4} {b.RunStats.upgradesBought,4} {b.Sparks,6}");
                    }
                }
                if (b.MaxHp > 0) hpMin = Math.Min(hpMin, b.Hp / b.MaxHp);
                ev.Clear();
            }
            var r = b.BuildResult();
            Console.WriteLine($"{(r.victory ? "VICTORY" : "DEFEAT")} time {TextFormat.Duration(r.stats.timeSec)}");
        }

        static void Probe(Dictionary<string, string> o)
        {
            string mid = Opt(o, "mission", "m02");
            string build = Opt(o, "build", "default");
            var work = TestContent.Fresh();
            foreach (var sc in new[] { 1.0f, 1.5f, 2.0f, 3.0f, 4.0f })
            {
                work.Mission(mid).healthScale = sc;
                var sw = Stopwatch.StartNew();
                var r = PlayContent(work, mid, build, 104729);
                Console.WriteLine($"{mid} scale {sc:0.0}: {(r.victory ? "WIN" : "LOSS")} waves {r.wavesCleared} minHP {r.stats.minHealthFraction:P0} time {TextFormat.Duration(r.stats.timeSec)} perks {r.stats.perksTaken} upgrades {r.stats.upgradesBought} ({sw.ElapsedMilliseconds} ms) top {r.principalDamageSource}");
            }
        }

        static RunResult PlayContent(GameContent content, string missionId, string build, ulong seed)
        {
            var m = content.Mission(missionId);
            var save = ProfileFor("mid", build, m.index);
            var meta = new GameMeta(content, save);
            var setup = meta.CreateCampaignSetup(missionId, seed, false);
            setup.emitEvents = false;
            var b = new Battle(content, setup);
            return AutoPilot.Play(b, AutoPilot.Build(build, seed));
        }

        static void SpeedInvariance(Dictionary<string, string> o)
        {
            // Same seed, same inputs: stepping 1 tick per frame vs 2 ticks per frame must match exactly.
            var r1 = RunFrames("m03", 1);
            var r2 = RunFrames("m03", 2);
            Console.WriteLine($"1x: waves {r1.wavesCleared} kills {r1.stats.kills} hp {r1.healthFraction:0.0000} score {r1.score}");
            Console.WriteLine($"2x: waves {r2.wavesCleared} kills {r2.stats.kills} hp {r2.healthFraction:0.0000} score {r2.score}");
            Console.WriteLine(r1.score == r2.score && r1.stats.kills == r2.stats.kills ? "IDENTICAL" : "DIFFERENT");
        }

        static RunResult RunFrames(string mid, int ticksPerFrame)
        {
            var save = ProfileFor("mid", "default", C.Mission(mid).index);
            var meta = new GameMeta(C, save);
            var setup = meta.CreateCampaignSetup(mid, 99, false);
            setup.emitEvents = false;
            var b = new Battle(C, setup);
            var pilot = AutoPilot.Build("default", 99);
            while (!b.IsOver && b.TickCount < 30 * 60 * 30)
            {
                // the pilot acts on tick counts, not frames, so its inputs are identical at both speeds
                for (int k = 0; k < ticksPerFrame && !b.IsOver; k++)
                {
                    pilot.Step(b);
                    if (b.Phase == BattlePhase.Running) b.Tick();
                    if (b.CheckpointPending) b.TakeCheckpoint();
                }
            }
            return b.BuildResult();
        }
    }
}
