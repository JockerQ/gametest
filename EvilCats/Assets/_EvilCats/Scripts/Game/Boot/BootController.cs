using System.Collections;
using EvilCats.Meta;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

namespace EvilCats.Game
{
    /// <summary>
    /// Boot scene: shows real loading steps, reports save recovery, offers "Continue as Guest"
    /// on first launch, plays the skippable opening story once, then opens the Hub.
    /// </summary>
    public sealed class BootController : SceneController
    {
        private RectTransform _root;
        private TextMeshProUGUI _status;
        private UI.Bar _bar;
        private Image _emblem;
        private bool _advance;
        private bool _skip;

        private void Start()
        {
            var cam = CameraUtil.EnsureCamera(Theme.Bg);
            _root = UI.CreateCanvas("BootCanvas", 0, out _);
            UI.Stretch(UI.Block(_root.parent, Theme.Bg, false, "Bg").rectTransform).SetAsFirstSibling();
            BuildLoadingUi();
            StartCoroutine(Run());
        }

        private void BuildLoadingUi()
        {
            var col = UI.Rect(_root, "Column");
            UI.Place(col, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), new Vector2(0f, 20f), new Vector2(300f, 360f));
            UI.VLayout(col, Theme.S3, 0, TextAnchor.MiddleCenter);
            _emblem = UI.Img(col, null, new Color(1, 1, 1, 0), false, "Emblem");
            UI.Size(_emblem, 128f, 128f);
            _emblem.preserveAspect = true;
            var title = UI.Text(col, "EVIL CATS", 40f, Theme.Cyan, TextAlignmentOptions.Center, true, "Title");
            UI.Size(title, -1, 52f);
            title.outlineWidth = 0.2f;
            title.outlineColor = new Color32(40, 16, 70, 255);
            var sub = UI.Text(col, "Arc Light Cat and the Nine-Lives Citadel", Theme.FontSmall, Theme.TextDim);
            UI.Size(sub, -1, 20f);
            UI.Spacer(col, 20f);
            _bar = UI.ProgressBar(col, Theme.Cyan, 10f);
            _bar.Set(0f);
            _status = UI.Text(col, "Loading", Theme.FontSmall, Theme.TextDim);
            UI.Size(_status, -1, 20f);
            var ver = UI.Text(_root, "v" + GameApp.Version, Theme.FontTiny, Theme.TextMuted, TextAlignmentOptions.BottomRight);
            UI.Place(ver.rectTransform, new Vector2(1f, 0f), new Vector2(1f, 0f), new Vector2(-8f, 6f), new Vector2(120f, 16f));
        }

        private IEnumerator Run()
        {
            var app = GameApp.Ensure();
            yield return app.BootRoutine((i, n, key) =>
            {
                _bar.Set(n > 0 ? (float)i / n : 0f);
                // Before strings are loaded we can only show a neutral word.
                _status.text = L.Has(key) ? L.T(key) + "..." : "Loading...";
                if (_emblem.color.a < 0.5f && app.Sprites != null && app.Sprites.Has("logo/emblem"))
                {
                    _emblem.sprite = app.Sprites.Get("logo/emblem");
                    _emblem.color = Color.white;
                }
            });
            if (!app.IsBooted)
            {
                ShowFatal();
                yield break;
            }
            if (app.Audio != null) app.Audio.PlayMusic("menu", 1.5f);
            _bar.Set(1f);
            _status.text = L.T("ui.boot.done");
            if (app.BootProblems.Count > 0)
                Debug.LogWarning("[EvilCats] Boot finished with problems:\n" + string.Join("\n", app.BootProblems));

            // Save recovery notices (never silently erase progress).
            var outcome = app.SaveLoad != null ? app.SaveLoad.outcome : LoadOutcome.Loaded;
            if (outcome == LoadOutcome.RecoveredFromBackup || outcome == LoadOutcome.ResetAfterCorruption)
            {
                yield return Notice(outcome == LoadOutcome.RecoveredFromBackup ? L.T("ui.error.save_recovered") : L.T("ui.error.save_reset"));
            }

            var data = app.Meta.Data;
            if (!data.tutorial.guestChosen)
            {
                yield return GuestChoice();
                data.tutorial.guestChosen = true;
                app.SaveNow();
            }
            if (!data.tutorial.storySeen)
            {
                yield return Story();
                data.tutorial.storySeen = true;
                app.SaveNow();
            }
            app.GoTo(GameApp.HubScene);
        }

