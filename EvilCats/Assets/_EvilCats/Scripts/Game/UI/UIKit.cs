using System;
using System.Collections.Generic;
using EvilCats.Content;
using TMPro;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;
#if ENABLE_INPUT_SYSTEM && EC_INPUT_SYSTEM_PACKAGE
using UnityEngine.InputSystem.UI;
#endif

namespace EvilCats.Game
{
    /// <summary>Localised text lookup. All player-facing strings live in Data/.../strings_en.json.</summary>
    public static class L
    {
        private static StringTable _t;
        public static void Use(StringTable t) => _t = t;
        public static string T(string key) => _t != null ? _t.Get(key) : "[" + key + "]";
        public static bool Has(string key) => _t != null && _t.Has(key);

        public static string F(string key, params (string name, object value)[] args)
        {
            var d = new Dictionary<string, string>(args.Length);
            foreach (var a in args) d[a.name] = a.value is float f ? TextFormat.Number(f) : Convert.ToString(a.value, System.Globalization.CultureInfo.InvariantCulture);
            return StringTable.Fill(T(key), d);
        }
    }

    /// <summary>Colours, sizes and spacing shared by every screen (one consistent spacing system).</summary>
    public static class Theme
    {
        public static readonly Color Bg = Hex("0d0914");
        public static readonly Color Text = Hex("f1ecfb");
        public static readonly Color TextDim = Hex("b9aed3");
        public static readonly Color TextMuted = Hex("7f7499");
        public static readonly Color Gold = Hex("ffd24a");
        public static readonly Color Cyan = Hex("62eeff");
        public static readonly Color Violet = Hex("a57ad6");
        public static readonly Color Red = Hex("ff5d5d");
        public static readonly Color Green = Hex("8be38f");
        public static readonly Color Barrier = Hex("c8f6ff");
        public static readonly Color Health = Hex("e8434f");
        public static readonly Color Overlay = new Color(0.03f, 0.02f, 0.06f, 0.78f);

        public const float S1 = 4f, S2 = 8f, S3 = 12f, S4 = 16f, S6 = 24f;
        public const float Touch = 48f;             // minimum touch target (UI units ≈ dp)
        public const float FontTitle = 30f, FontH1 = 22f, FontH2 = 18f, FontBody = 14f, FontSmall = 12f, FontTiny = 10f;

        public static Color Hex(string h)
        {
            ColorUtility.TryParseHtmlString("#" + h, out var c);
            return c;
        }

        public static Color Family(string family)
        {
            switch (family)
            {
                case "arc": return Hex("62eeff");
                case "ember": return Hex("ff9a3c");
                case "frost": return Hex("a9e6ff");
                case "bone": return Hex("e8dcc0");
                case "ward": return Hex("8fe6c4");
                case "gravity": return Hex("b98bff");
                default: return Text;
            }
        }
    }

    public enum ButtonStyle { Normal, Primary, Danger, Ghost }

    /// <summary>Ignores repeated taps for a short time (rapid-tap protection on top of idempotent claims).</summary>
    public sealed class TapGuard : MonoBehaviour
    {
        public float Cooldown = 0.3f;
        private float _last = -10f;

        public bool Allow()
        {
            if (Time.unscaledTime - _last < Cooldown) return false;
            _last = Time.unscaledTime;
            return true;
        }
    }

    /// <summary>Keeps a RectTransform inside Screen.safeArea (notches, rounded corners, gesture bars).</summary>
    public sealed class SafeAreaFitter : MonoBehaviour
    {
        private Rect _last;
        private Vector2Int _lastScreen;

        private void OnEnable() => Apply();

        private void Update()
        {
            if (Screen.safeArea != _last || _lastScreen.x != Screen.width || _lastScreen.y != Screen.height) Apply();
        }

