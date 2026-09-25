using System;
using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Meta;
using EvilCats.Sim;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace EvilCats.Game
{
    /// <summary>A hub screen. Screens are rebuilt when shown (cheap, and always shows fresh data).</summary>
    public abstract class HubScreen
    {
        public HubController Hub;
        protected GameApp App => Hub.App;
        protected GameMeta Meta => Hub.App.Meta;
        protected GameContent C => Hub.App.Content;
        protected SaveData Data => Hub.App.Meta.Data;
        /// <summary>String key of the header title (null = no header).</summary>
        public virtual string TitleKey => null;
        /// <summary>Bottom navigation tab this screen belongs to.</summary>
        public virtual string Tab => "home";
        public abstract void Build(RectTransform content);
        /// <summary>Called after meta data changed (purchases, claims); default rebuilds the screen.</summary>
        public virtual void Refresh() => Hub.Rebuild();
        public virtual bool OnBack() => false;
        /// <summary>Called when another screen replaces this one.</summary>
        public virtual void OnHide() { }
    }

    /// <summary>
    /// Menu scene: top bar (profile, Moon Gold, Storm Shards, settings), content area with a
    /// screen stack (back button / Android back pops), bottom navigation with badges, dialogs,
    /// and the prompts on arrival (resume an interrupted run, post-battle results).
    /// </summary>
    public sealed class HubController : SceneController
    {
        public GameApp App { get; private set; }
        private RectTransform _root, _content, _top, _nav, _dialogs;
        private TextMeshProUGUI _gold, _shards, _name;
        private Image _avatar;
        private readonly List<HubScreen> _stack = new List<HubScreen>();
        private readonly Dictionary<string, (Image frame, Image icon, TextMeshProUGUI label, Image badge)> _tabs =
            new Dictionary<string, (Image, Image, TextMeshProUGUI, Image)>();
        private readonly List<RectTransform> _openDialogs = new List<RectTransform>();
        private bool _dirty;
        private float _badgeTimer;

        public HubScreen Current => _stack.Count > 0 ? _stack[_stack.Count - 1] : null;

        private void Start()
        {
            App = GameApp.Ensure();
            if (!App.IsBooted) App.BootImmediate();
            if (!App.IsBooted) { App.GoTo(GameApp.BootScene); return; }
            Time.timeScale = 1f;
            CameraUtil.EnsureCamera(Theme.Bg);
            _root = UI.CreateCanvas("HubCanvas", 10, out _);
            var bg = UI.Block(_root.parent, Theme.Bg, false, "Bg");
            UI.Stretch(bg.rectTransform);
            bg.transform.SetAsFirstSibling();
            BuildTop();
            BuildNav();
            _content = UI.Rect(_root, "Content");
            UI.Stretch(_content, 0, 54, 0, 66);
            _content.SetSiblingIndex(0);
            _dialogs = UI.Rect(_root, "Dialogs");
            UI.Stretch(_dialogs);
            App.Meta.EnsureDaily(GameApp.LocalNow);
            App.Meta.Changed += OnMetaChanged;
            App.Audio?.PlayMusic("menu", 1.2f);

            string start = App.HubStartScreen;
            App.HubStartScreen = null;
            if (start == "results" && App.LastOutcome != null) Open(new ResultsScreen(App.LastOutcome), true);
            else Open(new HomeScreen(), true);
            RefreshTop();
            RefreshBadges();
            if (start != "results") OfferResume();
        }

        protected override void OnDestroy()
        {
            base.OnDestroy();
            if (App != null && App.Meta != null) App.Meta.Changed -= OnMetaChanged;
        }

        private void OnMetaChanged() => _dirty = true;

        private void Update()
        {
            if (_dirty)
            {
                _dirty = false;
                RefreshTop();
                RefreshBadges();
                Current?.Refresh();
            }
            _badgeTimer -= Time.unscaledDeltaTime;
            if (_badgeTimer <= 0f)
            {
                _badgeTimer = 5f;   // offline gold and date changes tick over time
                App.Meta.EnsureDaily(GameApp.LocalNow);
                RefreshBadges();
            }
        }

        // =========================================================================================
        // Chrome
        // =========================================================================================
        private void BuildTop()
        {
            _top = UI.Rect(_root, "TopBar");
            UI.Strip(_top, true, 52f);
            var bg = UI.Img(_top, "ui/topbar", null, true, "Bg");
            bg.type = Image.Type.Sliced;
            bg.preserveAspect = false;
            UI.Stretch(bg.rectTransform);

            var prof = UI.Img(_top, "ui/slot_frame", null, true, "Profile");
            prof.type = Image.Type.Sliced;
            UI.Place(prof.rectTransform, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), new Vector2(6f, 0f), new Vector2(44f, 44f));
            _avatar = UI.Img(prof.transform, null, null, false, "Avatar");
            UI.Stretch(_avatar.rectTransform, 4, 4, 4, 4);
            _avatar.preserveAspect = true;
            prof.gameObject.AddComponent<PressHandler>().OnTap = () => { App.Audio?.Play("ui_click"); Open(new ProfileScreen()); };
            _name = UI.Text(_top, "", Theme.FontSmall, Theme.TextDim, TextAlignmentOptions.Left, false, "Name");
            // ends 4 units before the Moon Gold box (which starts 118 units from the left edge)
            UI.Place(_name.rectTransform, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), new Vector2(56f, 0f), new Vector2(58f, 20f));
            _name.enableAutoSizing = true;
            _name.fontSizeMin = 8f;
            _name.fontSizeMax = Theme.FontSmall;

            _gold = Currency(_top, "icon/moon_gold", -150f);
            _shards = Currency(_top, "icon/storm_shard", -54f);
            var settings = UI.IconButton(_top, "icon/settings", () => Open(new SettingsScreen()), 44f);
            UI.Place((RectTransform)settings.transform, new Vector2(1f, 0.5f), new Vector2(1f, 0.5f), new Vector2(-4f, 0f), new Vector2(44f, 44f));
        }

        private TextMeshProUGUI Currency(RectTransform parent, string icon, float x)
        {
            var box = UI.Img(parent, "ui/panel_inset", null, false, "Currency");
            box.type = Image.Type.Sliced;
            box.preserveAspect = false;
            UI.Place(box.rectTransform, new Vector2(1f, 0.5f), new Vector2(1f, 0.5f), new Vector2(x, 0f), new Vector2(92f, 32f));
            var ic = UI.Icon(box.transform, icon, 22f);
            UI.Place(ic.rectTransform, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), new Vector2(4f, 0f), new Vector2(22f, 22f));
            var t = UI.Text(box.transform, "0", Theme.FontBody, Theme.Gold, TextAlignmentOptions.Right, true, "Value");
            UI.Place(t.rectTransform, new Vector2(1f, 0.5f), new Vector2(1f, 0.5f), new Vector2(-6f, 0f), new Vector2(62f, 28f));
            t.enableAutoSizing = true;
            t.fontSizeMin = 9f;
            t.fontSizeMax = Theme.FontBody;
            return t;
        }

        private void BuildNav()
        {
            _nav = UI.Rect(_root, "Nav");
            UI.Strip(_nav, false, 64f);
            var bg = UI.Img(_nav, "ui/dock", null, true, "Bg");
            bg.type = Image.Type.Sliced;
            bg.preserveAspect = false;
            UI.Stretch(bg.rectTransform);
            var row = UI.Rect(_nav, "Row");
            UI.Stretch(row, 2, 4, 2, 4);
            var h = UI.HLayout(row, 2f, 0f);
            h.childForceExpandWidth = true;
            Tab(row, "home", "icon/home", "ui.home", () => new HomeScreen());
            Tab(row, "missions", "icon/map", "ui.missions", () => new MissionsScreen());
            Tab(row, "stations", "icon/lantern", "ui.modules", () => new StationsScreen());
            Tab(row, "upgrades", "icon/up_arrow", "ui.upgrades", () => new UpgradesScreen());
            Tab(row, "daily", "icon/calendar", "ui.daily", () => new DailyScreen());
            Tab(row, "more", "icon/scroll", "ui.more", () => new MoreScreen());
        }

        private void Tab(RectTransform row, string id, string icon, string labelKey, Func<HubScreen> make)
        {
            var frame = UI.Img(row, "ui/tab", null, true, "Tab " + id);
            frame.type = Image.Type.Sliced;
            frame.preserveAspect = false;
            UI.Size(frame, -1, 56f, 1);
            var ic = UI.Icon(frame.transform, icon, 26f);
            UI.Place(ic.rectTransform, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -6f), new Vector2(26f, 26f));
            var label = UI.Text(frame.transform, L.T(labelKey), Theme.FontTiny, Theme.TextDim, TextAlignmentOptions.Center, true, "Label");
            UI.Place(label.rectTransform, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 4f), new Vector2(58f, 14f));
            label.enableAutoSizing = true;
            label.fontSizeMin = 7f;
            label.fontSizeMax = Theme.FontTiny;
            var badge = UI.Img(frame.transform, "ui/badge", null, false, "Badge");
            UI.Place(badge.rectTransform, new Vector2(1f, 1f), new Vector2(1f, 1f), new Vector2(-4f, -3f), new Vector2(12f, 12f));
            badge.enabled = false;
            _tabs[id] = (frame, ic, label, badge);
            frame.gameObject.AddComponent<PressHandler>().OnTap = () =>
            {
                App.Audio?.Play("ui_click");
                Open(make(), true);
            };
        }

        private void RefreshTop()
        {
            var d = App.Meta.Data;
            _gold.text = TextFormat.Compact(d.moonGold);
            _shards.text = TextFormat.Compact(d.stormShards);
            _name.text = d.displayName;
            _avatar.sprite = UI.S("avatar/" + d.avatar);
        }

        public void RefreshBadges()
        {
            var meta = App.Meta;
            bool daily = meta.AttendanceAvailable(GameApp.LocalNow, out _) || meta.OfflinePending(GameApp.UtcNow, out double hours, out _) > 0 && hours * 60.0 >= App.Content.Tuning.offline.minCollectMinutes;
            foreach (var o in meta.Data.daily.objectives) if (meta.ObjectiveReady(o)) daily = true;
            bool more = false;
            foreach (var a in App.Content.Progression.achievements) if (meta.AchievementReady(a.id)) { more = true; break; }
            bool stations = false;
            foreach (var m in App.Content.Modules)
            {
                var st = meta.GetModuleState(m.id);
                if (st == ModuleState.Available && meta.Data.stormShards >= m.unlockShards) stations = true;
            }
            SetBadge("daily", daily);
            SetBadge("more", more);
            SetBadge("stations", stations);
            SetBadge("home", false);
            SetBadge("missions", false);
            SetBadge("upgrades", false);
            string active = Current != null ? Current.Tab : "home";
            foreach (var kv in _tabs)
            {
                bool on = kv.Key == active;
                kv.Value.frame.sprite = UI.S(on ? "ui/tab_active" : "ui/tab");
                kv.Value.label.color = on ? Theme.Gold : Theme.TextDim;
            }
        }

        private void SetBadge(string tab, bool on)
        {
            if (_tabs.TryGetValue(tab, out var t)) t.badge.enabled = on;
        }

        // =========================================================================================
        // Screen stack
        // =========================================================================================
        /// <summary>Show a screen. root=true clears the stack (tab switch); otherwise it is pushed.</summary>
        public void Open(HubScreen screen, bool root = false)
        {
            Current?.OnHide();
            if (root) _stack.Clear();
            screen.Hub = this;
            _stack.Add(screen);
            Rebuild();
            RefreshBadges();
        }

        public void Back()
        {
            if (_stack.Count <= 1)
            {
                if (!(Current is HomeScreen)) Open(new HomeScreen(), true);
                return;
            }
            Current?.OnHide();
            _stack.RemoveAt(_stack.Count - 1);
            App.Audio?.Play("ui_back");
            Rebuild();
            RefreshBadges();
        }

        private HubScreen _built;

        /// <summary>Rebuilds the current screen from scratch (after data changes). Rebuilding the same
        /// screen keeps its scroll position, so buying something does not jump back to the top.</summary>
        public void Rebuild()
        {
            float? scroll = null;
            if (_built != null && _built == Current)
            {
                var sr = _content.GetComponentInChildren<ScrollRect>();
                if (sr != null) scroll = sr.verticalNormalizedPosition;
            }
            UI.Clear(_content);
            var s = Current;
            _built = s;
            if (s == null) return;
            var body = _content;
            if (s.TitleKey != null)
            {
                var header = UI.Rect(_content, "Header");
                UI.Strip(header, true, 44f);
                if (_stack.Count > 1)
                {
                    var back = UI.IconButton(header, "icon/back", Back, 40f, "ui_back");
                    UI.Place((RectTransform)back.transform, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), new Vector2(6f, 0f), new Vector2(40f, 40f));
                }
                var title = UI.Text(header, L.T(s.TitleKey), Theme.FontH1, Theme.Gold, TextAlignmentOptions.Center, true, "Title");
                UI.Stretch(title.rectTransform, 50, 0, 50, 0);
                title.enableAutoSizing = true;
                title.fontSizeMin = 12f;
                title.fontSizeMax = Theme.FontH1;
                body = UI.Rect(_content, "Body");
                UI.Stretch(body, 0, 46, 0, 0);
            }
            else
            {
                body = UI.Rect(_content, "Body");
                UI.Stretch(body);
            }
            try
            {
                s.Build(body);
            }
            catch (Exception e)
            {
                // a broken screen must never trap the player: show the problem and keep navigation working
                Debug.LogException(e);
                var t = UI.Text(body, L.F("ui.error.content", ("msg", e.Message)), Theme.FontSmall, Theme.Red);
                UI.Stretch(t.rectTransform, 16, 16, 16, 16);
            }
            if (scroll.HasValue) StartCoroutine(RestoreScroll(scroll.Value));
        }

        private System.Collections.IEnumerator RestoreScroll(float pos)
        {
            yield return null;   // wait for the new layout to be calculated
            var sr = _content.GetComponentInChildren<ScrollRect>();
            if (sr != null) sr.verticalNormalizedPosition = pos;
        }

        // =========================================================================================
        // Dialogs
        // =========================================================================================
        public RectTransform Dialog(float width = 320f, Action onDismiss = null)
        {
            var layer = UI.Blocker(_dialogs);
            var panel = UI.Panel(layer, "ui/panel", "Dialog");
            UI.Place(panel.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(width, 200f));
            var v = UI.VLayout(panel, Theme.S2, Theme.S4, TextAnchor.UpperCenter);
            v.padding = new RectOffset(14, 14, 14, 14);
            var fit = panel.gameObject.AddComponent<ContentSizeFitter>();
            fit.verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            _openDialogs.Add(layer);
            layer.gameObject.AddComponent<DialogTag>().OnDismiss = onDismiss;
            return panel.rectTransform;
        }

        public void CloseDialog(RectTransform panelOrLayer)
        {
            if (panelOrLayer == null) return;
            var layer = panelOrLayer.GetComponent<DialogTag>() != null ? panelOrLayer : (RectTransform)panelOrLayer.parent;
            _openDialogs.Remove(layer);
            if (layer != null) Destroy(layer.gameObject);
        }

        private sealed class DialogTag : MonoBehaviour { public Action OnDismiss; }

        public void Confirm(string text, Action onYes, string yesLabel = null, bool danger = true)
        {
            var d = Dialog();
            var t = UI.Text(d, text, Theme.FontBody, Theme.Text);
            t.overflowMode = TextOverflowModes.Overflow;
            var row = UI.Rect(d, "Buttons");
            UI.Size(row, -1, 50f, -1, -1, 50f);
            UI.HLayout(row, Theme.S2, 0f);
            UI.Button(row, L.T("ui.cancel"), () => CloseDialog(d), ButtonStyle.Normal, null, 48f, Theme.FontBody, "ui_back");
            UI.Button(row, yesLabel ?? L.T("ui.confirm"), () => { CloseDialog(d); onYes?.Invoke(); }, danger ? ButtonStyle.Danger : ButtonStyle.Primary, null, 48f, Theme.FontBody);
        }

        public void Message(string title, string body, string icon = null)
        {
            var d = Dialog();
            if (!string.IsNullOrEmpty(icon)) { var ic = UI.Icon(d, icon, 48f); UI.Size(ic, -1, 48f); }
            if (!string.IsNullOrEmpty(title))
            {
                var tt = UI.Text(d, title, Theme.FontH2, Theme.Gold, TextAlignmentOptions.Center, true);
                UI.Size(tt, -1, 26f);
            }
            var t = UI.Text(d, body, Theme.FontBody, Theme.Text);
            t.overflowMode = TextOverflowModes.Overflow;
            UI.Button(d, L.T("ui.close"), () => CloseDialog(d), ButtonStyle.Primary, null, 48f);
        }

        /// <summary>Shows what a MetaResult means to the player (never a silent failure).</summary>
        public void Explain(MetaResult r)
        {
            string text;
            switch (r)
            {
                case MetaResult.Ok: return;
                case MetaResult.NotEnoughMoonGold: text = L.F("ui.not_enough", ("currency", L.T("ui.moon_gold"))); break;
                case MetaResult.NotEnoughShards: text = L.F("ui.not_enough", ("currency", L.T("ui.storm_shards"))); break;
                case MetaResult.MaxLevel: text = L.T("upgrade.max"); break;
                case MetaResult.AlreadyClaimed: text = L.T("ui.claimed"); break;
                case MetaResult.Locked: text = L.T("ui.locked"); break;
                case MetaResult.RequirementMissing: text = L.T("ui.requirement_missing"); break;
                case MetaResult.ClockMovedBack: text = L.T("ui.daily.clock_warning"); break;
                case MetaResult.TooSoon: text = L.T("ui.daily.too_soon"); break;
                case MetaResult.NothingToClaim: text = L.T("ui.nothing_to_claim"); break;
                case MetaResult.InvalidInput: text = L.T("ui.profile.name_rules"); break;
                default: text = L.T("ui.not_available"); break;
            }
            App.Audio?.Play("ui_denied");
            Toast.Show(text, Theme.Red);
        }

        // =========================================================================================
        // Starting battles
        // =========================================================================================
        public void StartMission(string missionId)
        {
            if (App.Meta.Data.activeRun != null)
            {
                // starting something new while a run is saved would silently abandon it: ask first
                Confirm(L.T("ui.resume_discard_confirm"), () =>
                {
                    AbandonSavedRun();
                    StartMission(missionId);
                }, L.T("ui.resume_discard"));
                return;
            }
            App.Audio?.Play("swoosh");
            App.StartBattle(App.Meta.CreateCampaignSetup(missionId, BattleController.NewSeed(), true));
        }

        public void StartEndless()
        {
            if (App.Meta.Data.activeRun != null) { OfferResume(); return; }
            App.StartBattle(App.Meta.CreateEndlessSetup(BattleController.NewSeed(), true));
        }

        public void StartDaily()
        {
            if (App.Meta.Data.activeRun != null) { OfferResume(); return; }
            App.StartBattle(App.Meta.CreateDailySetup(GameMeta.DailyChallenge(App.Content, GameApp.UtcNow)));
        }

        /// <summary>A run interrupted by closing the app resumes at the start of the next wave.</summary>
        public void OfferResume()
        {
            var cp = App.Meta.Data.activeRun;
            if (cp == null) return;
            string mission = cp.mode == BattleMode.Campaign ? L.T("mission." + cp.missionId + ".name")
                : cp.mode == BattleMode.Endless ? L.T("ui.endless") : L.T("ui.daily.challenge");
            var d = Dialog(320f);
            var title = UI.Text(d, L.T("ui.resume_title"), Theme.FontH2, Theme.Gold, TextAlignmentOptions.Center, true);
            UI.Size(title, -1, 26f);
            var body = UI.Text(d, L.F("ui.resume_body", ("mission", mission), ("wave", cp.nextWave)), Theme.FontSmall, Theme.Text);
            body.overflowMode = TextOverflowModes.Overflow;
            UI.Button(d, L.T("ui.resume"), () =>
            {
                CloseDialog(d);
                ResumeRun(cp);
            }, ButtonStyle.Primary, "icon/play", 52f);
            UI.Button(d, L.T("ui.resume_discard"), () => Confirm(L.T("ui.resume_discard_confirm"), () =>
            {
                CloseDialog(d);
                AbandonSavedRun();
            }, L.T("ui.resume_discard")), ButtonStyle.Normal, null, 44f, Theme.FontBody);
        }

        private void ResumeRun(RunCheckpoint cp)
        {
            var meta = App.Meta;
            BattleSetup s;
            switch (cp.mode)
            {
                case BattleMode.Endless: s = meta.CreateEndlessSetup(cp.seed, true); break;
                case BattleMode.Daily:
                {
                    // rebuild the challenge the run started with (loadout, modifiers, boss), even
                    // if it is resumed on a later day
                    var day = GameApp.UtcNow;
                    var inv = System.Globalization.CultureInfo.InvariantCulture;
                    if (!string.IsNullOrEmpty(cp.dailyDate) && DateTime.TryParseExact(cp.dailyDate, "yyyy-MM-dd", inv,
                            System.Globalization.DateTimeStyles.AssumeUniversal | System.Globalization.DateTimeStyles.AdjustToUniversal, out var date)) day = date;
                    else if (!string.IsNullOrEmpty(cp.savedAtUtc) && DateTime.TryParse(cp.savedAtUtc, inv,
                            System.Globalization.DateTimeStyles.RoundtripKind, out var saved)) day = saved.ToUniversalTime();   // saves made before dailyDate existed
                    s = meta.CreateDailySetup(GameMeta.DailyChallenge(App.Content, day));
                    s.seed = cp.seed;
                    break;
                }
                default: s = meta.CreateCampaignSetup(cp.missionId, cp.seed, true); break;
            }
            s.resume = cp;
            s.runId = cp.runId;
            App.StartBattle(s);
        }

        /// <summary>Abandoning a saved run counts as a defeat: rewards for its cleared waves are kept (once).</summary>
        private void AbandonSavedRun()
        {
            var cp = App.Meta.Data.activeRun;
            if (cp == null) return;
            var result = new RunResult
            {
                runId = cp.runId, mode = cp.mode, missionId = cp.missionId, victory = false, abandoned = true,
                wavesCleared = cp.stats != null ? cp.stats.wavesCleared : 0, levelReached = cp.level,
                stats = cp.stats ?? new RunStats(), seed = cp.seed, dailyDate = cp.dailyDate,
            };
            var m = App.Content.Mission(cp.missionId);
            result.totalWaves = cp.mode == BattleMode.Campaign && m != null ? m.waves : cp.mode == BattleMode.Daily ? App.Content.Daily.waves : 0;
            foreach (var kv in cp.loadout) result.loadout[kv.Key] = kv.Value;
            result.unlockedSlots.AddRange(cp.unlockedSlots);
            result.score = Battle.ComputeScore(result);
            App.Meta.ApplyRunResult(result, GameApp.UtcNow, GameApp.LocalNow);
            App.Meta.ClearCheckpoint(GameApp.UtcNow);
            RefreshTop();
        }

        // =========================================================================================
        // Back button
        // =========================================================================================
        public override bool OnBack()
        {
            if (_openDialogs.Count > 0)
            {
                var top = _openDialogs[_openDialogs.Count - 1];
                var tag = top != null ? top.GetComponent<DialogTag>() : null;
                _openDialogs.RemoveAt(_openDialogs.Count - 1);
                if (top != null) Destroy(top.gameObject);
                tag?.OnDismiss?.Invoke();
                return true;
            }
            if (Current != null && Current.OnBack()) return true;
            if (_stack.Count > 1 || !(Current is HomeScreen)) { Back(); return true; }
            // on the home screen: offer to leave (progress is already saved)
            App.SaveNow();
            Confirm(L.T("ui.exit_confirm"), () =>
            {
                App.SaveNow();
                Application.Quit();
            }, L.T("ui.exit"), false);
            return true;
        }
    }
}
