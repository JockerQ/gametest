using System.Collections.Generic;
using EvilCats.Sim;
using UnityEngine;

namespace EvilCats.Game
{
    /// <summary>
    /// Views for enemies, bosses and projectiles, keyed by simulation uid (the simulation reuses
    /// its entity objects, so references are never kept). Positions are interpolated between the
    /// last two fixed steps for smooth 60 fps motion from the 30 Hz simulation. Shows health
    /// bars, elite/boss auras, status icons (burn, chill, freeze, stun, mark, armour break,
    /// bleed, pull) and plays walk/attack/special/death clips.
    /// </summary>
    public sealed class UnitViews : MonoBehaviour
    {
        private BattleView _view;
        private SpriteLibrary _sp;
        private Transform _root;
        private Pool<EnemyView> _enemyPool;
        private Pool<SpriteAnimator> _projPool;
        private readonly Dictionary<int, EnemyView> _enemies = new Dictionary<int, EnemyView>(256);
        private readonly Dictionary<int, ProjectileView> _projectiles = new Dictionary<int, ProjectileView>(256);
        private readonly List<EnemyView> _dying = new List<EnemyView>(64);
        private readonly HashSet<int> _seen = new HashSet<int>();
        private readonly List<int> _remove = new List<int>(64);

        /// <summary>Interpolation factor between the previous and current fixed step (0..1).</summary>
        public float Alpha = 1f;

        private sealed class ProjectileView
        {
            public SpriteAnimator anim;
            public SpriteRenderer shadow;
            public ProjectileKind kind;
            public Vector2 start, target;
        }

        public void Init(BattleView view, SpriteLibrary sprites)
        {
            _view = view;
            _sp = sprites;
            _root = new GameObject("Units").transform;
            _root.SetParent(view.transform, false);
            _enemyPool = new Pool<EnemyView>(() =>
            {
                var go = new GameObject("Enemy");
                go.transform.SetParent(_root, false);
                var v = go.AddComponent<EnemyView>();
                v.Build(_sp);
                return v;
            });
            _projPool = new Pool<SpriteAnimator>(() =>
            {
                var sr = WorldKit.Sprite(_root, "Projectile", null, WorldKit.ProjectileOrder, Vector2.zero);
                var a = sr.gameObject.AddComponent<SpriteAnimator>();
                a.Target = sr;
                a.UseUnscaledTime = false;
                return a;
            });
        }

        public bool TryGetPos(int uid, out Vector2 pos)
        {
            if (_enemies.TryGetValue(uid, out var v) && v != null) { pos = v.Position; return true; }
            pos = Vector2.zero;
            return false;
        }

        public EnemyView Get(int uid) => _enemies.TryGetValue(uid, out var v) ? v : null;

        // ---- events ----------------------------------------------------------------------------
        public void OnHit(int uid, bool dot)
        {
            if (!dot && _enemies.TryGetValue(uid, out var v)) v.Hit();
        }

        public void OnAttack(int uid)
        {
            if (_enemies.TryGetValue(uid, out var v)) v.Attack();
        }

        public void OnSpecial(int uid, string clip, bool loop = false)
        {
            if (_enemies.TryGetValue(uid, out var v)) v.Special(clip, loop);
        }

        public void OnDied(int uid, Vector2 at)
        {
            if (!_enemies.TryGetValue(uid, out var v)) return;
            _enemies.Remove(uid);
            v.Die();
            _dying.Add(v);
        }

        /// <summary>Removed without dying on screen (fled, exploded): vanish with a puff.</summary>
        public void OnVanish(int uid)
        {
            if (!_enemies.TryGetValue(uid, out var v)) return;
            _enemies.Remove(uid);
            _enemyPool.Release(v);
        }

