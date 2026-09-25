using System;
using EvilCats.Content;
using UnityEngine;

namespace EvilCats.Game
{
    /// <summary>Reads content JSON from Resources/ECData (TextAssets).</summary>
    public sealed class ResourcesContentSource : IContentSource
    {
        public string Read(string name)
        {
            var ta = Resources.Load<TextAsset>("ECData/" + name);
            return ta != null ? ta.text : null;
        }
    }

    /// <summary>
    /// Short, optional vibrations for major impacts and purchases only (never for every shot).
    /// Android: VibrationEffect.createOneShot when available (API 26+), otherwise the legacy call.
    /// </summary>
    public sealed class Haptics
    {
        public bool Enabled = true;
        private float _lastTime = -10f;
#if UNITY_ANDROID && !UNITY_EDITOR
        private AndroidJavaObject _vibrator;
        private bool _hasEffects;
        private bool _initTried;
#endif

        public void Light() => Pulse(18, 60);
        public void Medium() => Pulse(35, 140);
        public void Heavy() => Pulse(60, 255);

        private void Pulse(long ms, int amplitude)
        {
            if (!Enabled) return;
            if (Time.unscaledTime - _lastTime < 0.12f) return;   // never buzz continuously
            _lastTime = Time.unscaledTime;
#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                if (!_initTried)
                {
                    _initTried = true;
                    using (var unityPlayer = new AndroidJavaClass("com.unity3d.player.UnityPlayer"))
                    using (var activity = unityPlayer.GetStatic<AndroidJavaObject>("currentActivity"))
                        _vibrator = activity.Call<AndroidJavaObject>("getSystemService", "vibrator");
                    using (var version = new AndroidJavaClass("android.os.Build$VERSION"))
                        _hasEffects = version.GetStatic<int>("SDK_INT") >= 26;
                }
                if (_vibrator == null) { Handheld.Vibrate(); return; }
                if (_hasEffects)
                {
                    using (var effectClass = new AndroidJavaClass("android.os.VibrationEffect"))
                    using (var effect = effectClass.CallStatic<AndroidJavaObject>("createOneShot", ms, Mathf.Clamp(amplitude, 1, 255)))
                        _vibrator.Call("vibrate", effect);
                }
                else _vibrator.Call("vibrate", ms);
            }
            catch (Exception)
            {
                // Handheld.Vibrate() also makes Unity add the VIBRATE permission to the manifest.
                Handheld.Vibrate();
            }
#endif
        }
    }
}
