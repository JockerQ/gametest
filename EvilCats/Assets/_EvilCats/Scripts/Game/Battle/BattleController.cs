using System;
using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Core;
using EvilCats.Meta;
using EvilCats.Sim;
using UnityEngine;

namespace EvilCats.Game
{
    /// <summary>
    /// Runs a battle: steps the deterministic simulation with a fixed-step accumulator (2x speed
    /// = twice as many steps per second, identical outcome), turns simulation events into visuals,
    /// sound and HUD feedback, opens the decision modals, saves wave checkpoints, applies the run
    /// result exactly once and handles pause, app backgrounding and the Android back button.
    /// Time.timeScale only drives the visuals (0 while paused / deciding, 2 at 2x).
    /// </summary>
    public sealed class BattleController : SceneController
    {
        public Battle Battle { get; private set; }
        public BattleView View { get; private set; }
        public CameraRig Rig { get; private set; }
        public BattleHud Hud { get; private set; }
        public BattleModals Modals { get; private set; }
        public int Speed { get; private set; } = 1;
        public bool Aiming { get; private set; }

        private const float AimSlowdown = 0.3f;
        private GameApp _app;
        private BattleSetup _setup;
        private float _acc;
        private readonly List<SimEvent> _events = new List<SimEvent>(512);
        private bool _paused, _ended, _started;
        private Vector2 _aimPoint;
        private bool _aimManual;
        private float _endDelay = -1f;
        private int _lastBarkWave;
        private string _biomeMusic;
        private float _hintCheck;

        private void Start()
        {
            _app = GameApp.Ensure();
            if (!_app.IsBooted) _app.BootImmediate();   // scene opened directly in the Editor
            if (!_app.IsBooted)
            {
                _app.GoTo(GameApp.BootScene);
                return;
            }
            _setup = _app.PendingBattle ?? DefaultSetup();
            _app.PendingBattle = null;
            try
            {
                Battle = new Battle(_app.Content, _setup);
            }
            catch (Exception e)
            {
                Debug.LogException(e);
                Toast.Show(L.F("ui.error.content", ("msg", e.Message)), Theme.Red);
                _app.GoTo(GameApp.HubScene);
                return;
            }
            Rig = CameraRig.Create(Theme.Bg);
            View = new GameObject("BattleView").AddComponent<BattleView>();
            View.Init(Battle, Rig, _setup.heroSkin);
            Hud = new GameObject("BattleHud").AddComponent<BattleHud>();
            Hud.Init(this);
            Modals = new GameObject("BattleModals").AddComponent<BattleModals>();
            Modals.Init();
            View.Fx.SparkTarget = Hud.SparkTargetWorld;
            View.Fx.CoinArrived = OnCoinArrived;
            Speed = _app.Meta.Data.settings.startAt2x ? 2 : 1;
            _biomeMusic = Battle.Spec.biome == "moonfall" ? "moonfall" : "gravewood";
            _app.Audio?.PlayMusic(_biomeMusic, 1.5f);
            _app.Audio?.Duck(1f);
            _app.Services.Analytics.Event("battle_start", new Dictionary<string, object> { { "mode", Battle.Spec.mode.ToString() }, { "mission", Battle.Spec.missionId } });

            string title = Battle.Spec.mode == BattleMode.Campaign ? L.T("mission." + Battle.Spec.missionId + ".name")
                : Battle.Spec.mode == BattleMode.Endless ? L.T("ui.endless") : L.T("ui.daily.challenge");
            Hud.Announce(title, Theme.Gold, 2.4f, true);
            if (_setup.resume != null) Hud.Announce(L.F("ui.resumed_at", ("n", Battle.NextWave)), Theme.Cyan, 2.2f);
            Hud.ShowHint("tutorial.welcome");
            _started = true;
        }

        private BattleSetup DefaultSetup()
        {
            var m = _app.Meta.NextCampaignMission();
            return _app.Meta.CreateCampaignSetup(m.id, NewSeed(), true);
        }

        public static ulong NewSeed() => Hash.Fnv1a64(Guid.NewGuid().ToString("N"));

        protected override void OnDestroy()
        {
            base.OnDestroy();
            Time.timeScale = 1f;
            if (_app != null && _app.Audio != null) { _app.Audio.StopLoop(); _app.Audio.Duck(1f); }
        }

        // =========================================================================================
        // Main loop
        // =========================================================================================
        private bool Blocked => _paused || (Modals != null && Modals.IsOpen) || Battle == null || Battle.Phase != BattlePhase.Running;