        // ---- per-frame sync ----------------------------------------------------------------------
        private void LateUpdate()
        {
            var battle = _view.Battle;
            if (battle == null) return;
            float a = Mathf.Clamp01(Alpha);

            // enemies and bosses
            _seen.Clear();
            var list = battle.Enemies;
            for (int i = 0; i < list.Count; i++)
            {
                var e = list[i];
                if (!e.alive) continue;
                _seen.Add(e.uid);
                if (!_enemies.TryGetValue(e.uid, out var v))
                {
                    v = _enemyPool.Get();
                    v.Bind(e, _sp);
                    _enemies[e.uid] = v;
                }
                Vector2 p = Vector2.Lerp(new Vector2(e.prevPos.x, e.prevPos.y), new Vector2(e.pos.x, e.pos.y), a);
                v.Sync(e, p, battle);
            }
            _remove.Clear();
            foreach (var kv in _enemies) if (!_seen.Contains(kv.Key)) _remove.Add(kv.Key);
            foreach (var uid in _remove)
            {
                // left the simulation without an EnemyDied event this frame (fled / silently removed)
                var v = _enemies[uid];
                _enemies.Remove(uid);
                _enemyPool.Release(v);
            }
            for (int i = _dying.Count - 1; i >= 0; i--)
            {
                if (_dying[i].UpdateDeath(Time.deltaTime)) continue;
                _enemyPool.Release(_dying[i]);
                _dying.RemoveAt(i);
            }

            // projectiles
            _seen.Clear();
            var projs = battle.Projectiles;
            for (int i = 0; i < projs.Count; i++)
            {
                var p = projs[i];
                if (!p.alive) continue;
                _seen.Add(p.uid);
                if (!_projectiles.TryGetValue(p.uid, out var pv))
                {
                    pv = CreateProjectile(p);
                    if (pv == null) continue;
                    _projectiles[p.uid] = pv;
                }
                SyncProjectile(pv, p, a);
            }
            _remove.Clear();
            foreach (var kv in _projectiles) if (!_seen.Contains(kv.Key)) _remove.Add(kv.Key);
            foreach (var uid in _remove)
            {
                var pv = _projectiles[uid];
                _projectiles.Remove(uid);
                ReleaseProjectile(pv);
            }
        }

        private ProjectileView CreateProjectile(Projectile p)
        {
            var anim = _projPool.Get();
            anim.Target.color = Color.white;
            anim.transform.localScale = Vector3.one;
            var pv = new ProjectileView { anim = anim, kind = p.kind, start = new Vector2(p.start.x, p.start.y), target = new Vector2(p.target.x, p.target.y) };
            switch (p.kind)
            {
                case ProjectileKind.Shell: PlayOrSprite(anim, "fx/shell"); break;
                case ProjectileKind.Bolt: PlayOrSprite(anim, "fx/ballista_bolt"); break;
                case ProjectileKind.Arrow: PlayOrSprite(anim, "fx/arrow"); break;
                case ProjectileKind.Feather: PlayOrSprite(anim, "fx/feather"); break;
                default:
                    PlayOrSprite(anim, "fx/shell");
                    anim.Target.color = FxSystem.GoldColor;
                    break;
            }
            if (p.kind == ProjectileKind.Shell)
            {
                var sh = _sp.TryGet("fx/shadow");
                if (sh != null)
                {
                    pv.shadow = WorldKit.Sprite(_root, "ShellShadow", sh, WorldKit.TelegraphOrder + 40, pv.start, new Color(1f, 1f, 1f, 0.6f));
                    pv.shadow.transform.localScale = Vector3.one * 0.6f;
                }
            }
            return pv;
        }

        private void PlayOrSprite(SpriteAnimator anim, string name)
        {
            var clip = _sp.Anim(name);
            if (clip != null) { anim.enabled = true; anim.Play(clip, true); }
            else { anim.enabled = false; anim.Target.sprite = _sp.Get(name); }
        }

