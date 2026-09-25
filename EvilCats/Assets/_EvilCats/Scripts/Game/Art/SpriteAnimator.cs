using System;
using UnityEngine;
using UnityEngine.UI;

namespace EvilCats.Game
{
    /// <summary>
    /// Plays SpriteAnim frame sequences on a SpriteRenderer (world) with an optional white
    /// "flash" overlay renderer for hit feedback. Uses unscaled or game time as chosen.
    /// </summary>
    public sealed class SpriteAnimator : MonoBehaviour
    {
        public SpriteRenderer Target;
        public SpriteRenderer FlashOverlay;
        public bool UseUnscaledTime = true;
        public float SpeedMultiplier = 1f;

        private SpriteAnim _anim;
        private SpriteAnim _fallback;
        private float _t;
        private int _frame = -1;
        private bool _finished;
        private float _flashTime;
        public Action OnFinished;

        public SpriteAnim Current => _anim;
        public bool Finished => _finished;
        public float NormalizedTime => _anim == null ? 1f : Mathf.Clamp01(_t / _anim.Duration);

        /// <summary>Play a clip. If restart is false and it is already playing, nothing happens.
        /// A non-looping clip returns to `thenLoop` (if given) when it ends.</summary>
        public void Play(SpriteAnim anim, bool restart = false, SpriteAnim thenLoop = null)
        {
            if (anim == null) return;
            if (!restart && _anim == anim && !_finished) return;
            _anim = anim;
            _fallback = thenLoop;
            _t = 0f;
            _frame = -1;
            _finished = false;
            Apply(0);
        }

        public void Flash(float seconds = 0.08f) => _flashTime = seconds;

        public void Tick(float dt)
        {
            if (_anim == null || _anim.frames == null || _anim.frames.Length == 0) return;
            _t += dt * SpeedMultiplier;
            int n = _anim.frames.Length;
            int f = (int)(_t * _anim.fps);
            if (_anim.loop) f %= n;
            else if (f >= n)
            {
                f = n - 1;
                if (!_finished)
                {
                    _finished = true;
                    OnFinished?.Invoke();
                    if (_fallback != null)
                    {
                        var next = _fallback;
                        _fallback = null;
                        Play(next, true);
                        return;
                    }
                }
            }
            if (f != _frame) Apply(f);
            if (FlashOverlay != null)
            {
                if (_flashTime > 0f)
                {
                    _flashTime -= dt;
                    FlashOverlay.enabled = true;
                    FlashOverlay.flipX = Target != null && Target.flipX;
                }
                else if (FlashOverlay.enabled) FlashOverlay.enabled = false;
            }
        }

        private void Apply(int f)
        {
            _frame = f;
            if (Target != null) Target.sprite = _anim.frames[f];
            if (FlashOverlay != null && _anim.flash != null && f < _anim.flash.Length) FlashOverlay.sprite = _anim.flash[f];
        }

        private void Update() => Tick(UseUnscaledTime ? Time.unscaledDeltaTime : Time.deltaTime);
    }

    /// <summary>Same idea for UI Images (home screen hero, portraits, icons that animate).</summary>
    public sealed class UIImageAnimator : MonoBehaviour
    {
        public Image Target;
        public Sprite[] Frames;
        public float Fps = 8f;
        private float _t;

        private void Update()
        {
            if (Target == null || Frames == null || Frames.Length == 0) return;
            _t += Time.unscaledDeltaTime;
            Target.sprite = Frames[(int)(_t * Fps) % Frames.Length];
        }
    }
}