        private void Apply()
        {
            var rt = (RectTransform)transform;
            var sa = Screen.safeArea;
            _last = sa;
            _lastScreen = new Vector2Int(Screen.width, Screen.height);
            if (Screen.width <= 0 || Screen.height <= 0) return;
            rt.anchorMin = new Vector2(sa.xMin / Screen.width, sa.yMin / Screen.height);
            rt.anchorMax = new Vector2(sa.xMax / Screen.width, sa.yMax / Screen.height);
            rt.offsetMin = rt.offsetMax = Vector2.zero;
        }
    }

    /// <summary>
    /// Portrait phones: 360 reference units across (≈ dp). Wider screens (tablets) match height
    /// instead so the layout is not stretched; content is capped in width by ContentWidth.
    /// </summary>
    public sealed class AdaptiveScaler : MonoBehaviour
    {
        private CanvasScaler _scaler;
        private float _lastAspect;

        private void Awake() => _scaler = GetComponent<CanvasScaler>();

        private void Update()
        {
            float aspect = Screen.height > 0 ? (float)Screen.width / Screen.height : 0.5625f;
            if (Mathf.Abs(aspect - _lastAspect) < 0.0005f) return;
            _lastAspect = aspect;
            _scaler.matchWidthOrHeight = aspect > 0.6f ? 1f : 0f;
        }
    }

    /// <summary>UI construction helpers. Every screen is built from these, so style stays consistent.</summary>
    public static class UI
    {
        public static TMP_FontAsset Font;
        public static TMP_FontAsset FontBold;

        public static SpriteLibrary Sprites => GameApp.I != null ? GameApp.I.Sprites : null;

        public static Sprite S(string name) => Sprites != null ? Sprites.Get(name) : null;

        // ---- canvas / event system --------------------------------------------------------------
        public static RectTransform CreateCanvas(string name, int sortingOrder, out Canvas canvas)
        {
            EnsureEventSystem();
            var go = new GameObject(name, typeof(RectTransform));
            canvas = go.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = sortingOrder;
            canvas.pixelPerfect = false;
            var scaler = go.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(360f, 640f);
            scaler.screenMatchMode = CanvasScaler.ScreenMatchMode.MatchWidthOrHeight;
            scaler.referencePixelsPerUnit = 100f;
            go.AddComponent<AdaptiveScaler>();
            go.AddComponent<GraphicRaycaster>();
            var safe = Rect(go.transform, "SafeArea");
            Stretch(safe);
            safe.gameObject.AddComponent<SafeAreaFitter>();
            return safe;
        }

        public static void EnsureEventSystem()
        {
            if (EventSystem.current != null) return;
            var go = new GameObject("EventSystem");
            go.AddComponent<EventSystem>();
#if ENABLE_INPUT_SYSTEM && EC_INPUT_SYSTEM_PACKAGE
            go.AddComponent<InputSystemUIInputModule>();   // default UI actions are assigned automatically
#else
            go.AddComponent<StandaloneInputModule>();       // only if the Input System backend is not active yet
#endif
        }

        public static void EnsureFonts()
        {
            if (Font != null) return;
            Font = Resources.Load<TMP_FontAsset>("ECUI/Fonts/PixelifySans-Regular SDF");
            FontBold = Resources.Load<TMP_FontAsset>("ECUI/Fonts/PixelifySans-Bold SDF");
            if (Font == null)
            {
                // Setup not run yet: build a dynamic font asset from the TTF at runtime.
                var ttf = Resources.Load<UnityEngine.Font>("ECUI/Fonts/PixelifySans-Regular");
                if (ttf != null) Font = TMP_FontAsset.CreateFontAsset(ttf);
                if (Font == null) Font = TMP_Settings.defaultFontAsset;
            }
            if (FontBold == null)
            {
                var ttfB = Resources.Load<UnityEngine.Font>("ECUI/Fonts/PixelifySans-Bold");
                FontBold = ttfB != null ? TMP_FontAsset.CreateFontAsset(ttfB) : Font;
                if (FontBold == null) FontBold = Font;
            }
        }