        private void Update()
        {
            if (!_started || Battle == null) return;
            float factor = Speed * (Aiming ? AimSlowdown : 1f);
            bool blocked = Blocked;
            Time.timeScale = Battle.IsOver ? 1f : (blocked ? 0f : factor);
            if (!blocked)
            {
                // clamp long frames (app hitches) so the simulation never "spirals" to catch up
                _acc += Mathf.Min(Time.unscaledDeltaTime, 0.1f) * factor;
                int steps = 0;
                while (_acc >= Battle.Dt && steps < 8)
                {
                    Battle.Tick();
                    steps++;
                    _acc -= Battle.Dt;
                    if (Battle.Phase != BattlePhase.Running) { _acc = 0f; break; }
                }
                if (steps >= 8) _acc = 0f;
            }
            View.Units.Alpha = Battle.Dt > 0f ? _acc / Battle.Dt : 1f;

            _events.Clear();
            Battle.DrainEvents(_events);
            for (int i = 0; i < _events.Count; i++) Handle(_events[i]);

            if (Battle.CheckpointPending) SaveCheckpoint();
            HandlePhase();
            if (Aiming) UpdateAim();
            UpdateTutorialHints();
            if (_endDelay > 0f)
            {
                _endDelay -= Time.unscaledDeltaTime;
                if (_endDelay <= 0f) ShowEndSummary();
            }
        }

        private void HandlePhase()
        {
            if (Aiming && Battle.Phase != BattlePhase.Running) EndAim(false);
            switch (Battle.Phase)
            {
                case BattlePhase.AwaitingPerk:
                    if (!Modals.IsShowing("perk"))
                    {
                        Hud.ShowHint("tutorial.perk");
                        Modals.ShowPerkChoice(Battle, i => Battle.ChoosePerk(i));
                    }
                    break;
                case BattlePhase.AwaitingModuleChoice:
                    if (!Modals.IsShowing("module"))
                        Modals.ShowModuleChoice(Battle, id => Battle.ChooseModuleForSlot(id));
                    break;
                case BattlePhase.AwaitingRevive:
                    if (!Modals.IsShowing("revive"))
                        Modals.ShowRevive(Battle, _app.Services.Ads, () => Battle.Revive(), () => Battle.DeclineRevive());
                    break;
                case BattlePhase.Victory:
                case BattlePhase.Defeat:
                    if (!_ended) OnBattleEnded();
                    break;
            }
        }

        private void SaveCheckpoint()
        {
            var cp = Battle.TakeCheckpoint();
            try
            {
                _app.Meta.CommitCheckpoint(cp, GameApp.UtcNow);
            }
            catch (Exception e)
            {
                // never interrupt the battle because a save failed; the next wave tries again
                Debug.LogException(e);
            }
        }

        // =========================================================================================
        // Player commands (from the HUD)
        // =========================================================================================
        public void TogglePause()
        {
            if (_ended || Battle == null) return;
            if (Modals.IsShowing("pause"))
            {
                Modals.ClosePause();
                _paused = false;
                _app.Audio?.Duck(1f);
                return;
            }
            if (Modals.IsOpen) return;
            if (Aiming) EndAim(false);
            _paused = true;
            _app.Audio?.Duck(0.5f);
            Modals.ShowPause(() =>
            {
                _paused = false;
                _app.Audio?.Duck(1f);
            }, () =>
            {
                _paused = false;
                _app.Audio?.Duck(1f);
                Battle.Abandon();
            });
        }

        public void ToggleSpeed()
        {
            Speed = Speed == 1 ? 2 : 1;
            _app.Audio?.Play("ui_toggle");
        }

        public void CycleTarget()
        {
            if (Battle == null) return;
            var next = (TargetPriority)(((int)Battle.Priority + 1) % 3);
            Battle.SetPriority(next);
            _app.Meta.Data.defaultPriority = next;
            string key = next == TargetPriority.Nearest ? "nearest" : next == TargetPriority.Strongest ? "strongest" : "rangedThreat";
            Toast.Show(L.T("priority." + key) + ": " + L.T("priority." + key + ".desc"), Theme.Cyan);
        }

        public void BuyUpgrade(string id)
        {
            if (Battle == null) return;
            switch (Battle.BuyUpgrade(id))
            {
                case PurchaseResult.Bought:
                    _app.Haptics?.Light();
                    break;
                case PurchaseResult.NotEnoughSparks:
                    _app.Audio?.Play("ui_denied");
                    Toast.Show(L.F("ui.not_enough", ("currency", L.T("ui.sparks"))), Theme.Red);
                    break;
                case PurchaseResult.MaxLevel:
                    _app.Audio?.Play("ui_denied");
                    Toast.Show(L.T("upgrade." + id + ".name") + ": " + L.T("upgrade.max"));
                    break;
                default:
                    _app.Audio?.Play("ui_denied");
                    Toast.Show(L.T("ability.paused"));
                    break;
            }
        }

        public void WardPressed()
        {
            if (Blocked) { Toast.Show(L.T("ability.paused")); return; }
            var r = Battle.CastWard();
            if (r == AbilityResult.OnCooldown)
            {
                _app.Audio?.Play("ui_denied");
                Toast.Show(L.F("ability.cooldown", ("s", Mathf.CeilToInt(Battle.WardCooldown))));
            }
        }

