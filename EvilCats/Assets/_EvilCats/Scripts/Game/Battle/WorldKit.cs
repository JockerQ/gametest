using System.Collections.Generic;
using EvilCats.Core;
using UnityEngine;

namespace EvilCats.Game
{
    /// <summary>Sorting and sprite-renderer helpers for the top-down 3/4 battlefield.</summary>
    public static class WorldKit
    {
        public const int GroundOrder = -30000, PathOrder = -29000, TelegraphOrder = -20000;
        public const int ProjectileOrder = 20000, FxOrder = 21000, NumberOrder = 25000;
        // The citadel group is drawn as a block that sits at depth y≈1 (see BattleView).
        public const int CitadelOrder = -20, CrownOrder = -19, StormheartOrder = -18, HeroOrder = -17, MiddleOrder = -16, BaseOrder = -15;

        private static Material _spriteMaterial;
        private static Sprite _white;

        /// <summary>Lower on screen = drawn in front. 20 steps per world unit.</summary>
        public static int SortY(float y) => Mathf.Clamp(Mathf.RoundToInt(-y * 20f), -600, 600);

        public static Vector3 V3(Vec2 v, float z = 0f) => new Vector3(v.x, v.y, z);

        public static SpriteRenderer Sprite(Transform parent, string name, Sprite sprite, int order, Vector2 pos, Color? color = null)
        {
            var go = new GameObject(name);
            go.transform.SetParent(parent, false);
            go.transform.localPosition = new Vector3(pos.x, pos.y, 0f);
            var sr = go.AddComponent<SpriteRenderer>();
            sr.sprite = sprite;
            sr.sortingOrder = order;
            sr.color = color ?? Color.white;
            if (Material != null) sr.sharedMaterial = Material;
            return sr;
        }

        /// <summary>
        /// Unlit sprite material when the setup script created one (URP 2D: Sprite-Unlit-Default),
        /// otherwise the pipeline's default sprite material is kept.
        /// </summary>
        public static Material Material
        {
            get
            {
                if (_spriteMaterial == null) _spriteMaterial = Resources.Load<Material>("ECArt/Materials/EC_SpriteUnlit");
                return _spriteMaterial;
            }
        }

        /// <summary>1x1 white sprite (16 px per unit scale) for bars and flat shapes.</summary>
        public static Sprite White
        {
            get
            {
                if (_white != null) return _white;
                var t = new Texture2D(4, 4, TextureFormat.RGBA32, false) { filterMode = FilterMode.Point, wrapMode = TextureWrapMode.Clamp };
                var px = new Color32[16];
                for (int i = 0; i < px.Length; i++) px[i] = new Color32(255, 255, 255, 255);
                t.SetPixels32(px);
                t.Apply(false, true);
                _white = UnityEngine.Sprite.Create(t, new Rect(0, 0, 4, 4), new Vector2(0f, 0.5f), 4f);
                _white.name = "white";
                return _white;
            }
        }
    }

    /// <summary>
    /// Fits the 16x20 arena into the part of the screen between the HUD's top bar and bottom dock
    /// (in real pixels, including notches), and adds optional screen shake.
    /// </summary>
    public sealed class CameraRig : MonoBehaviour
    {
        public Camera Cam;
        public float ArenaW = 16f, ArenaH = 20f;
        public float TopReservedPx, BottomReservedPx;
        private Vector3 _base;
        private float _shake, _shakeTime;
        private int _lastW, _lastH;
        private Rect _lastSafe;
        public float PixelsPerUnit { get; private set; }

        public static CameraRig Create(Color bg)
        {
            var cam = CameraUtil.EnsureCamera(bg);
            var rig = cam.gameObject.GetComponent<CameraRig>() ?? cam.gameObject.AddComponent<CameraRig>();
            rig.Cam = cam;
            return rig;
        }

        public void SetReserved(float topPx, float bottomPx)
        {
            TopReservedPx = topPx;
            BottomReservedPx = bottomPx;
            Fit();
        }

        public void Fit()
        {
            if (Cam == null || Screen.width <= 0 || Screen.height <= 0) return;
            _lastW = Screen.width;
            _lastH = Screen.height;
            _lastSafe = Screen.safeArea;
            float availH = Mathf.Max(100f, Screen.height - TopReservedPx - BottomReservedPx);
            float availW = Screen.width;
            float ppu = Mathf.Min(availW / (ArenaW + 0.2f), availH / (ArenaH + 0.2f));
            PixelsPerUnit = ppu;
            Cam.orthographicSize = Screen.height / (2f * ppu);
            float centerScreenY = BottomReservedPx + availH * 0.5f;
            float offsetWorld = (centerScreenY - Screen.height * 0.5f) / ppu;
            _base = new Vector3(0f, -offsetWorld, -10f);
            Cam.transform.position = _base;
        }

        public void Shake(float strength, float time = 0.25f)
        {
            var app = GameApp.I;
            if (app != null && app.Meta != null && !app.Meta.Data.settings.screenShake) return;
            _shake = Mathf.Max(_shake, strength);
            _shakeTime = Mathf.Max(_shakeTime, time);
        }

        private void LateUpdate()
        {
            if (Screen.width != _lastW || Screen.height != _lastH || Screen.safeArea != _lastSafe) Fit();
            if (_shakeTime > 0f)
            {
                _shakeTime -= Time.unscaledDeltaTime;
                float s = _shake * Mathf.Clamp01(_shakeTime / 0.25f);
                Cam.transform.position = _base + new Vector3(Random.Range(-s, s), Random.Range(-s, s), 0f);
                if (_shakeTime <= 0f) { Cam.transform.position = _base; _shake = 0f; }
            }
        }

        public Vector2 ScreenToWorld(Vector2 screen)
        {
            var w = Cam.ScreenToWorldPoint(new Vector3(screen.x, screen.y, 10f));
            return new Vector2(w.x, w.y);
        }

        public Vector2 WorldToScreen(Vector2 world)
        {
            var s = Cam.WorldToScreenPoint(new Vector3(world.x, world.y, 0f));
            return new Vector2(s.x, s.y);
        }
    }

    /// <summary>Minimal reusable object pool keyed by prefab kind.</summary>
    public sealed class Pool<T> where T : Component
    {
        private readonly Stack<T> _free = new Stack<T>();
        private readonly System.Func<T> _create;
        public int Created { get; private set; }

        public Pool(System.Func<T> create) { _create = create; }

        public T Get()
        {
            T item = _free.Count > 0 ? _free.Pop() : null;
            if (item == null) { item = _create(); Created++; }
            item.gameObject.SetActive(true);
            return item;
        }

        public void Release(T item)
        {
            if (item == null) return;
            item.gameObject.SetActive(false);
            _free.Push(item);
        }
    }
}