        // ---- rect helpers ----------------------------------------------------------------------------
        public static RectTransform Rect(Transform parent, string name)
        {
            var go = new GameObject(name, typeof(RectTransform));
            var rt = (RectTransform)go.transform;
            rt.SetParent(parent, false);
            return rt;
        }

        public static RectTransform Stretch(RectTransform rt, float left = 0, float top = 0, float right = 0, float bottom = 0)
        {
            rt.anchorMin = Vector2.zero;
            rt.anchorMax = Vector2.one;
            rt.pivot = new Vector2(0.5f, 0.5f);
            rt.offsetMin = new Vector2(left, bottom);
            rt.offsetMax = new Vector2(-right, -top);
            return rt;
        }

        /// <summary>Anchor to a point/edge. anchor (0..1), pivot (0..1), position offset and size.</summary>
        public static RectTransform Place(RectTransform rt, Vector2 anchor, Vector2 pivot, Vector2 pos, Vector2 size)
        {
            rt.anchorMin = rt.anchorMax = anchor;
            rt.pivot = pivot;
            rt.anchoredPosition = pos;
            rt.sizeDelta = size;
            return rt;
        }

        /// <summary>Full-width strip anchored to the top (fromTop=true) or bottom edge.</summary>
        public static RectTransform Strip(RectTransform rt, bool fromTop, float height, float offset = 0f)
        {
            rt.anchorMin = new Vector2(0f, fromTop ? 1f : 0f);
            rt.anchorMax = new Vector2(1f, fromTop ? 1f : 0f);
            rt.pivot = new Vector2(0.5f, fromTop ? 1f : 0f);
            rt.anchoredPosition = new Vector2(0f, fromTop ? -offset : offset);
            rt.sizeDelta = new Vector2(0f, height);
            return rt;
        }

        public static LayoutElement Size(Component c, float prefW = -1, float prefH = -1, float flexW = -1, float flexH = -1, float minH = -1)
        {
            var le = c.GetComponent<LayoutElement>() ?? c.gameObject.AddComponent<LayoutElement>();
            le.preferredWidth = prefW;
            le.preferredHeight = prefH;
            le.flexibleWidth = flexW;
            le.flexibleHeight = flexH;
            if (minH >= 0) le.minHeight = minH;
            return le;
        }

        public static VerticalLayoutGroup VLayout(Component c, float spacing = Theme.S2, float pad = 0f, TextAnchor align = TextAnchor.UpperCenter, bool expandW = true)
        {
            var g = c.gameObject.AddComponent<VerticalLayoutGroup>();
            g.spacing = spacing;
            g.padding = new RectOffset((int)pad, (int)pad, (int)pad, (int)pad);
            g.childAlignment = align;
            g.childControlWidth = true;
            g.childControlHeight = true;
            g.childForceExpandWidth = expandW;
            g.childForceExpandHeight = false;
            return g;
        }

        public static HorizontalLayoutGroup HLayout(Component c, float spacing = Theme.S2, float pad = 0f, TextAnchor align = TextAnchor.MiddleCenter, bool expandW = true)
        {
            var g = c.gameObject.AddComponent<HorizontalLayoutGroup>();
            g.spacing = spacing;
            g.padding = new RectOffset((int)pad, (int)pad, (int)pad, (int)pad);
            g.childAlignment = align;
            g.childControlWidth = true;
            g.childControlHeight = true;
            g.childForceExpandWidth = expandW;
            g.childForceExpandHeight = false;
            return g;
        }

        public static ContentSizeFitter FitHeight(Component c)
        {
            var f = c.gameObject.AddComponent<ContentSizeFitter>();
            f.verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            f.horizontalFit = ContentSizeFitter.FitMode.Unconstrained;
            return f;
        }