        private void SyncProjectile(ProjectileView pv, Projectile p, float a)
        {
            Vector2 pos = Vector2.Lerp(new Vector2(p.prevPos.x, p.prevPos.y), new Vector2(p.pos.x, p.pos.y), a);
            var tr = pv.anim.transform;
            if (p.kind == ProjectileKind.Shell)
            {
                // lobbed: the simulation moves the shell along the ground; draw it on an arc above its shadow
                float total = Mathf.Max(0.01f, Vector2.Distance(pv.start, pv.target));
                float t = Mathf.Clamp01(Vector2.Distance(pv.start, pos) / total);
                float h = Mathf.Min(2.4f, 0.35f * total) * 4f * t * (1f - t);
                tr.localPosition = new Vector3(pos.x, pos.y + h, 0f);
                if (pv.shadow != null) pv.shadow.transform.localPosition = new Vector3(pos.x, pos.y, 0f);
                tr.localRotation = Quaternion.identity;
            }
            else
            {
                tr.localPosition = new Vector3(pos.x, pos.y, 0f);
                Vector2 d = new Vector2(p.pos.x - p.prevPos.x, p.pos.y - p.prevPos.y);
                if (d.sqrMagnitude < 1e-6f) d = pv.target - pos;
                if (d.sqrMagnitude > 1e-6f)
                    tr.localRotation = Quaternion.Euler(0f, 0f, Mathf.Atan2(d.y, d.x) * Mathf.Rad2Deg);
            }
        }

        private void ReleaseProjectile(ProjectileView pv)
        {
            if (pv.shadow != null) Destroy(pv.shadow.gameObject);
            pv.anim.transform.localRotation = Quaternion.identity;
            _projPool.Release(pv.anim);
        }

        public void ClearAll()
        {
            foreach (var v in _enemies.Values) _enemyPool.Release(v);
            _enemies.Clear();
            foreach (var v in _dying) _enemyPool.Release(v);
            _dying.Clear();
            foreach (var pv in _projectiles.Values) ReleaseProjectile(pv);
            _projectiles.Clear();
        }
    }

    /// <summary>One enemy or boss on screen. Pooled; re-bound to a new simulation uid on reuse.</summary>
    public sealed class EnemyView : MonoBehaviour
    {
        private SpriteRenderer _body, _flash, _shadow, _aura, _barBg, _barFill, _frozen;
        private SpriteAnimator _anim, _auraAnim;
        private SpriteRenderer _stun, _burn, _chill, _mark, _armour, _bleed;
        private SpriteAnimator _stunAnim, _burnAnim, _bleedAnim;
        private SpriteLibrary _sp;
        private string _prefix;              // "enemy/rat_raider/" or "boss/sir_barkhelm/"
        private SpriteAnim _move, _idle, _charge, _attack, _death;
        private bool _isBoss, _flying, _dead;
        private float _deathTime, _lastFlash, _height, _scale, _barWidth;
        private Color _tint = Color.white;
        private int _uid;
        public string TypeId { get; private set; }
        public Vector2 Position { get; private set; }
        public bool IsBoss => _isBoss;

        public void Build(SpriteLibrary sp)
        {
            _sp = sp;
            _shadow = WorldKit.Sprite(transform, "Shadow", sp.TryGet("fx/shadow"), WorldKit.TelegraphOrder + 30, Vector2.zero, new Color(1f, 1f, 1f, 0.55f));
            _aura = WorldKit.Sprite(transform, "Aura", null, WorldKit.TelegraphOrder + 31, Vector2.zero);
            _auraAnim = _aura.gameObject.AddComponent<SpriteAnimator>();
            _auraAnim.Target = _aura;
            _auraAnim.UseUnscaledTime = false;
            _body = WorldKit.Sprite(transform, "Body", null, 0, Vector2.zero);
            _flash = WorldKit.Sprite(_body.transform, "Flash", null, 1, Vector2.zero);
            _flash.enabled = false;
            _anim = _body.gameObject.AddComponent<SpriteAnimator>();
            _anim.Target = _body;
            _anim.FlashOverlay = _flash;
            _anim.UseUnscaledTime = false;
            _frozen = WorldKit.Sprite(transform, "Frozen", sp.TryGet("fx/frozen"), 2, Vector2.zero, new Color(1f, 1f, 1f, 0.85f));
            _frozen.enabled = false;
            _barBg = WorldKit.Sprite(transform, "HpBg", WorldKit.White, WorldKit.NumberOrder - 200, Vector2.zero, new Color(0.08f, 0.04f, 0.1f, 0.85f));
            _barFill = WorldKit.Sprite(transform, "HpFill", WorldKit.White, WorldKit.NumberOrder - 199, Vector2.zero, Theme.Health);
            _stun = Icon("Stun", out _stunAnim, "fx/stun");
            _burn = Icon("Burn", out _burnAnim, "fx/burn");
            _bleed = Icon("Bleed", out _bleedAnim, "fx/bleed");
            _chill = Icon("Chill", out _, null, "fx/chill");
            _mark = Icon("Mark", out _, null, "fx/mark");
            _armour = Icon("Armour", out _, null, "fx/armour_break");
        }