        /// <summary>
        /// Arc Storm: first tap starts aiming (the battle slows down, the densest group is
        /// highlighted). Then tap/drag on the battlefield to strike there, tap Arc Storm again to
        /// strike the highlighted spot, or Cancel. Striking empty ground is refused without using
        /// the cooldown.
        /// </summary>
        public void StormPressed()
        {
            if (Blocked) { Toast.Show(L.T("ability.paused")); return; }
            if (Battle.StormCooldown > 0f)
            {
                _app.Audio?.Play("ui_denied");
                Toast.Show(L.F("ability.cooldown", ("s", Mathf.CeilToInt(Battle.StormCooldown))));
                return;
            }
            if (!Aiming)
            {
                var def = Battle.DefaultStormTarget();
                if (!def.HasValue)
                {
                    _app.Audio?.Play("ui_denied");
                    Toast.Show(L.T("ability.no_targets"));
                    return;
                }
                Aiming = true;
                _aimManual = false;
                _aimPoint = new Vector2(def.Value.x, def.Value.y);
                Hud.SetAiming(true);
                _app.Audio?.Play("swoosh");
                UpdateAim();
                return;
            }
            TryCast(_aimPoint);
        }

        public void AimAt(Vector2 world, bool commit)
        {
            if (!Aiming) return;
            float hw = Battle.C.Tuning.arena.width * 0.5f, hh = Battle.C.Tuning.arena.height * 0.5f;
            _aimPoint = new Vector2(Mathf.Clamp(world.x, -hw, hw), Mathf.Clamp(world.y, -hh, hh));
            _aimManual = true;
            UpdateAim();
            if (commit) TryCast(_aimPoint);
        }

        public void CancelAim() => EndAim(true);

        private void TryCast(Vector2 point)
        {
            var r = Battle.CastArcStorm(new Vec2(point.x, point.y));
            switch (r)
            {
                case AbilityResult.Cast:
                    EndAim(false);
                    break;
                case AbilityResult.NoTargets:
                    _app.Audio?.Play("ui_denied");
                    Toast.Show(L.T("ability.no_targets"));
                    break;
                default:
                    EndAim(false);
                    break;
            }
        }

        private void UpdateAim()
        {
            if (!_aimManual)
            {
                var def = Battle.DefaultStormTarget();
                if (def.HasValue) _aimPoint = Vector2.Lerp(_aimPoint, new Vector2(def.Value.x, def.Value.y), 0.25f);
            }
            int n = Battle.StormTargetsAt(new Vec2(_aimPoint.x, _aimPoint.y));
            View.Fx.ShowReticle(true, _aimPoint, Battle.Stats.abilities.stormRadius, n > 0);
            Hud.SetAimInfo(n, n > 0);
        }

        private void EndAim(bool announce)
        {
            if (!Aiming) return;
            Aiming = false;
            View.Fx.ShowReticle(false, Vector2.zero, 0f, false);
            Hud.SetAiming(false);
            if (announce)
            {
                _app.Audio?.Play("ui_back");
                Toast.Show(L.T("ability.cancelled"));
            }
        }

        private void OnCoinArrived()
        {
            Hud.CoinArrived();
            _app.Audio?.Play("coin", 0.55f);
        }