        // ---- graphics ----------------------------------------------------------------------------------
        public static Image Img(Transform parent, string sprite, Color? color = null, bool raycast = false, string name = null)
        {
            var rt = Rect(parent, name ?? ("Img " + sprite));
            var img = rt.gameObject.AddComponent<Image>();
            img.sprite = sprite != null ? S(sprite) : null;
            img.color = color ?? Color.white;
            img.raycastTarget = raycast;
            if (img.sprite != null && img.sprite.border != Vector4.zero) img.type = Image.Type.Sliced;
            img.preserveAspect = img.type != Image.Type.Sliced && img.sprite != null;
            return img;
        }

        /// <summary>Solid colour block (uses the 4x4 white UI sprite, or none).</summary>
        public static Image Block(Transform parent, Color color, bool raycast = false, string name = "Block")
        {
            var rt = Rect(parent, name);
            var img = rt.gameObject.AddComponent<Image>();
            var white = Sprites != null ? Sprites.TryGet("ui/white") : null;
            img.sprite = white;
            img.color = color;
            img.raycastTarget = raycast;
            return img;
        }

        public static Image Panel(Transform parent, string sprite = "ui/panel", string name = "Panel", Color? tint = null)
        {
            var img = Img(parent, sprite, tint, true, name);
            img.type = Image.Type.Sliced;
            img.preserveAspect = false;
            return img;
        }

        public static TextMeshProUGUI Text(Transform parent, string text, float size = Theme.FontBody, Color? color = null,
            TextAlignmentOptions align = TextAlignmentOptions.Center, bool bold = false, string name = "Text")
        {
            EnsureFonts();
            var rt = Rect(parent, name);
            var t = rt.gameObject.AddComponent<TextMeshProUGUI>();
            if (bold && FontBold != null) t.font = FontBold;
            else if (Font != null) t.font = Font;
            t.text = text ?? "";
            t.fontSize = size;
            t.color = color ?? Theme.Text;
            t.alignment = align;
            t.raycastTarget = false;
            t.richText = true;
            t.overflowMode = TextOverflowModes.Ellipsis;
            return t;
        }

        /// <summary>Text that sizes its own height inside a vertical layout.</summary>
        public static TextMeshProUGUI Para(Transform parent, string text, float size = Theme.FontBody, Color? color = null,
            TextAlignmentOptions align = TextAlignmentOptions.TopLeft)
        {
            var t = Text(parent, text, size, color, align);
            t.overflowMode = TextOverflowModes.Overflow;
            var f = t.gameObject.AddComponent<ContentSizeFitter>();
            f.verticalFit = ContentSizeFitter.FitMode.PreferredSize;
            return t;
        }

        public static Image Icon(Transform parent, string icon, float size = 32f, Color? tint = null)
        {
            var img = Img(parent, icon, tint, false, "Icon");
            img.preserveAspect = true;
            Size(img, size, size);
            ((RectTransform)img.transform).sizeDelta = new Vector2(size, size);
            return img;
        }

