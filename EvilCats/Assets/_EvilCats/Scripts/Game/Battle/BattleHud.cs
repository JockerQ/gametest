using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Sim;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace EvilCats.Game
{
    /// <summary>
    /// Battle HUD built at runtime. Top bar: pause, wave, Spark Coins, speed, health + barrier,
    /// XP/level. Boss bar with phase / shield / stagger meter. Bottom dock: Arc Storm (aim with
    /// cancel), Nine-Lives Ward, target priority, synergy info and the six run upgrades
    /// (tap = buy, hold = details). Also announcements, tutorial hints, barks, the danger vignette
    /// and the battlefield input layer (aiming, tapping enemies for info).
    /// </summary>
    public sealed class BattleHud : MonoBehaviour
    {
        private BattleController _ctl;
        private Battle B => _ctl.Battle;
        private RectTransform _screen, _root, _top, _dock, _boss, _tooltip, _hint, _aimBar, _bark;
        private Canvas _canvas;

        // top bar
        private UI.Bar _hp, _xp;
        private TextMeshProUGUI _hpText, _waveText, _waveSub, _sparksText, _levelText;
        private RectTransform _sparkIcon;
        private Punch _sparkPunch;
        private Button _speedBtn;
        private TextMeshProUGUI _speedText;

        // boss bar
        private UI.Bar _bossBar;
        private TextMeshProUGUI _bossName, _bossStatus;
        private Image _bossIcon;
        private string _bossShown;

        // dock
        private AbilityButton _storm, _ward;
        private Button _targetBtn;
        private TextMeshProUGUI _targetText;
        private Image _targetIcon;
        private Button _synergyBtn;
        private TextMeshProUGUI _synergyText;
        private readonly List<UpgradeButton> _upgrades = new List<UpgradeButton>();
        private TextMeshProUGUI _tooltipTitle, _tooltipBody;

        // overlays
        private Image _vignette, _flash;
        private float _flashT;
        private TextMeshProUGUI _banner;
        private readonly Queue<(string text, Color color, float time, bool big)> _banners = new Queue<(string, Color, float, bool)>();
        private float _bannerT, _bannerDur;
        private TextMeshProUGUI _hintText, _barkText, _aimText;
        private readonly List<string> _hints = new List<string>();   // waiting to be shown, first = next
        private string _hintKey;                                     // the one on screen
        private float _hintT, _barkT;

        // cached values (avoid rebuilding text every frame)
        private int _lastHp = -1, _lastMax = -1, _lastBarrier = -1, _lastSparks = -1, _lastWave = -1, _lastLevel = -1, _lastSub = -9999;
        private TargetPriority _lastPriority = (TargetPriority)(-1);
        private float _reservedTop = -1f, _reservedBottom = -1f;

        private sealed class AbilityButton
        {
            public RectTransform root;
            public Image frame, icon, cooldown, glow;
            public TextMeshProUGUI label, timer;
            public Punch punch;
            public bool wasReady;
        }

        private sealed class UpgradeButton
        {
            public string id;
            public RunUpgradeDef def;
            public RectTransform root;
            public Image frame, icon, coin;
            public TextMeshProUGUI level, cost;
            public Punch punch;
            public int lastLevel = -1, lastCost = -1, lastState = -1;
        }

        public void Init(BattleController ctl)
        {
            _ctl = ctl;
            _root = UI.CreateCanvas("BattleHud", 100, out _canvas);
            _screen = (RectTransform)_root.parent;
            BuildInputLayer();
            BuildOverlays();
            BuildTopBar();
            BuildBossBar();
            BuildDock();
            BuildBanner();
            BuildTooltip();
            BuildHint();
            BuildAimBar();
            BuildBark();
        }

        // =========================================================================================
        // Construction
        // =========================================================================================
        private void BuildInputLayer()
        {
            // Full-screen transparent layer behind all HUD widgets: taps on the battlefield.
            var img = UI.Block(_screen, new Color(0f, 0f, 0f, 0.001f), true, "BattlefieldInput");
            UI.Stretch(img.rectTransform);
            img.transform.SetAsFirstSibling();
            var input = img.gameObject.AddComponent<BattlefieldInput>();
            input.Hud = this;
        }

        private void BuildOverlays()
        {
            _vignette = UI.Img(_screen, "ui/vignette", new Color(1f, 0.1f, 0.15f, 0f), false, "DangerVignette");
            _vignette.type = Image.Type.Simple;
            _vignette.preserveAspect = false;
            UI.Stretch(_vignette.rectTransform);
            _vignette.transform.SetSiblingIndex(1);
            _flash = UI.Block(_screen, new Color(1f, 1f, 1f, 0f), false, "Flash");
            UI.Stretch(_flash.rectTransform);
            _flash.transform.SetSiblingIndex(2);
        }

        private void BuildTopBar()
        {
            _top = UI.Rect(_root, "TopBar");
            UI.Strip(_top, true, 86f);
            var bg = UI.Img(_top, "ui/topbar", null, true, "Bg");
            bg.type = Image.Type.Sliced;
            bg.preserveAspect = false;
            UI.Stretch(bg.rectTransform);

            var pause = UI.IconButton(_top, "icon/pause", () => _ctl.TogglePause(), 42f);
            UI.Place((RectTransform)pause.transform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(6f, -4f), new Vector2(42f, 42f));

            _waveText = UI.Text(_top, "", Theme.FontH2, Theme.Text, TextAlignmentOptions.Left, true, "Wave");
            UI.Place(_waveText.rectTransform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(56f, -4f), new Vector2(150f, 24f));
            _waveSub = UI.Text(_top, "", Theme.FontTiny, Theme.TextDim, TextAlignmentOptions.Left, false, "WaveSub");
            UI.Place(_waveSub.rectTransform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(56f, -27f), new Vector2(150f, 16f));

            var sparks = UI.Rect(_top, "Sparks");
            UI.Place(sparks, new Vector2(1f, 1f), new Vector2(1f, 1f), new Vector2(-56f, -6f), new Vector2(112f, 36f));
            var sparksBg = UI.Img(sparks, "ui/panel_inset", null, false, "Bg");
            sparksBg.type = Image.Type.Sliced;
            sparksBg.preserveAspect = false;
            UI.Stretch(sparksBg.rectTransform);
            var coin = UI.Icon(sparks, "icon/spark", 24f);
            UI.Place(coin.rectTransform, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), new Vector2(6f, 0f), new Vector2(24f, 24f));
            _sparkIcon = coin.rectTransform;
            _sparkPunch = sparks.gameObject.AddComponent<Punch>();
            _sparksText = UI.Text(sparks, "0", Theme.FontH2, Theme.Gold, TextAlignmentOptions.Right, true, "Value");
            UI.Place(_sparksText.rectTransform, new Vector2(1f, 0.5f), new Vector2(1f, 0.5f), new Vector2(-8f, 0f), new Vector2(76f, 30f));
            _sparksText.enableAutoSizing = true;
            _sparksText.fontSizeMin = 10f;
            _sparksText.fontSizeMax = Theme.FontH2;
            var sparkTap = sparksBg.gameObject.AddComponent<PressHandler>();
            sparksBg.raycastTarget = true;
            sparkTap.OnTap = () => ShowHintNow("tutorial.sparks");

            _speedBtn = UI.Button(_top, "1x", () => _ctl.ToggleSpeed(), ButtonStyle.Normal, null, 42f, Theme.FontH2);
            UI.Place((RectTransform)_speedBtn.transform, new Vector2(1f, 1f), new Vector2(1f, 1f), new Vector2(-6f, -4f), new Vector2(46f, 42f));
            _speedText = _speedBtn.GetComponentInChildren<TextMeshProUGUI>(true);

            // health (with barrier segment) and XP
            _hp = UI.ProgressBar(_top, Theme.Health, 18f, true, Theme.Barrier, true);
            UI.Place(_hp.root, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(8f, -50f), new Vector2(344f, 18f));
            _hp.root.anchorMax = new Vector2(1f, 1f);
            _hp.root.sizeDelta = new Vector2(-16f, 18f);
            _hpText = _hp.label;
            _hp.extraMinY = 0.5f;   // barrier: a pale strip over the top half of the health bar
            var hpIcon = UI.Icon(_hp.root, "icon/heart", 16f);
            UI.Place(hpIcon.rectTransform, new Vector2(0f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0f, 0f), new Vector2(18f, 18f));

            _xp = UI.ProgressBar(_top, Theme.Violet, 8f);
            UI.Place(_xp.root, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(44f, -73f), new Vector2(0f, 8f));
            _xp.root.anchorMax = new Vector2(1f, 1f);
            _xp.root.sizeDelta = new Vector2(-52f, 8f);
            _levelText = UI.Text(_top, "", Theme.FontTiny, Theme.Violet, TextAlignmentOptions.Left, true, "Level");
            UI.Place(_levelText.rectTransform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(8f, -69f), new Vector2(40f, 16f));
        }

        private void BuildBossBar()
        {
            _boss = UI.Rect(_root, "BossBar");
            UI.Strip(_boss, true, 42f, 88f);
            var bg = UI.Panel(_boss, "ui/panel", "Bg");
            bg.raycastTarget = false;
            UI.Stretch(bg.rectTransform, 6, 0, 6, 0);
            _bossIcon = UI.Icon(_boss, null, 32f);
            UI.Place(_bossIcon.rectTransform, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), new Vector2(12f, 0f), new Vector2(32f, 32f));
            _bossName = UI.Text(_boss, "", Theme.FontSmall, Theme.Gold, TextAlignmentOptions.Left, true, "Name");
            UI.Place(_bossName.rectTransform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(50f, -3f), new Vector2(170f, 16f));
            _bossStatus = UI.Text(_boss, "", Theme.FontTiny, Theme.Cyan, TextAlignmentOptions.Right, true, "Status");
            UI.Place(_bossStatus.rectTransform, new Vector2(1f, 1f), new Vector2(1f, 1f), new Vector2(-14f, -3f), new Vector2(150f, 16f));
            _bossBar = UI.ProgressBar(_boss, Theme.Gold, 14f, true, Theme.Cyan);
            UI.Place(_bossBar.root, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(50f, 6f), new Vector2(0f, 14f));
            _bossBar.root.anchorMax = new Vector2(1f, 0f);
            _bossBar.root.sizeDelta = new Vector2(-64f, 14f);
            _bossBar.extraMinY = 0.6f;   // stagger meter strip during Goldenfang's volley
            _boss.gameObject.SetActive(false);
        }

        private void BuildDock()
        {
            _dock = UI.Rect(_root, "Dock");
            UI.Strip(_dock, false, 172f);
            var bg = UI.Img(_dock, "ui/dock", null, true, "Bg");
            bg.type = Image.Type.Sliced;
            bg.preserveAspect = false;
            UI.Stretch(bg.rectTransform);

            _storm = Ability(_dock, "icon/bolt", L.T("ability.arc_storm.name"), 8f, Theme.Cyan, () => _ctl.StormPressed(), () => ShowAbilityInfo(true));
            _ward = Ability(_dock, "icon/shield", L.T("ability.ward.name"), 80f, Theme.Barrier, () => _ctl.WardPressed(), () => ShowAbilityInfo(false));

            _targetBtn = UI.Button(_dock, "", () => _ctl.CycleTarget(), ButtonStyle.Normal, null, 64f, Theme.FontSmall);
            UI.Place((RectTransform)_targetBtn.transform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(152f, -8f), new Vector2(104f, 64f));
            var row = _targetBtn.transform.Find("Row");
            if (row != null) UI.Clear(row);
            _targetIcon = UI.Icon(_targetBtn.transform, "icon/target_nearest", 26f);
            UI.Place(_targetIcon.rectTransform, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -6f), new Vector2(26f, 26f));
            var tcap = UI.Text(_targetBtn.transform, L.T("ui.target"), Theme.FontTiny, Theme.TextDim, TextAlignmentOptions.Center, false, "Caption");
            UI.Place(tcap.rectTransform, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 20f), new Vector2(100f, 12f));
            _targetText = UI.Text(_targetBtn.transform, "", Theme.FontSmall, Theme.Text, TextAlignmentOptions.Center, true, "Value");
            UI.Place(_targetText.rectTransform, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 5f), new Vector2(100f, 16f));
            _targetText.enableAutoSizing = true;
            _targetText.fontSizeMin = 8f;
            _targetText.fontSizeMax = Theme.FontSmall;

            _synergyBtn = UI.Button(_dock, "", ToggleSynergyInfo, ButtonStyle.Normal, null, 64f, Theme.FontSmall);
            UI.Place((RectTransform)_synergyBtn.transform, new Vector2(1f, 1f), new Vector2(1f, 1f), new Vector2(-8f, -8f), new Vector2(92f, 64f));
            var srow = _synergyBtn.transform.Find("Row");
            if (srow != null) UI.Clear(srow);
            var sic = UI.Icon(_synergyBtn.transform, "icon/chain", 24f);
            UI.Place(sic.rectTransform, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -7f), new Vector2(24f, 24f));
            _synergyText = UI.Text(_synergyBtn.transform, "", Theme.FontTiny, Theme.TextDim, TextAlignmentOptions.Center, true, "Value");
            UI.Place(_synergyText.rectTransform, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 5f), new Vector2(88f, 26f));
            _synergyText.enableAutoSizing = true;
            _synergyText.fontSizeMin = 7f;
            _synergyText.fontSizeMax = Theme.FontTiny;
            _synergyText.overflowMode = TextOverflowModes.Truncate;

            // six run upgrades
            var ups = new List<RunUpgradeDef>(B.C.Upgrades);
            ups.Sort((a, b) => a.order.CompareTo(b.order));
            float w = (344f - 5 * 4f) / 6f;
            for (int i = 0; i < ups.Count && i < 6; i++) _upgrades.Add(Upgrade(ups[i], 8f + i * (w + 4f), w));
        }

        private AbilityButton Ability(RectTransform parent, string icon, string label, float x, Color color, System.Action onTap, System.Action onHold)
        {
            var ab = new AbilityButton();
            var frame = UI.Img(parent, "ui/button", null, true, "Ability " + label);
            frame.type = Image.Type.Sliced;
            frame.preserveAspect = false;
            ab.root = frame.rectTransform;
            UI.Place(ab.root, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(x, -8f), new Vector2(64f, 64f));
            ab.frame = frame;
            ab.glow = UI.Img(ab.root, "ui/ring", new Color(color.r, color.g, color.b, 0f), false, "Glow");
            ab.glow.preserveAspect = false;
            UI.Stretch(ab.glow.rectTransform, -4, -4, -4, -4);
            ab.icon = UI.Icon(ab.root, icon, 34f, color);
            UI.Place(ab.icon.rectTransform, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -5f), new Vector2(34f, 34f));
            ab.label = UI.Text(ab.root, label, Theme.FontTiny, Theme.Text, TextAlignmentOptions.Center, true, "Label");
            UI.Place(ab.label.rectTransform, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 4f), new Vector2(60f, 20f));
            ab.label.enableAutoSizing = true;
            ab.label.fontSizeMin = 7f;
            ab.label.fontSizeMax = Theme.FontTiny;
            ab.cooldown = UI.Block(ab.root, new Color(0.02f, 0.01f, 0.05f, 0.72f), false, "Cooldown");
            UI.Stretch(ab.cooldown.rectTransform, 3, 3, 3, 3);
            ab.cooldown.type = Image.Type.Filled;
            ab.cooldown.fillMethod = Image.FillMethod.Vertical;
            ab.cooldown.fillOrigin = (int)Image.OriginVertical.Bottom;
            ab.timer = UI.Text(ab.root, "", Theme.FontH1, Theme.Text, TextAlignmentOptions.Center, true, "Timer");
            UI.Stretch(ab.timer.rectTransform);
            ab.punch = ab.root.gameObject.AddComponent<Punch>();
            var press = frame.gameObject.AddComponent<PressHandler>();
            press.OnTap = onTap;
            press.OnHoldStart = onHold;
            press.OnHoldEnd = HideTooltip;
            return ab;
        }

        private UpgradeButton Upgrade(RunUpgradeDef def, float x, float w)
        {
            var ub = new UpgradeButton { id = def.id, def = def };
            var frame = UI.Img(_dock, "ui/slot_frame", null, true, "Upgrade " + def.id);
            frame.type = Image.Type.Sliced;
            frame.preserveAspect = false;
            ub.frame = frame;
            ub.root = frame.rectTransform;
            UI.Place(ub.root, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(x, -80f), new Vector2(w, 84f));
            ub.icon = UI.Icon(ub.root, "icon/" + (string.IsNullOrEmpty(def.icon) ? "up_arrow" : def.icon), 30f);
            UI.Place(ub.icon.rectTransform, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -8f), new Vector2(30f, 30f));
            ub.level = UI.Text(ub.root, "", Theme.FontTiny, Theme.TextDim, TextAlignmentOptions.Center, false, "Level");
            UI.Place(ub.level.rectTransform, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -40f), new Vector2(w, 14f));
            ub.coin = UI.Icon(ub.root, "icon/spark", 12f);
            UI.Place(ub.coin.rectTransform, new Vector2(0f, 0f), new Vector2(0f, 0f), new Vector2(4f, 10f), new Vector2(12f, 12f));
            ub.cost = UI.Text(ub.root, "", Theme.FontSmall, Theme.Gold, TextAlignmentOptions.Right, true, "Cost");
            UI.Place(ub.cost.rectTransform, new Vector2(1f, 0f), new Vector2(1f, 0f), new Vector2(-4f, 6f), new Vector2(w - 18f, 20f));
            ub.cost.enableAutoSizing = true;
            ub.cost.fontSizeMin = 8f;
            ub.cost.fontSizeMax = Theme.FontSmall;
            ub.punch = ub.root.gameObject.AddComponent<Punch>();
            var press = frame.gameObject.AddComponent<PressHandler>();
            press.OnTap = () => _ctl.BuyUpgrade(def.id);
            press.OnHoldStart = () => ShowUpgradeInfo(def);
            press.OnHoldEnd = HideTooltip;
            return ub;
        }

        private void BuildBanner()
        {
            _banner = UI.Text(_root, "", Theme.FontH1, Theme.Text, TextAlignmentOptions.Center, true, "Banner");
            UI.Place(_banner.rectTransform, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -140f), new Vector2(340f, 64f));
            _banner.overflowMode = TextOverflowModes.Overflow;
            _banner.enableAutoSizing = true;
            _banner.fontSizeMin = 12f;
            _banner.fontSizeMax = Theme.FontTitle;
            _banner.outlineWidth = 0.22f;
            _banner.outlineColor = new Color32(20, 8, 32, 255);
            _banner.alpha = 0f;
        }

        private void BuildTooltip()
        {
            var panel = UI.Panel(_root, "ui/tooltip", "Tooltip");
            panel.raycastTarget = false;
            _tooltip = panel.rectTransform;
            UI.Place(_tooltip, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 178f), new Vector2(340f, 120f));
            _tooltipTitle = UI.Text(_tooltip, "", Theme.FontH2, Theme.Gold, TextAlignmentOptions.TopLeft, true, "Title");
            UI.Place(_tooltipTitle.rectTransform, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(12f, -8f), new Vector2(316f, 24f));
            _tooltipBody = UI.Text(_tooltip, "", Theme.FontSmall, Theme.Text, TextAlignmentOptions.TopLeft, false, "Body");
            UI.Stretch(_tooltipBody.rectTransform, 12, 34, 12, 8);
            _tooltipBody.overflowMode = TextOverflowModes.Overflow;
            _tooltip.gameObject.SetActive(false);
        }

        private void BuildHint()
        {
            var panel = UI.Panel(_root, "ui/panel", "Hint");
            panel.raycastTarget = false;   // only the Continue button takes taps; the battlefield stays usable
            _hint = panel.rectTransform;
            UI.Place(_hint, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 178f), new Vector2(340f, 74f));
            var icon = UI.Icon(_hint, "icon/info", 24f, Theme.Cyan);
            UI.Place(icon.rectTransform, new Vector2(0f, 0.5f), new Vector2(0f, 0.5f), new Vector2(10f, 0f), new Vector2(24f, 24f));
            _hintText = UI.Text(_hint, "", Theme.FontSmall, Theme.Text, TextAlignmentOptions.Left, false, "Text");
            UI.Stretch(_hintText.rectTransform, 42, 6, 76, 6);
            _hintText.enableAutoSizing = true;
            _hintText.fontSizeMin = 9f;
            _hintText.fontSizeMax = Theme.FontSmall;
            _hintText.overflowMode = TextOverflowModes.Overflow;
            var ok = UI.Button(_hint, L.T("ui.continue"), HideHint, ButtonStyle.Primary, null, 40f, Theme.FontSmall);
            UI.Place((RectTransform)ok.transform, new Vector2(1f, 0.5f), new Vector2(1f, 0.5f), new Vector2(-8f, 0f), new Vector2(64f, 40f));
            _hint.gameObject.SetActive(false);
        }

        private void BuildAimBar()
        {
            var panel = UI.Panel(_root, "ui/tooltip", "AimBar");
            panel.raycastTarget = false;   // enemies under the bar can still be targeted; Cancel still works
            _aimBar = panel.rectTransform;
            UI.Place(_aimBar, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 178f), new Vector2(340f, 56f));
            _aimText = UI.Text(_aimBar, L.T("ability.aim"), Theme.FontSmall, Theme.Cyan, TextAlignmentOptions.Left, false, "Text");
            UI.Stretch(_aimText.rectTransform, 12, 4, 108, 4);
            _aimText.enableAutoSizing = true;
            _aimText.fontSizeMin = 8f;
            _aimText.fontSizeMax = Theme.FontSmall;
            var cancel = UI.Button(_aimBar, L.T("ui.cancel"), () => _ctl.CancelAim(), ButtonStyle.Danger, "icon/close", 44f, Theme.FontSmall, "ui_back");
            UI.Place((RectTransform)cancel.transform, new Vector2(1f, 0.5f), new Vector2(1f, 0.5f), new Vector2(-6f, 0f), new Vector2(96f, 44f));
            _aimBar.gameObject.SetActive(false);
        }

        private void BuildBark()
        {
            var panel = UI.Panel(_root, "ui/tooltip", "Bark");
            panel.raycastTarget = false;
            _bark = panel.rectTransform;
            _bark.anchorMin = _bark.anchorMax = new Vector2(0.5f, 0.5f);
            _bark.pivot = new Vector2(0.5f, 0f);
            _bark.sizeDelta = new Vector2(220f, 44f);
            _barkText = UI.Text(_bark, "", Theme.FontSmall, Theme.Text, TextAlignmentOptions.Center, false, "Text");
            UI.Stretch(_barkText.rectTransform, 8, 4, 8, 4);
            _barkText.enableAutoSizing = true;
            _barkText.fontSizeMin = 8f;
            _barkText.fontSizeMax = Theme.FontSmall;
            _barkText.fontStyle = FontStyles.Italic;
            _bark.gameObject.SetActive(false);
        }

        // =========================================================================================
        // Public API used by the controller
        // =========================================================================================

        /// <summary>World-space position of the Spark counter (where coins fly).</summary>
        public Vector2 SparkTargetWorld()
        {
            if (_sparkIcon == null || _ctl.Rig == null) return Vector2.zero;
            var corners = new Vector3[4];
            _sparkIcon.GetWorldCorners(corners);
            Vector2 screen = (corners[0] + corners[2]) * 0.5f;   // overlay canvas: world = screen pixels
            return _ctl.Rig.ScreenToWorld(screen);
        }

        public void CoinArrived()
        {
            _sparkPunch.Play(0.12f);
        }

        public void Announce(string text, Color color, float seconds = 2.2f, bool big = false)
        {
            if (string.IsNullOrEmpty(text)) return;
            foreach (var b in _banners) if (b.text == text) return;
            if (_banners.Count > 4) _banners.Dequeue();
            _banners.Enqueue((text, color, seconds, big));
        }

        public void Flash(float strength = 0.35f)
        {
            if (GameApp.I != null && GameApp.I.Meta != null && !GameApp.I.Meta.Data.settings.flashes) return;
            _flashT = Mathf.Max(_flashT, Mathf.Clamp01(strength));
        }

        /// <summary>
        /// Queues a tutorial hint that has not been seen on this profile yet. It counts as seen
        /// only once it is actually on screen (RefreshHint), so a battle that ends first, or a
        /// modal that covers it, never uses it up.
        /// </summary>
        public void ShowHint(string key)
        {
            var app = GameApp.I;
            if (app == null || app.Meta == null) return;
            if (app.Meta.Data.tutorial.hintsShown.Contains(key) || _hints.Contains(key) || _hintKey == key) return;
            _hints.Add(key);
        }

        /// <summary>The player tapped something to ask what it is: show this next, even if seen before.</summary>
        private void ShowHintNow(string key)
        {
            _hints.Remove(key);
            _hints.Insert(0, key);
            if (_hint.gameObject.activeSelf) HideHint();
        }

        private void HideHint()
        {
            _hint.gameObject.SetActive(false);
            _hintT = 0f;
            _hintKey = null;
        }

        public void Bark(string text)
        {
            if (string.IsNullOrEmpty(text)) return;
            _barkText.text = "“" + text + "”";
            _barkT = 2.8f;
            _bark.gameObject.SetActive(true);
            PlaceBark();
        }

        public void SetAiming(bool aiming)
        {
            _aimBar.gameObject.SetActive(aiming);
            if (!aiming) return;
            HideTooltip();
            // The hint sits where the aim bar goes. Put it back at the front of the queue so it
            // returns once aiming ends, and keep the aim bar on top.
            if (_hint.gameObject.activeSelf)
            {
                string key = _hintKey;
                HideHint();
                if (key != null) _hints.Insert(0, key);
            }
            _aimBar.SetAsLastSibling();
        }

        public void SetAimInfo(int targets, bool valid)
        {
            _aimText.text = L.T("ability.aim") + "\n<color=#" + (valid ? "62eeff" : "ff5d5d") + ">" + L.F("ui.storm_targets", ("n", targets)) + "</color>";
        }

        public void PunchUpgrade(string id)
        {
            foreach (var u in _upgrades) if (u.id == id) u.punch.Play(0.15f);
        }

        public void PunchAbility(bool storm) => (storm ? _storm : _ward).punch.Play(0.15f);

        // ---- tooltips ------------------------------------------------------------------------------
        private void ShowTooltip(string title, string body)
        {
            _tooltipTitle.text = title;
            _tooltipBody.text = body;
            _tooltip.gameObject.SetActive(true);
            _tooltip.SetAsLastSibling();
            float h = Mathf.Clamp(46f + _tooltipBody.GetPreferredValues(body, 316f, 0f).y, 70f, 220f);
            _tooltip.sizeDelta = new Vector2(340f, h);
        }

        private void HideTooltip()
        {
            if (_tooltip != null) _tooltip.gameObject.SetActive(false);
        }

        private void ShowAbilityInfo(bool storm)
        {
            var ab = B.Stats.abilities;
            if (storm)
            {
                string desc = StringTable.Fill(L.T("ability.arc_storm.desc"), new Dictionary<string, string>
                {
                    { "targets", ab.stormTargets.ToString() },
                    { "mult", TextFormat.Number(ab.stormDamageMult) },
                });
                ShowTooltip(L.T("ability.arc_storm.name"), desc + "\n" + L.T("stat.damage") + ": " + TextFormat.Number(Mathf.Round(B.Stats.hero.damage * ab.stormDamageMult * 10f) / 10f)
                    + "   " + L.T("stat.radius") + ": " + TextFormat.Number(ab.stormRadius) + "   " + TextFormat.Number(ab.stormCooldown) + "s");
            }
            else
            {
                string desc = StringTable.Fill(L.T("ability.ward.desc"), new Dictionary<string, string>
                {
                    { "pct", TextFormat.Percent(ab.wardFraction * B.Stats.citadel.barrierMult) },
                    { "duration", TextFormat.Number(ab.wardDuration) },
                });
                ShowTooltip(L.T("ability.ward.name"), desc + "\n" + L.T("ui.barrier") + ": " + Mathf.RoundToInt(B.MaxHp * ab.wardFraction * B.Stats.citadel.barrierMult)
                    + "   " + TextFormat.Number(ab.wardCooldown) + "s");
            }
        }

        private void ShowUpgradeInfo(RunUpgradeDef def)
        {
            int lvl = B.UpgradeLevel(def.id);
            string name = L.T("upgrade." + def.id + ".name");
            string body = L.T("upgrade." + def.id + ".desc") + "\n" + L.F("upgrade.level", ("n", lvl), ("max", def.maxLevel));
            string now = UpgradeValue(def.id, lvl);
            if (lvl < def.maxLevel)
            {
                string next = UpgradeValue(def.id, lvl + 1);
                body += "   " + L.F("upgrade.now_next", ("now", now), ("next", next));
                body += "\n" + L.T("ui.buy") + ": " + B.UpgradeCost(def.id) + " " + L.T("ui.sparks");
            }
            else body += "   " + now + "  (" + L.T("upgrade.max") + ")";
            ShowTooltip(name, body);
        }

        /// <summary>The real stat an upgrade changes, computed with the same StatsBuilder as the simulation.</summary>
        private string UpgradeValue(string id, int level)
        {
            var levels = new Dictionary<string, int>();
            foreach (var kv in B.UpgradeLevels) levels[kv.Key] = kv.Value;
            levels[id] = level;
            var perks = new Dictionary<string, int>();
            foreach (var kv in B.PerkStacks) perks[kv.Key] = kv.Value;
            var d = StatsBuilder.Build(B.C, new StatSources
            {
                loadout = new Dictionary<string, string>(B.Loadout),
                upgradeLevels = levels,
                perkStacks = perks,
                nodeLevels = B.Setup.nodeLevels,
                moduleTiers = B.Setup.moduleTiers,
                ignorePermanent = B.Setup.ignorePermanent,
            });
            switch (id)
            {
                case "damage": return TextFormat.Number(Mathf.Round(d.hero.damage * 10f) / 10f);
                case "attack_speed": return TextFormat.Number(Mathf.Round(100f / d.hero.interval) / 100f) + "/s";
                case "max_health": return TextFormat.Number(Mathf.Round(d.citadel.maxHealth));
                case "regen": return TextFormat.Number(Mathf.Round(d.citadel.regen * 10f) / 10f) + "/s";
                case "crit": return TextFormat.Percent(d.hero.critChance);
                case "collection": return TextFormat.Percent(d.econ.sparkGain);
                default: return level.ToString();
            }
        }

        private void ToggleSynergyInfo()
        {
            if (_tooltip.gameObject.activeSelf) { HideTooltip(); return; }
            var active = StatsBuilder.ActiveSynergies(B.C, new Dictionary<string, string>(B.Loadout));
            if (active.Count == 0)
            {
                ShowTooltip(L.T("ui.synergies"), L.T("ui.no_synergy"));
                return;
            }
            var sb = new System.Text.StringBuilder();
            foreach (var syn in active)
            {
                if (sb.Length > 0) sb.Append("\n\n");
                sb.Append("<b>").Append(L.T("synergy." + syn.id + ".name")).Append("</b>\n");
                sb.Append(TextFormat.Fill(L.T("synergy." + syn.id + ".desc"), null, syn.mods, new Dictionary<string, string> { { "value", TextFormat.Percent(syn.value) } }));
            }
            ShowTooltip(L.T("ui.synergy_active"), sb.ToString());
        }

        // =========================================================================================
        // Per-frame refresh
        // =========================================================================================
        private void Update()
        {
            if (_ctl == null || B == null) return;
            float dt = Time.unscaledDeltaTime;
            RefreshTop();
            RefreshBoss();
            RefreshDock();
            RefreshOverlays(dt);
            RefreshBanner(dt);
            RefreshHint(dt);
            if (_barkT > 0f)
            {
                _barkT -= dt;
                PlaceBark();
                if (_barkT <= 0f) _bark.gameObject.SetActive(false);
            }
            UpdateReservedArea();
        }

        private void RefreshTop()
        {
            int hp = Mathf.CeilToInt(Mathf.Max(0f, B.Hp)), max = Mathf.RoundToInt(B.MaxHp), barrier = Mathf.RoundToInt(B.BarrierTotal);
            if (hp != _lastHp || max != _lastMax || barrier != _lastBarrier)
            {
                _lastHp = hp; _lastMax = max; _lastBarrier = barrier;
                _hp.Set(B.Hp / Mathf.Max(1f, B.MaxHp), Mathf.Min(1f, B.BarrierTotal / Mathf.Max(1f, B.MaxHp)));
                _hpText.text = barrier > 0 ? hp + " / " + max + "  <color=#c8f6ff>+" + barrier + "</color>" : hp + " / " + max;
            }
            int sparks = B.Sparks;
            if (sparks != _lastSparks)
            {
                _lastSparks = sparks;
                _sparksText.text = TextFormat.Compact(sparks);
            }
            if (B.Wave != _lastWave)
            {
                _lastWave = B.Wave;
                int shownWave = Mathf.Max(1, B.Wave);
                _waveText.text = B.Spec.totalWaves > 0
                    ? L.F("announce.wave_of", ("n", shownWave), ("total", B.Spec.totalWaves))
                    : L.F("announce.wave", ("n", shownWave));
            }
            int sub;
            string subText;
            if (!B.WaveActive && B.NextWaveIn > 0f && !B.IsOver)
            {
                sub = -1000 - Mathf.CeilToInt(B.NextWaveIn);
                subText = L.F("ui.next_wave_in", ("s", Mathf.CeilToInt(B.NextWaveIn)));
            }
            else
            {
                sub = B.AliveCount + B.PendingSpawns;
                subText = L.F("ui.enemies_left", ("n", sub));
            }
            if (sub != _lastSub) { _lastSub = sub; _waveSub.text = subText; }
            if (B.Level != _lastLevel)
            {
                _lastLevel = B.Level;
                _levelText.text = L.F("ui.level_short", ("n", B.Level));
            }
            _xp.Set(B.XpNeeded > 0f ? B.Xp / B.XpNeeded : 0f);
            string speed = _ctl.Speed + "x";
            if (_speedText != null && _speedText.text != speed) _speedText.text = speed;
        }

        private void RefreshBoss()
        {
            var boss = B.ActiveBoss;
            bool show = boss != null && boss.alive;
            if (_boss.gameObject.activeSelf != show) _boss.gameObject.SetActive(show);
            if (!show) { _bossShown = null; return; }
            if (_bossShown != boss.typeId)
            {
                _bossShown = boss.typeId;
                _bossName.text = L.T("boss." + boss.typeId + ".name");
                _bossIcon.sprite = UI.S("icon/enemy/" + boss.typeId);
            }
            string status = "";
            float extra = 0f;
            var b = boss.boss;
            if (boss.shieldTime > 0f) status = L.T("ui.boss_shielded");
            if (b != null && b.activeAbility >= 0 && boss.bossDef != null && b.activeAbility < boss.bossDef.abilities.Count)
            {
                var a = boss.bossDef.abilities[b.activeAbility];
                if (a.type == "volley" && b.abilityStage == 1)
                {
                    float need = (a.p != null && a.p.TryGetValue("staggerFraction", out var f) ? f : 0.08f) * boss.maxHp;
                    status = L.F("ui.stagger", ("n", Mathf.RoundToInt(b.staggerDamage)), ("max", Mathf.RoundToInt(need)));
                    extra = need > 0f ? Mathf.Clamp01(b.staggerDamage / need) : 0f;
                }
            }
            else if (b != null && b.phase > 1 && status.Length == 0) status = L.F("ui.phase", ("n", b.phase));
            _bossStatus.text = status;
            _bossBar.Set(boss.HealthFraction, extra);
        }

        private void RefreshDock()
        {
            RefreshAbility(_storm, B.StormCooldown, B.StormCooldownTotal, true);
            RefreshAbility(_ward, B.WardCooldown, B.WardCooldownTotal, false);
            if (B.Priority != _lastPriority)
            {
                _lastPriority = B.Priority;
                string key = B.Priority == TargetPriority.Nearest ? "nearest" : B.Priority == TargetPriority.Strongest ? "strongest" : "rangedThreat";
                _targetText.text = L.T("priority." + key);
                _targetIcon.sprite = UI.S(B.Priority == TargetPriority.Nearest ? "icon/target_nearest" : B.Priority == TargetPriority.Strongest ? "icon/target_strongest" : "icon/target_ranged");
                RefreshSynergy();
            }
            int sparks = B.Sparks;
            foreach (var u in _upgrades)
            {
                int lvl = B.UpgradeLevel(u.id);
                bool maxed = lvl >= u.def.maxLevel;
                int cost = maxed ? 0 : B.UpgradeCost(u.id);
                int state = maxed ? 2 : (sparks >= cost ? 1 : 0);
                if (lvl == u.lastLevel && cost == u.lastCost && state == u.lastState) continue;
                u.lastLevel = lvl; u.lastCost = cost; u.lastState = state;
                u.level.text = lvl + "/" + u.def.maxLevel;
                u.cost.text = maxed ? L.T("upgrade.max") : TextFormat.Compact(cost);
                u.cost.color = state == 2 ? Theme.Green : state == 1 ? Theme.Gold : Theme.Red;
                u.coin.enabled = !maxed;
                u.icon.color = state == 0 ? new Color(1f, 1f, 1f, 0.5f) : Color.white;
                u.frame.color = state == 1 ? Color.white : new Color(0.75f, 0.72f, 0.8f, 1f);
            }
        }

        public void RefreshSynergy()
        {
            var active = StatsBuilder.ActiveSynergies(B.C, new Dictionary<string, string>(B.Loadout));
            if (active.Count == 0) { _synergyText.text = L.T("ui.synergies") + ": 0"; _synergyText.color = Theme.TextMuted; return; }
            var names = new List<string>();
            foreach (var s in active) names.Add(L.T("synergy." + s.id + ".name"));
            _synergyText.text = string.Join("\n", names);
            _synergyText.color = Theme.Gold;
        }

        private void RefreshAbility(AbilityButton ab, float cd, float total, bool storm)
        {
            bool ready = cd <= 0.01f && !B.IsOver;
            float frac = total > 0f ? Mathf.Clamp01(cd / total) : 0f;
            ab.cooldown.fillAmount = frac;
            ab.cooldown.enabled = !ready;
            string t = ready ? "" : Mathf.CeilToInt(cd).ToString();
            if (ab.timer.text != t) ab.timer.text = t;
            var g = ab.glow.color;
            g.a = ready ? 0.45f + 0.35f * Mathf.Sin(Time.unscaledTime * 4f) : 0f;
            if (storm && _ctl.Aiming) g.a = 1f;
            ab.glow.color = g;
            ab.icon.color = new Color(ab.icon.color.r, ab.icon.color.g, ab.icon.color.b, ready ? 1f : 0.45f);
            if (ready && !ab.wasReady) ab.punch.Play(0.12f);
            ab.wasReady = ready;
        }

        private void RefreshOverlays(float dt)
        {
            float frac = B.MaxHp > 0f ? B.Hp / B.MaxHp : 1f;
            bool flashes = GameApp.I == null || GameApp.I.Meta == null || GameApp.I.Meta.Data.settings.flashes;
            float target = frac < 0.3f && !B.IsOver ? (flashes ? 0.35f + 0.2f * Mathf.Sin(Time.unscaledTime * 5f) : 0.3f) * (1f - frac / 0.3f + 0.3f) : 0f;
            var c = _vignette.color;
            c.a = Mathf.MoveTowards(c.a, Mathf.Clamp01(target), dt * 2f);
            _vignette.color = c;
            if (_flashT > 0f)
            {
                _flashT = Mathf.Max(0f, _flashT - dt * 2.5f);
                _flash.color = new Color(1f, 1f, 1f, _flashT);
            }
            else if (_flash.color.a > 0f) _flash.color = new Color(1f, 1f, 1f, 0f);
        }

        private void RefreshBanner(float dt)
        {
            if (_bannerT <= 0f && _banners.Count > 0)
            {
                var (text, color, time, big) = _banners.Dequeue();
                _banner.text = text;
                _banner.color = color;
                _banner.fontSizeMax = big ? Theme.FontTitle : Theme.FontH2;
                _bannerT = _bannerDur = time;
            }
            if (_bannerT > 0f)
            {
                _bannerT -= dt;
                float t = 1f - _bannerT / _bannerDur;
                _banner.alpha = t < 0.12f ? t / 0.12f : (_bannerT < 0.35f ? Mathf.Clamp01(_bannerT / 0.35f) : 1f);
                _banner.rectTransform.localScale = Vector3.one * (t < 0.12f ? Mathf.Lerp(1.25f, 1f, t / 0.12f) : 1f);
            }
            else if (_banner.alpha > 0f) _banner.alpha = 0f;
        }

        private void RefreshHint(float dt)
        {
            // A modal (perk choice, pause, boss intro) covers the HUD: wait, and do not let an
            // uncovered hint time out behind it.
            bool covered = _ctl.Aiming || (_ctl.Modals != null && _ctl.Modals.IsOpen);
            if (_hint.gameObject.activeSelf)
            {
                if (covered) return;
                _hintT += dt;
                if (_hintT > 9f) HideHint();
                return;
            }
            if (_hints.Count == 0 || covered || _tooltip.gameObject.activeSelf) return;
            _hintKey = _hints[0];
            _hints.RemoveAt(0);
            var app = GameApp.I;
            if (app != null && app.Meta != null && !app.Meta.Data.tutorial.hintsShown.Contains(_hintKey))
                app.Meta.Data.tutorial.hintsShown.Add(_hintKey);
            _hintText.text = L.T(_hintKey);
            _hintT = 0f;
            _hint.gameObject.SetActive(true);
            _hint.SetAsLastSibling();
        }

        private void PlaceBark()
        {
            if (_ctl.View == null || _ctl.Rig == null) return;
            Vector2 screen = _ctl.Rig.WorldToScreen(_ctl.View.HeroPos + new Vector2(0f, 3.4f));
            if (RectTransformUtility.ScreenPointToLocalPointInRectangle(_root, screen, null, out var local))
                _bark.anchoredPosition = local;
            var c = _barkText.color;
            c.a = Mathf.Clamp01(_barkT / 0.3f);
            _barkText.color = c;
        }

        /// <summary>Tells the camera how much of the screen the top bar and dock cover (real pixels).</summary>
        private void UpdateReservedArea()
        {
            if (_ctl.Rig == null) return;
            var corners = new Vector3[4];
            float top = 0f, bottom = 0f;
            var topRt = _boss.gameObject.activeSelf ? _boss : _top;
            topRt.GetWorldCorners(corners);
            top = Mathf.Max(0f, Screen.height - corners[0].y);
            _dock.GetWorldCorners(corners);
            bottom = Mathf.Max(0f, corners[1].y);
            // hysteresis: the boss bar toggling must not make the camera jump every frame
            if (Mathf.Abs(top - _reservedTop) > 2f || Mathf.Abs(bottom - _reservedBottom) > 2f)
            {
                _reservedTop = top;
                _reservedBottom = bottom;
                _ctl.Rig.SetReserved(top, bottom);
            }
        }

        // =========================================================================================
        // Battlefield input: aiming Arc Storm, or tapping an enemy for a short description
        // =========================================================================================
        internal void BattlefieldDown(Vector2 screen)
        {
            if (_ctl.Aiming) _ctl.AimAt(_ctl.Rig.ScreenToWorld(screen), false);
        }

        internal void BattlefieldDrag(Vector2 screen)
        {
            if (_ctl.Aiming) _ctl.AimAt(_ctl.Rig.ScreenToWorld(screen), false);
        }

        /// <summary>Finger/mouse released over the battlefield. While aiming this strikes; otherwise a
        /// tap (not a drag) on an enemy shows what it is and how to counter it.</summary>
        internal void BattlefieldRelease(Vector2 screen, bool dragged)
        {
            HideTooltip();
            Vector2 world = _ctl.Rig.ScreenToWorld(screen);
            if (_ctl.Aiming)
            {
                _ctl.AimAt(world, true);
                return;
            }
            if (dragged) return;
            // tap an enemy: name + how to counter it
            Enemy best = null;
            float bestD = 1.1f * 1.1f;
            foreach (var e in B.Enemies)
            {
                if (!e.alive) continue;
                var v = _ctl.View.Units.Get(e.uid);
                Vector2 p = v != null ? v.Position + new Vector2(0f, 0.4f) : new Vector2(e.pos.x, e.pos.y);
                float d = (p - world).sqrMagnitude;
                if (d < bestD) { bestD = d; best = e; }
            }
            if (best == null) return;
            string id = best.isBoss ? best.typeId : (best.def != null && best.typeId == "bat" ? "bat_swarm" : best.typeId);
            string name = best.isBoss ? L.T("boss." + id + ".name") : L.T("enemy." + id + ".name");
            string desc = best.isBoss ? L.T("boss." + id + ".hint") : L.T("enemy." + id + ".desc");
            string hp = Mathf.CeilToInt(best.hp) + " / " + Mathf.CeilToInt(best.maxHp);
            ShowTooltip(best.elite ? L.F("ui.elite_name", ("name", name)) : name, L.T("ui.hp") + ": " + hp + "\n" + desc);
        }

        public bool Back()
        {
            if (_tooltip.gameObject.activeSelf) { HideTooltip(); return true; }
            if (_hint.gameObject.activeSelf) { HideHint(); return true; }
            return false;
        }
    }

    /// <summary>Receives pointer events that reach the battlefield (no HUD widget was hit).</summary>
    public sealed class BattlefieldInput : MonoBehaviour, IPointerDownHandler, IPointerUpHandler, IDragHandler, IBeginDragHandler
    {
        public BattleHud Hud;
        private bool _dragged;

        public void OnPointerDown(PointerEventData e)
        {
            _dragged = false;
            Hud.BattlefieldDown(e.position);
        }

        public void OnBeginDrag(PointerEventData e)
        {
            _dragged = true;
            Hud.BattlefieldDrag(e.position);
        }

        public void OnDrag(PointerEventData e) => Hud.BattlefieldDrag(e.position);

        public void OnPointerUp(PointerEventData e)
        {
            // only when released over the battlefield itself (not over the dock or a button)
            if (e.pointerCurrentRaycast.gameObject != gameObject) return;
            Hud.BattlefieldRelease(e.position, _dragged);
        }
    }
}