        // =========================================================================================
        // Simulation events -> presentation
        // =========================================================================================
        private void Handle(SimEvent ev)
        {
            var fx = View.Fx;
            var audio = _app.Audio;
            Vector2 p = new Vector2(ev.pos.x, ev.pos.y), p2 = new Vector2(ev.pos2.x, ev.pos2.y);
            switch (ev.type)
            {
                // ---- waves -------------------------------------------------------------------
                case SimEventType.WaveStarted:
                {
                    int w = (int)ev.value;
                    string text = Battle.Spec.totalWaves > 0 ? L.F("announce.wave_of", ("n", w), ("total", Battle.Spec.totalWaves)) : L.F("announce.wave", ("n", w));
                    Hud.Announce(text, Theme.Text, 1.6f, true);
                    audio?.Play("wave_start");
                    if (w >= 3 && w - _lastBarkWave >= 4 && UnityEngine.Random.value < 0.4f && string.IsNullOrEmpty(ev.id))
                    {
                        _lastBarkWave = w;
                        Hud.Bark(L.T("bark." + UnityEngine.Random.Range(1, 7)));
                    }
                    if (w == 2) Hud.ShowHint("tutorial.sparks");
                    if (w == 3) Hud.ShowHint("tutorial.speed");
                    if (w == 4) Hud.ShowHint("tutorial.priority");
                    break;
                }
                case SimEventType.IncomingAnnounce:
                    Announcement(ev.id);
                    break;
                case SimEventType.WaveCleared:
                    Hud.Announce(L.F("announce.wave_cleared", ("n", (int)ev.value), ("sparks", Mathf.RoundToInt(ev.value2))), Theme.Gold, 1.8f);
                    audio?.Play("wave_clear");
                    break;
                case SimEventType.StallRecovered:
                    if (ev.value >= 0.5f && ev.value < 1.5f) Hud.Announce(L.T("announce.stragglers"), Theme.Red, 2f);
                    break;

                // ---- enemies ------------------------------------------------------------------
                case SimEventType.EnemySpawned:
                    if (ev.id == "bat" && UnityEngine.Random.value < 0.2f) audio?.Play("bat_swarm", 0.6f);
                    else if (ev.id == "iron_golem") audio?.Play("golem_step", 0.7f);
                    break;
                case SimEventType.EnemyHit:
                {
                    bool dot = (ev.flags & SimEvent.FlagDot) != 0;
                    bool crit = (ev.flags & SimEvent.FlagCrit) != 0;
                    View.Units.OnHit(ev.uid, dot);
                    Vector2 at = View.Units.TryGetPos(ev.uid, out var up) ? up : p;
                    fx.DamageNumber(at + new Vector2(0f, 0.6f), ev.value, FxSystem.DamageTypeColor(dot ? 1 : (int)ev.value2), crit ? 1 : dot ? 2 : 0);
                    if (!dot) audio?.Play("enemy_hit", 0.7f);
                    break;
                }
                case SimEventType.EnemyDied:
                {
                    Vector2 at = View.Units.TryGetPos(ev.uid, out var up) ? up : p;
                    View.Units.OnDied(ev.uid, at);
                    bool boss = (ev.flags & SimEvent.FlagBoss) != 0, elite = (ev.flags & SimEvent.FlagElite) != 0;
                    fx.Play("fx/death_poof", at, boss ? 3f : elite ? 2f : 0f);
                    fx.Coins(at, ev.value, ev.value2);
                    audio?.Play("enemy_death", elite ? 1f : 0.8f);
                    if (elite) Rig.Shake(0.08f);
                    break;
                }
                case SimEventType.EnemyAttack:
                    View.Units.OnAttack(ev.uid);
                    if ((ev.flags & 1) != 0 && (ev.flags & SimEvent.FlagBoss) == 0) audio?.Play("arrow_fire", 0.8f);
                    break;
                case SimEventType.EnemyFled:
                    View.Units.OnVanish(ev.uid);
                    fx.Play("fx/dust", p, 1.2f);
                    break;
                case SimEventType.PowderFuse:
                    View.Units.OnSpecial(ev.uid, "fuse", true);
                    fx.Ring(ev.uid, p, 1.3f, FxSystem.DangerColor, ev.value + 0.6f, true);
                    audio?.Play("powder_fuse");
                    break;
                case SimEventType.PowderInterrupted:
                    View.Units.OnSpecial(ev.uid, "walk");
                    fx.Play("fx/stun", p + new Vector2(0f, 1.3f), 0f, null, WorldKit.FxOrder, 1f, ev.uid);
                    audio?.Play("enemy_hit");
                    break;
                case SimEventType.PowderExploded:
                    View.Units.OnVanish(ev.uid);
                    fx.Play("fx/powder_blast", p, 3.2f);
                    audio?.Play("powder_explode");
                    Rig.Shake(0.22f);
                    _app.Haptics?.Heavy();
                    break;
                case SimEventType.PriestHeal:
                    View.Units.OnSpecial(ev.uid, "cast");
                    fx.Play("fx/priest_heal_ring", p, ev.value * 2f);
                    audio?.Play("priest_heal");
                    break;

                // ---- citadel -----------------------------------------------------------------
                case SimEventType.CitadelDamaged:
                {
                    Vector2 dir = p.sqrMagnitude > 0.01f ? p.normalized : Vector2.down;
                    Vector2 hit = dir * 2.2f + new Vector2(0f, 0.8f);
                    fx.Play("fx/impact", hit, 1.2f, new Color(1f, 0.6f, 0.55f));
                    fx.DamageNumber(new Vector2(0f, -2.3f), ev.value, FxSystem.DangerColor, 3);
                    bool heavy = ev.value >= Battle.MaxHp * 0.05f;
                    audio?.Play(heavy ? "citadel_heavy_hit" : "citadel_hit");
                    if (!View.HeroBusy) View.HeroClip("hit");
                    Rig.Shake(Mathf.Clamp(ev.value / Mathf.Max(1f, Battle.MaxHp) * 3f, 0.03f, 0.35f));
                    if (heavy) _app.Haptics?.Medium();
                    if (Battle.Hp < Battle.MaxHp * 0.6f && Battle.WardCooldown <= 0f) Hud.ShowHint("tutorial.ward");
                    break;
                }
                case SimEventType.BarrierGained:
                    if (ev.id == "ward_lantern") audio?.Play("ward_pulse", 0.7f);
                    fx.Sprite("fx/range_ring", View.HeroPos + new Vector2(0f, 0.25f), 0.45f, 3.5f, 6.4f, FxSystem.BarrierColor);
                    break;
                case SimEventType.BarrierAbsorbed:
                    fx.DamageNumber(new Vector2(UnityEngine.Random.Range(-1.4f, 1.4f), 3.4f), ev.value, FxSystem.BarrierColor, 4);
                    audio?.Play("barrier_hit");
                    break;
                case SimEventType.BarrierExpired:
                    if (ev.id == "broken")
                    {
                        audio?.Play("barrier_break");
                        fx.Sprite("fx/range_ring", View.HeroPos + new Vector2(0f, 0.25f), 0.35f, 6.2f, 7.4f, new Color(0.78f, 0.96f, 1f, 0.8f));
                    }
                    break;
                case SimEventType.LastThread:
                    Hud.Announce(L.T("announce.last_thread"), Theme.Barrier, 2.2f, true);
                    audio?.Play("ward_cast");
                    Hud.Flash(0.25f);
                    break;
                case SimEventType.Reflect:
                    fx.Lightning(View.HeroPos + ((p - View.HeroPos).normalized * 3f), p, FxSystem.BarrierColor, 0.22f, 0.16f);
                    break;
                case SimEventType.Revived:
                    fx.Play("fx/level_up", View.HeroPos, 3f);
                    audio?.Play("ward_cast");
                    Hud.Flash(0.3f);
                    Hud.Bark(L.T("bark.1"));
                    break;

                // ---- Arc Light Cat -------------------------------------------------------------
                case SimEventType.HeroAttack:
                    if (!View.HeroBusy) View.HeroClip("attack");
                    fx.Lightning(View.HeroCastPoint, p + new Vector2(0f, 0.5f), FxSystem.ArcColor, 0.36f, 0.15f);
                    fx.Play("fx/spark_hit", p + new Vector2(0f, 0.5f));
                    audio?.Play("arc_bolt");
                    break;
                case SimEventType.ChainHop:
                {
                    Vector2 from = p;
                    if (ev.id == "arc_coil")
                    {
                        string slot = StatsBuilder.SlotOf(Battle.Loadout, "arc_coil");
                        if (slot != null && (p - SlotOriginOf(slot)).sqrMagnitude < 0.01f) from = View.StationMuzzle(slot);
                    }
                    fx.Lightning(from + new Vector2(0f, from == p ? 0.5f : 0f), p2 + new Vector2(0f, 0.5f), ev.id == "arc_coil" ? new Color(0.75f, 0.95f, 1f) : FxSystem.ArcColor, 0.26f, 0.13f);
                    fx.Play("fx/spark_hit", p2 + new Vector2(0f, 0.5f), 0.8f);
                    audio?.Play("chain_jump", 0.6f);
                    break;
                }
                case SimEventType.ThunderclapBurst:
                    fx.Play("fx/spark_hit", p + new Vector2(0f, 0.4f), ev.value * 2f);
                    audio?.Play("arc_storm", 0.45f);
                    break;
                case SimEventType.ArcStormCast:
                    View.HeroClip("cast");
                    fx.Sprite("fx/range_ring", p, 0.5f, ev.value * 2f, ev.value * 2.3f, FxSystem.ArcColor);
                    Hud.Flash(0.28f);
                    Hud.PunchAbility(true);
                    Rig.Shake(0.22f);
                    audio?.Play("arc_storm");
                    _app.Haptics?.Medium();
                    break;
                case SimEventType.ArcStormStrike:
                    fx.Play("fx/arc_storm_strike", p);
                    fx.Play("fx/spark_hit", p + new Vector2(0f, 0.4f), 1.4f);
                    break;
                case SimEventType.WardCast:
                    View.HeroClip("cast");
                    Hud.PunchAbility(false);
                    audio?.Play("ward_cast");
                    fx.Play("fx/heal", View.HeroCastPoint, 1.6f);
                    break;
                case SimEventType.LevelUp:
                    fx.Play("fx/level_up", View.HeroPos, 3f);
                    audio?.Play("level_up");
                    Hud.Announce(L.F("announce.level_up", ("n", (int)ev.value)), Theme.Violet, 1.4f);
                    break;
                case SimEventType.PerkChosen:
                    audio?.Play("perk_pick");
                    View.RebuildStations();
                    break;
                case SimEventType.UpgradeBought:
                    audio?.Play("purchase");
                    Hud.PunchUpgrade(ev.id);
                    if (ev.id == "damage" && (int)ev.value == 8) View.RebuildStations();   // weapons visibly improve
                    break;

                // ---- stations -----------------------------------------------------------------
                case SimEventType.StationFired:
                    View.StationFired(ev.id2);
                    StationSound(ev.id, ev.id2);
                    break;
                case SimEventType.ProjectileHit:
                    if (ev.id == "Bolt")
                    {
                        fx.Play("fx/impact", p + new Vector2(0f, 0.4f), 0.9f, FxSystem.BoneColor);
                        audio?.Play("ballista_hit", 0.7f);
                    }
                    else fx.Play("fx/impact", p, 0.8f, new Color(1f, 0.75f, 0.7f));
                    break;
                case SimEventType.Explosion:
                    if (ev.id == "powder_keg")
                    {
                        fx.Play("fx/powder_blast", p, ev.value * 2f);
                        audio?.Play("powder_explode", 0.8f);
                        Rig.Shake(0.1f);
                    }
                    else
                    {
                        fx.Play("fx/explosion", p, ev.value * 2f);
                        audio?.Play("explosion");
                        Rig.Shake(0.05f);
                    }
                    break;
                case SimEventType.FrostPulse:
                    fx.Play("fx/frost_burst", p, ev.value * 2f);
                    break;
                case SimEventType.WinterRing:
                    fx.Play("fx/winter_ring", p, ev.value * 2f);
                    audio?.Play("frost_bell", 0.8f);
                    break;
                case SimEventType.Freeze:
                    fx.Play("fx/frost_burst", p + new Vector2(0f, 0.4f), 0.9f);
                    audio?.Play("freeze", 0.8f);
                    break;
                case SimEventType.Shatter:
                    fx.Play("fx/shatter", p, ev.value * 2f);
                    audio?.Play("shatter");
                    break;
                case SimEventType.GravityWell:
                    fx.GravityWell(ev.uid, p, ev.value, ev.value2);
                    break;
                case SimEventType.GravityWellEnd:
                    fx.EndGravityWell(ev.uid);
                    break;
                case SimEventType.CinderSpread:
                    fx.Lightning(p + new Vector2(0f, 0.4f), p2 + new Vector2(0f, 0.4f), FxSystem.EmberColor, 0.2f, 0.18f, 0.15f);
                    break;
                case SimEventType.FurnaceHeart:
                    fx.Play("fx/explosion", p + new Vector2(0f, 0.6f), 1.4f, FxSystem.EmberColor);
                    audio?.Play("station_ember_fire");
                    break;

                // ---- bosses -------------------------------------------------------------------
                case SimEventType.BossSpawned:
                    BossArrived(ev.id);
                    break;
                case SimEventType.BossPhase:
                    Hud.Announce(L.F("announce.phase", ("name", L.T("boss." + ev.id + ".name"))), Theme.Red, 2f);
                    audio?.Play("boss_roar");
                    Rig.Shake(0.2f);
                    break;
                case SimEventType.BossTelegraph:
                    BossTelegraph(ev, p, p2);
                    break;
                case SimEventType.BossAbility:
                    BossAbility(ev, p);
                    break;
                case SimEventType.BossStaggered:
                    Hud.Announce(L.T("announce.staggered"), Theme.Cyan, 2f);
                    fx.Play("fx/stun", p + new Vector2(0f, 3.4f), 1.6f, null, WorldKit.FxOrder, 1.2f, ev.uid);
                    audio?.Play("shatter");
                    break;
                case SimEventType.BossDefeated:
                    fx.Play("fx/explosion", p + new Vector2(0f, 1f), 4f);
                    fx.Play("fx/death_poof", p, 4f);
                    Rig.Shake(0.4f);
                    Hud.Flash(0.3f);
                    audio?.Play("boss_roar");
                    _app.Haptics?.Heavy();
                    if (Battle.Spec.totalWaves == 0 || Battle.Wave < Battle.Spec.totalWaves) audio?.PlayMusic(_biomeMusic, 2f);
                    break;

                // ---- loadout changes ------------------------------------------------------------
                case SimEventType.SlotUnlocked:
                    Hud.Announce(L.F("announce.slot_unlocked", ("slot", L.T("slot." + ev.id + ".name"))), Theme.Cyan, 2.4f, true);
                    audio?.Play("unlock");
                    _app.Meta.UnlockSlot(ev.id, GameApp.UtcNow);   // permanent immediately, even if this run is lost
                    View.RebuildStations();
                    if (!string.IsNullOrEmpty(ev.id2)) Hud.ShowHint("tutorial.slot");
                    break;
                case SimEventType.ModuleEquipped:
                    View.RebuildStations();
                    Hud.RefreshSynergy();
                    fx.Play("fx/level_up", View.SlotAnchor(ev.id2), 2.2f);
                    Hud.Announce(L.F("announce.module_equipped", ("name", L.T("module." + ev.id + ".name")), ("slot", L.T("slot." + ev.id2 + ".name"))), Theme.Gold, 2f);
                    break;
            }
        }