        // ---- buttons -----------------------------------------------------------------------------------
        public static Button Button(Transform parent, string label, Action onClick, ButtonStyle style = ButtonStyle.Normal,
            string icon = null, float height = Theme.Touch, float fontSize = Theme.FontH2, string sound = "ui_click")
        {
            string sprite = style == ButtonStyle.Primary ? "ui/button_gold" : style == ButtonStyle.Danger ? "ui/button_red" : "ui/button";
            var bg = Img(parent, style == ButtonStyle.Ghost ? null : sprite, style == ButtonStyle.Ghost ? new Color(1, 1, 1, 0.001f) : (Color?)null, true, "Button " + label);
            bg.type = Image.Type.Sliced;
            bg.preserveAspect = false;
            var btn = bg.gameObject.AddComponent<Button>();
            btn.targetGraphic = bg;
            if (style != ButtonStyle.Ghost && Sprites != null)
            {
                btn.transition = Selectable.Transition.SpriteSwap;
                btn.spriteState = new SpriteState
                {
                    pressedSprite = Sprites.TryGet("ui/button_pressed") ?? bg.sprite,
                    highlightedSprite = bg.sprite,
                    selectedSprite = bg.sprite,
                    disabledSprite = Sprites.TryGet("ui/button_disabled") ?? bg.sprite,
                };
            }
            var nav = btn.navigation;
            nav.mode = Navigation.Mode.None;
            btn.navigation = nav;
            var guard = bg.gameObject.AddComponent<TapGuard>();
            btn.onClick.AddListener(() =>
            {
                if (!guard.Allow()) return;
                if (!string.IsNullOrEmpty(sound) && GameApp.I != null && GameApp.I.Audio != null) GameApp.I.Audio.Play(sound);
                onClick?.Invoke();
            });
            Size(bg, -1, height, -1, -1, height);
            var row = Rect(bg.transform, "Row");
            Stretch(row, Theme.S2, 0, Theme.S2, 0);
            var h = HLayout(row, Theme.S1, 0, TextAnchor.MiddleCenter, false);
            h.childControlWidth = true;
            if (!string.IsNullOrEmpty(icon)) Icon(row, icon, Mathf.Min(32f, height - 12f));
            if (!string.IsNullOrEmpty(label))
            {
                var t = Text(row, label, fontSize, style == ButtonStyle.Primary ? Theme.Hex("2b1a05") : Theme.Text, TextAlignmentOptions.Center, true, "Label");
                t.enableAutoSizing = true;
                t.fontSizeMin = 10f;
                t.fontSizeMax = fontSize;
                Size(t, -1, height, 1);
            }
            return btn;
        }

        public static Button IconButton(Transform parent, string icon, Action onClick, float size = Theme.Touch, string sound = "ui_click", string frame = "ui/button")
        {
            var btn = Button(parent, null, onClick, ButtonStyle.Normal, null, size, Theme.FontH2, sound);
            if (frame == null) btn.GetComponent<Image>().color = new Color(1, 1, 1, 0.001f);
            Size(btn, size, size);
            var ic = Icon(btn.transform.Find("Row"), icon, size * 0.62f);
            ic.name = "Icon";
            return btn;
        }

        public static void SetLabel(Button b, string text)
        {
            var t = b.GetComponentInChildren<TextMeshProUGUI>(true);
            if (t != null) t.text = text;
        }

        public static void SetIcon(Button b, string icon)
        {
            var row = b.transform.Find("Row");
            var ic = row != null ? row.Find("Icon") : null;
            if (ic != null) ic.GetComponent<Image>().sprite = S(icon);
        }

        // ---- bars, toggles, sliders, lists ---------------------------------------------------------------
        public sealed class Bar
        {
            public RectTransform root;
            public Image fill;
            public Image extra;   // optional second segment (e.g. barrier on top of health)
            public TextMeshProUGUI label;

            public void Set(float fraction, float extraFraction = 0f)
            {
                fraction = Mathf.Clamp01(fraction);
                SetSpan(fill, 0f, fraction);
                if (extra != null) SetSpan(extra, 0f, Mathf.Clamp01(extraFraction));
            }

            private static void SetSpan(Image img, float from, float to)
            {
                var rt = img.rectTransform;
                rt.anchorMin = new Vector2(from, 0f);
                rt.anchorMax = new Vector2(Mathf.Max(from, to), 1f);
                rt.offsetMin = rt.offsetMax = Vector2.zero;
                img.enabled = to > from + 0.0001f;
            }
        }