        private void ShowFatal()
        {
            _status.color = Theme.Red;
            string detail = string.Join("\n", GameApp.I.BootProblems);
            _status.text = (L.Has("ui.boot.error") ? L.T("ui.boot.error") : "Something went wrong while loading");
            var box = UI.Panel(_root, "ui/panel");
            UI.Place(box.rectTransform, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 24f), new Vector2(330f, 200f));
            var t = UI.Text(box.transform, detail, Theme.FontTiny, Theme.Text, TextAlignmentOptions.TopLeft);
            UI.Stretch(t.rectTransform, 10, 10, 10, 10);
            t.overflowMode = TextOverflowModes.Truncate;
        }

        private IEnumerator Notice(string message)
        {
            _advance = false;
            var layer = UI.Blocker(_root);
            var box = UI.Panel(layer, "ui/panel");
            UI.Place(box.rectTransform, new Vector2(0.5f, 0.5f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(300f, 190f));
            UI.VLayout(box, Theme.S3, Theme.S4, TextAnchor.MiddleCenter);
            var t = UI.Text(box.transform, message, Theme.FontBody, Theme.Text);
            UI.Size(t, -1, 90f);
            UI.Button(box.transform, L.T("ui.continue"), () => _advance = true, ButtonStyle.Primary);
            while (!_advance) yield return null;
            Destroy(layer.gameObject);
        }

        private IEnumerator GuestChoice()
        {
            _advance = false;
            var panel = UI.Rect(_root, "Guest");
            UI.Place(panel, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 40f), new Vector2(300f, 170f));
            UI.VLayout(panel, Theme.S3, 0, TextAnchor.LowerCenter);
            UI.Button(panel, L.T("ui.continue_guest"), () => _advance = true, ButtonStyle.Primary, "icon/profile", 56f);
            var signIn = UI.Button(panel, L.T("ui.sign_in"), () => Toast.Show(GameApp.I.Services.Auth.UnavailableReason), ButtonStyle.Normal, "icon/cloud");
            signIn.GetComponent<Image>().color = new Color(1, 1, 1, 0.55f);
            var note = UI.Text(panel, L.T("ui.sign_in_unavailable"), Theme.FontTiny, Theme.TextMuted);
            UI.Size(note, -1, 34f);
            while (!_advance) yield return null;
            Destroy(panel.gameObject);
        }

        // ---- opening story: 4 short panels (~18 s), skippable at any time ----------------------------
        private IEnumerator Story()
        {
            var app = GameApp.I;
            app.Audio?.PlayMusic("story", 0.8f);
            _skip = false;
            var layer = UI.Blocker(_root, new Color(0.02f, 0.01f, 0.04f, 1f));
            var tapCatcher = layer.GetComponent<Image>();
            var catcherBtn = tapCatcher.gameObject.AddComponent<Button>();
            catcherBtn.transition = Selectable.Transition.None;
            catcherBtn.onClick.AddListener(() => _advance = true);
            var skip = UI.Button(layer, L.T("story.skip"), () => _skip = true, ButtonStyle.Normal, null, 40f, Theme.FontBody);
            UI.Place((RectTransform)skip.transform, new Vector2(1f, 1f), new Vector2(1f, 1f), new Vector2(-12f, -12f), new Vector2(96f, 40f));

            var picture = UI.Rect(layer, "Picture");
            UI.Place(picture, new Vector2(0.5f, 0.6f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(300f, 300f));
            var caption = UI.Text(layer, "", Theme.FontH2, Theme.Text, TextAlignmentOptions.Center, false, "Caption");
            UI.Place(caption.rectTransform, new Vector2(0.5f, 0.22f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(320f, 120f));
            caption.overflowMode = TextOverflowModes.Overflow;
            var hint = UI.Text(layer, L.T("story.continue"), Theme.FontTiny, Theme.TextMuted);
            UI.Place(hint.rectTransform, new Vector2(0.5f, 0.06f), new Vector2(0.5f, 0.5f), Vector2.zero, new Vector2(300f, 20f));

            for (int panel = 0; panel < 4 && !_skip; panel++)
            {
                UI.Clear(picture);
                BuildStoryPicture(picture, panel);
                caption.text = L.T("story." + (panel + 1));
                _advance = false;
                float t = 0f;
                caption.alpha = 0f;
                while (!_skip && !_advance && t < 4.5f)
                {
                    t += Time.unscaledDeltaTime;
                    caption.alpha = Mathf.Clamp01(t * 2.5f);
                    yield return null;
                }
                if (_advance) app.Audio?.Play("swoosh");
            }
            Destroy(layer.gameObject);
            app.Audio?.PlayMusic("menu", 1.5f);
        }

        private void BuildStoryPicture(RectTransform parent, int panel)
        {
            var sp = GameApp.I.Sprites;
            switch (panel)
            {
                case 0:
                {
                    var anim = sp.Anim("hero/arc_light_cat/cast");
                    AnimatedUi(parent, anim, 6f, new Vector2(0f, -20f));
                    break;
                }
                case 1:
                {
                    var citadel = UI.Img(parent, null, Color.white, false, "Citadel");
                    citadel.sprite = sp.GetForUi("citadel/base", 2.5f);
                    citadel.SetNativeSize();
                    var hero = sp.Anim("hero/arc_light_cat/idle");
                    AnimatedUi(parent, hero, 2.5f, new Vector2(0f, 30f));
                    break;
                }
                case 2:
                {
                    string[] foes = { "enemy/shield_guard/walk", "enemy/rat_raider/walk", "enemy/crow_archer/walk", "enemy/hound_runner/walk", "enemy/iron_golem/walk" };
                    for (int i = 0; i < foes.Length; i++)
                    {
                        var a = sp.Anim(foes[i]);
                        var go = AnimatedUi(parent, a, 3f, new Vector2(-120f + i * 60f, (i % 2) * -30f));
                        if (go != null) go.transform.localScale = new Vector3(-1f, 1f, 1f);   // marching toward the viewer's left
                    }
                    break;
                }
                default:
                {
                    AnimatedUi(parent, sp.Anim("hero/arc_light_cat/victory"), 6f, new Vector2(0f, -20f));
                    break;
                }
            }
        }

        private static GameObject AnimatedUi(RectTransform parent, SpriteAnim anim, float scale, Vector2 pos)
        {
            if (anim == null || anim.frames.Length == 0) return null;
            var sp = GameApp.I.Sprites;
            var img = UI.Img(parent, null, Color.white, false, anim.name);
            var frames = new Sprite[anim.frames.Length];
            for (int i = 0; i < frames.Length; i++) frames[i] = anim.frames[i] != null ? sp.GetForUi(anim.frames[i].name, scale) : null;
            img.sprite = frames[0];
            img.SetNativeSize();
            img.rectTransform.anchoredPosition = pos;
            var a = img.gameObject.AddComponent<UIImageAnimator>();
            a.Target = img;
            a.Frames = frames;
            a.Fps = anim.fps;
            return img.gameObject;
        }

        public override bool OnBack()
        {
            _skip = true;
            return true;
        }
    }

    public static class CameraUtil
    {
        public static Camera EnsureCamera(Color bg)
        {
            var cam = Camera.main;
            if (cam == null)
            {
                var go = new GameObject("Main Camera");
                go.tag = "MainCamera";
                cam = go.AddComponent<Camera>();
            }
            cam.orthographic = true;
            cam.orthographicSize = 10f;
            cam.transform.position = new Vector3(0f, 0f, -10f);
            cam.clearFlags = CameraClearFlags.SolidColor;
            cam.backgroundColor = bg;
            cam.nearClipPlane = 0.1f;
            cam.farClipPlane = 50f;
            return cam;
        }
    }
}