        private Vector2 SlotOriginOf(string slot)
        {
            var o = Battle.SlotOrigin(slot);
            return new Vector2(o.x, o.y);
        }

        private void StationSound(string moduleId, string slot)
        {
            var audio = _app.Audio;
            if (audio == null) return;
            switch (moduleId)
            {
                case "arc_coil": audio.Play("station_arc_coil", 0.8f); break;
                case "ember_maw":
                    audio.Play("station_ember_fire", 0.8f);
                    View.Fx.Play("fx/dust", View.StationMuzzle(slot), 1f, new Color(0.6f, 0.55f, 0.5f, 0.9f));
                    break;
                case "frost_whisker": audio.Play("frost_bell", 0.8f); break;
                case "bone_ballista": audio.Play("ballista_fire", 0.8f); break;
                case "ward_lantern":
                    audio.Play("ward_pulse", 0.7f);
                    View.Fx.Play("fx/heal", View.StationMuzzle(slot), 1.2f);
                    break;
                case "gravity_paw": audio.Play("gravity_pull", 0.8f); break;
            }
        }

        private void Announcement(string id)
        {
            if (string.IsNullOrEmpty(id)) return;
            int colon = id.IndexOf(':');
            string kind = colon > 0 ? id.Substring(0, colon) : id;
            string arg = colon > 0 ? id.Substring(colon + 1) : "";
            switch (kind)
            {
                case "elite":
                    Hud.Announce(L.F("announce.elite", ("name", StatText.SourceName(Battle.C, arg))), Theme.Gold, 2.2f);
                    break;
                case "new":
                    Hud.Announce(L.F("announce.new", ("name", StatText.SourceName(Battle.C, arg))), Theme.Cyan, 2.2f);
                    break;
                case "key":
                    Hud.Announce(L.T(arg), Theme.Gold, 2.4f, true);
                    break;
                case "boss":
                    Hud.Announce(L.F("announce.boss", ("name", L.T("boss." + arg + ".name"))), Theme.Red, 2.4f, true);
                    break;
            }
        }