        public static Bar ProgressBar(Transform parent, Color fill, float height = 12f, bool withExtra = false, Color? extraColor = null, bool withLabel = false)
        {
            var bg = Img(parent, "ui/bar_bg", null, false, "Bar");
            bg.type = Image.Type.Sliced;
            bg.preserveAspect = false;
            Size(bg, -1, height, -1, -1, height);
            var inner = Rect(bg.transform, "Inner");
            Stretch(inner, 2, 2, 2, 2);
            var f = Img(inner, "ui/bar_fill", fill, false, "Fill");
            f.type = Image.Type.Sliced;
            f.preserveAspect = false;
            var bar = new Bar { root = (RectTransform)bg.transform, fill = f };
            if (withExtra)
            {
                var e = Img(inner, "ui/bar_fill", extraColor ?? Theme.Barrier, false, "Extra");
                e.type = Image.Type.Sliced;
                e.preserveAspect = false;
                bar.extra = e;
            }
            if (withLabel)
            {
                bar.label = Text(bg.transform, "", Mathf.Max(9f, height - 3f), Theme.Text, TextAlignmentOptions.Center, true, "Label");
                Stretch(bar.label.rectTransform);
            }
            bar.Set(1f);
            return bar;
        }

        public static Toggle Toggle(Transform parent, string label, bool value, Action<bool> onChanged)
        {
            var row = Rect(parent, "Toggle " + label);
            Size(row, -1, Theme.Touch, -1, -1, Theme.Touch);
            HLayout(row, Theme.S2, 0, TextAnchor.MiddleLeft, false);
            var t = Text(row, label, Theme.FontBody, Theme.Text, TextAlignmentOptions.MidlineLeft);
            Size(t, -1, Theme.Touch, 1);
            var bg = Img(row, value ? "ui/toggle_on" : "ui/toggle_off", null, true, "Switch");
            Size(bg, 56f, 28f);
            var toggle = bg.gameObject.AddComponent<Toggle>();
            toggle.targetGraphic = bg;
            toggle.isOn = value;
            var state = Text(row, value ? L.T("ui.settings.on") : L.T("ui.settings.off"), Theme.FontSmall, Theme.TextDim, TextAlignmentOptions.MidlineRight);
            Size(state, 44f, Theme.Touch);
            toggle.onValueChanged.AddListener(v =>
            {
                bg.sprite = S(v ? "ui/toggle_on" : "ui/toggle_off");
                state.text = v ? L.T("ui.settings.on") : L.T("ui.settings.off");
                if (GameApp.I != null && GameApp.I.Audio != null) GameApp.I.Audio.Play("ui_toggle");
                onChanged?.Invoke(v);
            });
            return toggle;
        }

        public static Slider Slider(Transform parent, string label, float value, Action<float> onChanged)
        {
            var row = Rect(parent, "Slider " + label);
            Size(row, -1, Theme.Touch, -1, -1, Theme.Touch);
            HLayout(row, Theme.S2, 0, TextAnchor.MiddleLeft, false);
            var t = Text(row, label, Theme.FontBody, Theme.Text, TextAlignmentOptions.MidlineLeft);
            Size(t, 110f, Theme.Touch);
            var sroot = Rect(row, "Track");
            Size(sroot, -1, 28f, 1);
            var bg = Img(sroot, "ui/slider_bg", null, false, "Bg");
            bg.type = Image.Type.Sliced;
            Stretch(bg.rectTransform, 0, 9, 0, 9);
            var fillArea = Rect(sroot, "FillArea");
            Stretch(fillArea, 0, 9, 0, 9);
            var fill = Img(fillArea, "ui/slider_fill", Theme.Cyan, false, "Fill");
            fill.type = Image.Type.Sliced;
            var handleArea = Rect(sroot, "HandleArea");
            Stretch(handleArea, 8, 0, 8, 0);
            var handle = Img(handleArea, "ui/slider_handle", null, true, "Handle");
            handle.rectTransform.sizeDelta = new Vector2(20f, 28f);
            var s = sroot.gameObject.AddComponent<Slider>();
            s.fillRect = fill.rectTransform;
            s.handleRect = handle.rectTransform;
            s.targetGraphic = handle;
            s.direction = UnityEngine.UI.Slider.Direction.LeftToRight;
            s.minValue = 0f;
            s.maxValue = 1f;
            s.value = value;
            var pct = Text(row, Mathf.RoundToInt(value * 100f) + "%", Theme.FontSmall, Theme.TextDim, TextAlignmentOptions.MidlineRight);
            Size(pct, 44f, Theme.Touch);
            s.onValueChanged.AddListener(v =>
            {
                pct.text = Mathf.RoundToInt(v * 100f) + "%";
                onChanged?.Invoke(v);
            });
            return s;
        }

