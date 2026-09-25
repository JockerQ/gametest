using System;
using UnityEngine;
using UnityEngine.EventSystems;

namespace EvilCats.Game
{
    /// <summary>
    /// Tap / hold detection on any raycast-target Graphic through the EventSystem (touch and mouse
    /// alike). A short press is a tap; holding past HoldTime opens details instead of tapping.
    /// </summary>
    public sealed class PressHandler : MonoBehaviour, IPointerDownHandler, IPointerUpHandler, IPointerExitHandler
    {
        public Action OnTap, OnHoldStart, OnHoldEnd;
        public float HoldTime = 0.42f;
        private bool _down, _held;
        private float _t;

        public void OnPointerDown(PointerEventData e)
        {
            _down = true;
            _held = false;
            _t = 0f;
        }

        public void OnPointerUp(PointerEventData e)
        {
            // a press that turned into scrolling a list is not a tap
            if (_down && !_held && !e.dragging) OnTap?.Invoke();
            if (_held) OnHoldEnd?.Invoke();
            _down = _held = false;
        }

        public void OnPointerExit(PointerEventData e)
        {
            if (_held) OnHoldEnd?.Invoke();
            _down = _held = false;
        }

        private void OnDisable()
        {
            if (_held) OnHoldEnd?.Invoke();
            _down = _held = false;
        }

        private void Update()
        {
            if (!_down || _held) return;
            _t += Time.unscaledDeltaTime;
            if (_t < HoldTime || OnHoldStart == null) return;
            _held = true;
            OnHoldStart.Invoke();
        }
    }

    /// <summary>Short scale "punch" for counters and buttons (unscaled time, so it works while paused).</summary>
    public sealed class Punch : MonoBehaviour
    {
        private float _t = 1f, _strength;
        private Vector3 _base = Vector3.one;
        private bool _hasBase;

        public void Play(float strength = 0.18f)
        {
            if (!_hasBase) { _base = transform.localScale; _hasBase = true; }
            _t = 0f;
            _strength = strength;
        }

        private void Update()
        {
            if (_t >= 1f) return;
            _t = Mathf.Min(1f, _t + Time.unscaledDeltaTime / 0.22f);
            float s = 1f + _strength * Mathf.Sin(_t * Mathf.PI);
            transform.localScale = _base * s;
        }
    }
}