        private void BossArrived(string bossId)
        {
            var audio = _app.Audio;
            audio?.Play("boss_warning");
            audio?.PlayMusic("boss", 1f);
            Rig.Shake(0.25f);
            Hud.Bark(L.T("bark.boss"));
            string key = "boss_intro:" + bossId;
            var shown = _app.Meta.Data.tutorial.hintsShown;
            if (!shown.Contains(key))
            {
                // first encounter: stop and introduce the boss with its counterplay hint
                shown.Add(key);
                if (Aiming) EndAim(false);
                Modals.ShowBossIntro(bossId, () => audio?.Play("boss_roar"));
            }
            else Hud.Announce(L.T("boss." + bossId + ".name") + " — " + L.T("boss." + bossId + ".title"), Theme.Red, 2.4f, true);
        }

        private void BossTelegraph(SimEvent ev, Vector2 p, Vector2 p2)
        {
            var fx = View.Fx;
            string bossName = L.T("boss." + (Battle.ActiveBoss != null ? Battle.ActiveBoss.typeId : "") + ".name");
            float radius = Battle.ActiveBoss != null ? Battle.ActiveBoss.radius : 0.9f;
            switch (ev.id2)
            {
                case "shield_stance":
                    View.Units.OnSpecial(ev.uid, "shield");
                    fx.Ring(ev.uid, p, radius * 1.6f, new Color(0.7f, 0.85f, 1f, 0.9f), ev.value + 0.3f);
                    Hud.Announce(L.F("announce.shield", ("name", bossName)), Theme.Cyan, 2f);
                    break;
                case "charge":
                    View.Units.OnSpecial(ev.uid, "windup", true);
                    fx.ChargeLane(p, p2, ev.value);
                    Hud.Announce(L.F("announce.charge", ("name", bossName)), Theme.Red, 2f, true);
                    _app.Audio?.Play("boss_warning");
                    break;
                case "sector_barrage":
                    View.Units.OnSpecial(ev.uid, Battle.ActiveBoss != null && Battle.ActiveBoss.typeId == "mother_carrion" ? "mark" : "command");
                    fx.Sector(p2, ev.value2, ev.value);
                    Hud.Announce(L.T("announce.barrage"), Theme.Red, 2.4f);
                    _app.Audio?.Play("boss_warning");
                    break;
                case "volley":
                    View.Units.OnSpecial(ev.uid, "windup", true);
                    fx.Ring(ev.uid, p, radius * 1.8f, FxSystem.GoldColor, ev.value, true);
                    Hud.Announce(L.T("announce.volley"), Theme.Gold, 2.4f, true);
                    _app.Audio?.Play("boss_warning");
                    break;
                default:
                    fx.Ring(ev.uid, p, radius * 1.5f, FxSystem.DangerColor, ev.value);
                    break;
            }
        }