        private SpriteRenderer Icon(string name, out SpriteAnimator anim, string clip, string sprite = null)
        {
            var sr = WorldKit.Sprite(transform, name, sprite != null ? _sp.TryGet(sprite) : null, WorldKit.NumberOrder - 198, Vector2.zero);
            anim = null;
            if (clip != null)
            {
                anim = sr.gameObject.AddComponent<SpriteAnimator>();
                anim.Target = sr;
                anim.UseUnscaledTime = false;
                anim.Play(_sp.Anim(clip));
            }
            sr.enabled = false;
            return sr;
        }

        public void Bind(Enemy e, SpriteLibrary sp)
        {
            _sp = sp;
            _uid = e.uid;
            TypeId = e.typeId;
            _isBoss = e.isBoss;
            _flying = e.flying;
            _dead = false;
            _deathTime = 0f;
            _lastFlash = -1f;
            _tint = Color.white;
            string id = e.typeId;
            bool eliteArt = e.elite && (sp.HasAnim("enemy/" + id + "_elite/walk") || sp.HasAnim("enemy/" + id + "_elite/fly"));
            _prefix = e.isBoss ? "boss/" + id + "/" : "enemy/" + id + (eliteArt ? "_elite/" : "/");
            _move = Clip("walk") ?? Clip("fly") ?? Clip("idle");
            _idle = Clip("idle");
            _charge = Clip("charge");
            _attack = Clip("attack") ?? Clip("volley") ?? Clip("barrage") ?? Clip("command");
            _death = Clip("death") ?? Clip("defeat");
            _anim.SpeedMultiplier = 1f;
            _anim.Play(_move, true);
            // elites: 1.25x size from the simulation; the art also has a distinct elite palette
            _scale = e.isBoss ? 1f : Mathf.Max(0.5f, e.scale);
            _body.transform.localScale = new Vector3(_scale, _scale, 1f);
            var frame = _move != null && _move.frames.Length > 0 && _move.frames[0] != null ? _move.frames[0] : null;
            _height = frame != null ? frame.rect.height / SpriteLibrary.WorldPpu * _scale : 1f;
            float shadowW = Mathf.Max(0.5f, e.radius * 2.2f);
            _shadow.transform.localScale = new Vector3(shadowW, shadowW * 0.8f, 1f);
            _shadow.transform.localPosition = new Vector3(0f, _flying ? -0.1f : 0.02f, 0f);
            _shadow.enabled = _shadow.sprite != null;
            string aura = e.isBoss ? "fx/boss_aura" : e.elite ? "fx/elite_aura" : null;
            _aura.enabled = aura != null;
            if (aura != null)
            {
                _auraAnim.Play(_sp.Anim(aura), true);
                float auraNative = _aura.sprite != null ? _aura.sprite.rect.width / SpriteLibrary.WorldPpu : 2f;
                float s = Mathf.Max(1f, e.radius * 2.6f) / auraNative;
                _aura.transform.localScale = new Vector3(s, s, 1f);
            }
            _barWidth = Mathf.Clamp(e.radius * 2.4f, 0.8f, 1.8f);
            _frozen.transform.localScale = Vector3.one * Mathf.Max(0.8f, _height / 1.5f);
            SetIcons(false, false, false, false, false, false);
            _frozen.enabled = false;
            _body.color = Color.white;
            SetAlpha(1f);
        }

        private SpriteAnim Clip(string name) => _sp.Anim(_prefix + name);

