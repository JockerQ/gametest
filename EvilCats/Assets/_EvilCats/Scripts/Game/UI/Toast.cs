using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.UI;
#if ENABLE_INPUT_SYSTEM && EC_INPUT_SYSTEM_PACKAGE
using UnityEngine.InputSystem;
#endif

namespace EvilCats.Game
{
    /// <summary>
    /// Short messages at the top of the screen (reasons for locked/unavailable actions, rewards).
    /// Lives on its own always-on-top canvas that survives scene changes. Never blocks input.
    /// </summary>
    public sealed class Toast : MonoBehaviour
    {
        private static Toast _i;
        private RectTransform _root;
        private readonly Queue<(string text, Color color)> _queue = new Queue<(string, Color)>();
        private RectTransform _current;
        private float _t;
        private const float Duration = 2.4f;

        public static void Show(string text) => Show(text, Theme.Text);

        public static void Show(string text, Color color)
        {
            if (string.IsNullOrEmpty(text)) return;
            if (_i == null)
            {
                var app = GameApp.Ensure();
                _i = app.gameObject.AddComponent<Toast>();
            }
            // de-duplicate rapid repeats of the same message
            foreach (var q in _i._queue) if (q.text == text) return;
            _i._queue.Enqueue((text, color));
        }

        private void EnsureCanvas()
        {
            if (_root != null) return;
            _root = UI.CreateCanvas("ToastCanvas", 5000, out var canvas);
            canvas.transform.SetParent(transform, false);
            var raycaster = canvas.GetComponent<GraphicRaycaster>();
            if (raycaster != null) raycaster.enabled = false;
        }

        private void Update()
        {
            if (_current == null && _queue.Count > 0)
            {
                EnsureCanvas();
                var (text, color) = _queue.Dequeue();
                var panel = UI.Panel(_root, "ui/tooltip", "Toast");
                panel.raycastTarget = false;
                _current = panel.rectTransform;
                UI.Place(_current, new Vector2(0.5f, 1f), new Vector2(0.5f, 1f), new Vector2(0f, -86f), new Vector2(320f, 46f));
                var t = UI.Text(_current, text, Theme.FontSmall, color, TextAlignmentOptions.Center);
                UI.Stretch(t.rectTransform, 10, 4, 10, 4);
                t.enableAutoSizing = true;
                t.fontSizeMin = 9f;
                t.fontSizeMax = Theme.FontSmall;
                _t = 0f;
            }
            if (_current != null)
            {
                _t += Time.unscaledDeltaTime;
                float a = _t < 0.15f ? _t / 0.15f : (_t > Duration - 0.3f ? Mathf.Clamp01((Duration - _t) / 0.3f) : 1f);
                foreach (var g in _current.GetComponentsInChildren<Graphic>()) { var c = g.color; c.a = a; g.color = c; }
                if (_t >= Duration)
                {
                    Destroy(_current.gameObject);
                    _current = null;
                }
            }
        }
    }

    /// <summary>Routes the Android back button (Escape in the editor) to the active scene controller.</summary>
    public sealed class BackButton : MonoBehaviour
    {
        private void Update()
        {
            bool pressed = false;
#if ENABLE_INPUT_SYSTEM && EC_INPUT_SYSTEM_PACKAGE
            var kb = Keyboard.current;
            pressed = kb != null && kb.escapeKey.wasPressedThisFrame;
#elif ENABLE_LEGACY_INPUT_MANAGER
            pressed = Input.GetKeyDown(KeyCode.Escape);
#endif
            if (pressed && SceneController.Current != null) SceneController.Current.OnBack();
        }
    }
}