        private void BossAbility(SimEvent ev, Vector2 p)
        {
            var fx = View.Fx;
            var audio = _app.Audio;
            string boss = Battle.ActiveBoss != null ? Battle.ActiveBoss.typeId : "";
            switch (ev.id2)
            {
                case "summon":
                    View.Units.OnSpecial(ev.uid, boss == "mother_carrion" ? "summon" : boss == "king_goldenfang" ? "command" : "attack");
                    audio?.Play(ev.id == "carrion_bats" ? "bat_swarm" : "boss_roar", 0.8f);
                    break;
                case "decree":
                    View.Units.OnSpecial(ev.uid, "roar");
                    Hud.Announce(L.T("announce.decree"), Theme.Gold, 2.2f);
                    audio?.Play("bell_toll");
                    break;
                case "shield_stance":
                    View.Units.OnSpecial(ev.uid, "shield");
                    break;
                case "charge_impact":
                    fx.Play("fx/explosion", p + new Vector2(0f, 0.5f), 2.6f, new Color(1f, 0.85f, 0.7f));
                    Rig.Shake(0.45f);
                    Hud.Flash(0.22f);
                    audio?.Play("citadel_heavy_hit");
                    _app.Haptics?.Heavy();
                    break;
                case "sector_barrage":
                    View.Units.OnSpecial(ev.uid, boss == "mother_carrion" ? "barrage" : "volley");
                    audio?.Play("arrow_fire");
                    break;
                case "volley":
                    View.Units.OnSpecial(ev.uid, "volley");
                    fx.Lightning(p + new Vector2(0f, 2f), View.HeroPos + new Vector2(0f, 1.5f), FxSystem.GoldColor, 0.6f, 0.3f, 0.2f);
                    Rig.Shake((ev.flags & 1) != 0 ? 0.15f : 0.4f);
                    audio?.Play("citadel_heavy_hit");
                    _app.Haptics?.Heavy();
                    break;
            }
        }