        /// <summary>A vertically scrolling, clearly bounded list. Returns the content transform.</summary>
        public static RectTransform ScrollList(Transform parent, out ScrollRect scroll, float spacing = Theme.S2, float pad = Theme.S2)
        {
            var root = Rect(parent, "Scroll");
            var img = root.gameObject.AddComponent<Image>();
            img.color = new Color(0, 0, 0, 0.001f);   // catches drags on empty space
            scroll = root.gameObject.AddComponent<ScrollRect>();
            scroll.horizontal = false;
            scroll.vertical = true;
            scroll.movementType = ScrollRect.MovementType.Elastic;
            scroll.scrollSensitivity = 30f;
            var viewport = Rect(root, "Viewport");
            Stretch(viewport);
            viewport.gameObject.AddComponent<RectMask2D>();
            var content = Rect(viewport, "Content");
            content.anchorMin = new Vector2(0f, 1f);
            content.anchorMax = new Vector2(1f, 1f);
            content.pivot = new Vector2(0.5f, 1f);
            content.offsetMin = content.offsetMax = Vector2.zero;
            var v = VLayout(content, spacing, pad, TextAnchor.UpperCenter);
            v.childForceExpandWidth = true;
            FitHeight(content);
            scroll.viewport = viewport;
            scroll.content = content;
            return content;
        }

        public static TMP_InputField Input(Transform parent, string text, string placeholder, Action<string> onEnd, int charLimit = 16)
        {
            var bg = Img(parent, "ui/panel_inset", null, true, "Input");
            bg.type = Image.Type.Sliced;
            Size(bg, -1, Theme.Touch, 1, -1, Theme.Touch);
            var area = Rect(bg.transform, "TextArea");
            Stretch(area, 10, 6, 10, 6);
            area.gameObject.AddComponent<RectMask2D>();
            var ph = Text(area, placeholder, Theme.FontBody, Theme.TextMuted, TextAlignmentOptions.MidlineLeft, false, "Placeholder");
            Stretch(ph.rectTransform);
            var tx = Text(area, text, Theme.FontBody, Theme.Text, TextAlignmentOptions.MidlineLeft, false, "Text");
            Stretch(tx.rectTransform);
            var input = bg.gameObject.AddComponent<TMP_InputField>();
            input.textViewport = area;
            input.textComponent = tx;
            input.placeholder = ph;
            input.characterLimit = charLimit;
            input.lineType = TMP_InputField.LineType.SingleLine;
            input.text = text;
            if (Font != null) input.fontAsset = Font;
            input.onEndEdit.AddListener(s => onEnd?.Invoke(s));
            return input;
        }

        public static RectTransform Spacer(Transform parent, float h)
        {
            var r = Rect(parent, "Spacer");
            Size(r, -1, h, -1, -1, h);
            return r;
        }

        public static void Clear(Transform t)
        {
            for (int i = t.childCount - 1; i >= 0; i--) UnityEngine.Object.Destroy(t.GetChild(i).gameObject);
        }

        /// <summary>A full-screen dimmed layer that blocks input to everything behind it (modals).</summary>
        public static RectTransform Blocker(Transform parent, Color? color = null)
        {
            var img = Block(parent, color ?? Theme.Overlay, true, "Blocker");
            Stretch(img.rectTransform);
            return img.rectTransform;
        }
    }
}