        public void Sync(Enemy e, Vector2 p, Battle battle)
        {
            Position = p;
            float bob = _flying ? 0.35f + 0.08f * Mathf.Sin(Time.time * 6f + _uid) : 0f;
            transform.localPosition = new Vector3(p.x, p.y, 0f);
            _body.transform.localPosition = new Vector3(0f, bob, 0f);
            int order = WorldKit.SortY(p.y);
            _body.sortingOrder = order;
            _flash.sortingOrder = order + 1;
            _frozen.sortingOrder = order + 2;
            _frozen.transform.localPosition = new Vector3(0f, bob, 0f);

            // facing: art faces right; face the travel direction, or the citadel while standing
            float vx = e.velocity.x;
            if (Mathf.Abs(vx) > 0.05f) _body.flipX = vx < 0f;
            else if (e.state == MoveState.Holding) _body.flipX = p.x > 0f;

            // animation speed follows actual movement (frozen = fully stopped)
            bool frozen = e.frozenTime > 0f;
            bool stunned = e.stunTime > 0f;
            float speed = e.velocity.Length;
            if (_isBoss) SyncBossClip(e, speed);
            else
            {
                bool specialPlaying = _anim.Current != null && _anim.Current != _move && !_anim.Finished;
                if (!specialPlaying && _anim.Current != _move && _move != null) _anim.Play(_move);
            }
            bool special = _anim.Current != null && _anim.Current != _move;
            if (frozen || stunned) _anim.SpeedMultiplier = 0f;
            else if (_flying || special || _isBoss) _anim.SpeedMultiplier = 1f;
            else _anim.SpeedMultiplier = speed > 0.05f ? Mathf.Clamp(speed / Mathf.Max(0.3f, e.speed), 0.5f, 2.5f) : 0f;

            // tints: frozen (ice), chilled (cool), decree buff (gold), shield stance (steel)
            Color tint = Color.white;
            if (frozen) tint = new Color(0.65f, 0.85f, 1f);
            else if (e.IsChilled) tint = new Color(0.8f, 0.92f, 1f);
            if (e.buffTime > 0f) tint = Color.Lerp(tint, new Color(1f, 0.85f, 0.4f), 0.35f + 0.15f * Mathf.Sin(Time.time * 8f));
            if (e.isBoss && e.shieldTime > 0f) tint = Color.Lerp(tint, new Color(0.7f, 0.8f, 1f), 0.5f);
            _tint = tint;
            if (!_dead) _body.color = tint;
            _frozen.enabled = frozen;

            // health bar: hidden at full health (bosses use the big HUD bar instead)
            float frac = e.HealthFraction;
            bool showBar = !_isBoss && frac < 0.999f;
            _barBg.enabled = _barFill.enabled = showBar;
            float top = _height + bob + 0.12f;
            if (showBar)
            {
                _barBg.transform.localPosition = new Vector3(-_barWidth * 0.5f - 0.03f, top, 0f);
                _barBg.transform.localScale = new Vector3(_barWidth + 0.06f, 0.2f, 1f);   // White is 1x1 unit, pivot left
                _barFill.transform.localPosition = new Vector3(-_barWidth * 0.5f, top, 0f);
                _barFill.transform.localScale = new Vector3(_barWidth * Mathf.Clamp01(frac), 0.12f, 1f);
                _barFill.color = e.elite ? FxSystem.GoldColor : Theme.Health;
            }

            // status icons in a row above the bar
            bool burning = e.IsBurning, bleeding = e.bleedCount > 0, marked = e.markTime > 0f, broken = e.armorBreakTime > 0f;
            bool chilled = e.IsChilled && !frozen;
            SetIcons(stunned || e.pulledTime > 0f, burning, bleeding, chilled, marked, broken);
            float iconY = top + (showBar ? 0.28f : 0.12f);
            float x = 0f;
            int shown = (burning ? 1 : 0) + (bleeding ? 1 : 0) + (chilled ? 1 : 0) + (marked ? 1 : 0) + (broken ? 1 : 0);
            float start = -(shown - 1) * 0.3f;
            x = start;
            PlaceIcon(_burn, burning, ref x, iconY);
            PlaceIcon(_bleed, bleeding, ref x, iconY);
            PlaceIcon(_chill, chilled, ref x, iconY);
            PlaceIcon(_mark, marked, ref x, iconY);
            PlaceIcon(_armour, broken, ref x, iconY);
            if (_stun.enabled) _stun.transform.localPosition = new Vector3(0f, iconY + (shown > 0 ? 0.42f : 0.1f), 0f);
            // being pulled: a slight sway
            _body.transform.localRotation = e.pulledTime > 0f ? Quaternion.Euler(0f, 0f, 8f * Mathf.Sin(Time.time * 18f + _uid)) : Quaternion.identity;
        }