        // =========================================================================================
        // Tutorial hints that depend on the situation
        // =========================================================================================
        private void UpdateTutorialHints()
        {
            _hintCheck -= Time.unscaledDeltaTime;
            if (_hintCheck > 0f || Battle.IsOver) return;
            _hintCheck = 0.5f;
            if (Battle.StormCooldown <= 0f && Battle.Wave >= 2 && Battle.AliveCount >= 4) Hud.ShowHint("tutorial.storm");
        }

        // =========================================================================================
        // End of run
        // =========================================================================================
        private void OnBattleEnded()
        {
            _ended = true;
            if (Aiming) EndAim(false);
            Modals.CloseAll();
            _paused = false;
            View.Fx.ClearTelegraphs();
            bool win = Battle.Phase == BattlePhase.Victory;
            var result = Battle.BuildResult();
            RewardSummary rewards = null;
            try
            {
                rewards = _app.Meta.ApplyRunResult(result, GameApp.UtcNow, GameApp.LocalNow);   // idempotent (ledger)
            }
            catch (Exception e)
            {
                Debug.LogException(e);
            }
            _app.LastOutcome = new BattleOutcome { result = result, rewards = rewards, setup = _setup };
            _app.Services.Analytics.Event("battle_end", new Dictionary<string, object> { { "victory", win }, { "waves", result.wavesCleared } });
            var audio = _app.Audio;
            if (win)
            {
                View.HeroClip("victory", false);
                audio?.PlayMusic("victory", 0.5f);
                audio?.Play("victory_sting");
                Hud.Bark(L.T("bark.victory"));
                Hud.Announce(L.T("ui.victory"), Theme.Gold, 2f, true);
            }
            else
            {
                View.ShowRuin();
                View.HeroClip("defeat", false);
                audio?.PlayMusic("defeat", 0.5f);
                audio?.Play("defeat_sting");
                Hud.Bark(L.T("bark.defeat"));
            }
            _endDelay = 1.6f;
        }

        private void ShowEndSummary()
        {
            var o = _app.LastOutcome;
            if (o == null) { GoHome(); return; }
            Modals.ShowEnd(_app.Content, o.result, o.rewards, true, GoHome, Retry);
        }

        private void GoHome()
        {
            _app.HubStartScreen = "results";
            _app.GoTo(GameApp.HubScene);
        }

        /// <summary>Fast retry: the same mode/mission again with a new seed, straight from the summary.</summary>
        private void Retry()
        {
            var meta = _app.Meta;
            BattleSetup s;
            switch (_setup.mode)
            {
                case BattleMode.Endless: s = meta.CreateEndlessSetup(NewSeed(), true); break;
                case BattleMode.Daily: s = meta.CreateDailySetup(GameMeta.DailyChallenge(_app.Content, GameApp.UtcNow)); break;
                default: s = meta.CreateCampaignSetup(_setup.missionId, NewSeed(), true); break;
            }
            _app.HubStartScreen = null;
            _app.StartBattle(s);
        }

        // =========================================================================================
        // Lifecycle and back button
        // =========================================================================================
        private void OnApplicationPause(bool paused)
        {
            if (paused) PauseForBackground();
        }

        private void OnApplicationFocus(bool focus)
        {
            if (!focus) PauseForBackground();
        }

        private void PauseForBackground()
        {
            if (!_started || _ended || Battle == null || Battle.IsOver) return;
            if (!Modals.IsOpen && !_paused) TogglePause();   // come back to a paused game, never a lost one
        }

        public override bool OnBack()
        {
            if (!_started) return false;
            if (Modals.IsOpen) return Modals.Back();
            if (Aiming) { EndAim(true); return true; }
            if (Hud.Back()) return true;
            if (_ended) { GoHome(); return true; }
            TogglePause();
            return true;
        }
    }
}