        /// <summary>
        /// Bosses: ability clips are started by events (windup, shield, summon...). Here we only
        /// handle states without events: the charge run itself, idling while holding position,
        /// and returning to the movement clip once an ability has ended.
        /// </summary>
        private void SyncBossClip(Enemy e, float speed)
        {
            var b = e.boss;
            if (b == null) return;
            bool abilityActive = b.activeAbility >= 0;
            string type = abilityActive && e.bossDef != null && b.activeAbility < e.bossDef.abilities.Count ? e.bossDef.abilities[b.activeAbility].type : null;
            if (type == "charge" && b.abilityStage == 2)
            {
                var run = _charge ?? _move;
                if (_anim.Current != run) _anim.Play(run, true);
                return;
            }
            if (abilityActive) return;
            var cur = _anim.Current;
            bool oneShotPlaying = cur != null && !cur.loop && !_anim.Finished;
            if (oneShotPlaying) return;
            var want = (speed < 0.05f && _idle != null && !_flying) ? _idle : _move;
            if (cur != want && want != null) _anim.Play(want, true);
        }

        private static void PlaceIcon(SpriteRenderer sr, bool on, ref float x, float y)
        {
            if (!on) return;
            sr.transform.localPosition = new Vector3(x, y, 0f);
            x += 0.6f;
        }

        private void SetIcons(bool stun, bool burn, bool bleed, bool chill, bool mark, bool armour)
        {
            _stun.enabled = stun;
            _burn.enabled = burn;
            _bleed.enabled = bleed;
            _chill.enabled = chill;
            _mark.enabled = mark;
            _armour.enabled = armour;
        }

        public void Hit()
        {
            if (_dead || Time.time - _lastFlash < 0.06f) return;
            _lastFlash = Time.time;
            _anim.Flash(0.07f);
        }

        public void Attack()
        {
            if (_dead || _attack == null) return;
            _anim.Play(_attack, true, _move);
        }

        public void Special(string clip, bool loop)
        {
            if (_dead) return;
            var a = Clip(clip);
            if (a == null) return;
            _anim.Play(a, true, loop || a.loop ? null : _move);
        }

        public void ResumeMove()
        {
            if (!_dead && _move != null) _anim.Play(_move, true);
        }

        public void Die()
        {
            _dead = true;
            _deathTime = 0f;
            _body.transform.localRotation = Quaternion.identity;
            _barBg.enabled = _barFill.enabled = false;
            SetIcons(false, false, false, false, false, false);
            _frozen.enabled = false;
            _aura.enabled = false;
            _anim.SpeedMultiplier = 1f;
            if (_death != null) _anim.Play(_death, true);
        }

        /// <summary>Returns false when the death animation and fade are complete.</summary>
        public bool UpdateDeath(float dt)
        {
            _deathTime += dt;
            float clip = _death != null ? _death.Duration : 0.3f;
            float fade = _isBoss ? 1.2f : 0.35f;
            if (_deathTime > clip) SetAlpha(1f - Mathf.Clamp01((_deathTime - clip) / fade));
            return _deathTime < clip + fade;
        }

        private void SetAlpha(float a)
        {
            var c = _tint;
            c.a = a;
            _body.color = c;
            var s = _shadow.color;
            s.a = 0.55f * a;
            _shadow.color = s;
        }
    }
}
