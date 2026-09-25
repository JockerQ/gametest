using System.Collections.Generic;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace EvilCats.Game
{
    /// <summary>
    /// Music with crossfades on two sources, and a pooled SFX player with a global voice
    /// limit, per-sound voice caps, retrigger cooldowns, round-robin variations and modest
    /// pitch variation. Music and effects have separate volume "buses" stored in settings.
    /// Clips and mixing values come from Resources/ECAudio/audio_manifest.json.
    /// </summary>
    public sealed class AudioManager : MonoBehaviour
    {
        private sealed class Sfx
        {
            public AudioClip[] clips;
            public float volume = 1f, pitchVar;
            public int maxVoices = 4;
            public float cooldown;
            public float lastPlayed = -10f;
            public int next;
            public bool loop;
        }

        private sealed class Music
        {
            public AudioClip clip;
            public float volume = 0.8f;
            public bool loop = true;
        }

        private const int Voices = 20;
        private readonly Dictionary<string, Sfx> _sfx = new Dictionary<string, Sfx>();
        private readonly Dictionary<string, Music> _music = new Dictionary<string, Music>();
        private readonly List<AudioSource> _voices = new List<AudioSource>(Voices);
        private readonly Dictionary<AudioSource, string> _voiceOwner = new Dictionary<AudioSource, string>();
        private AudioSource _musicA, _musicB, _loopSource;
        private bool _aIsCurrent = true;
        private string _currentMusic;
        private float _musicVol = 0.8f, _sfxVol = 0.9f;
        private float _fadeT = 1f, _fadeDur = 1f;
        private float _duck = 1f;
        public bool Ready { get; private set; }
        public readonly List<string> Problems = new List<string>();

        public void Init()
        {
            if (Ready) return;
            _musicA = NewSource("MusicA");
            _musicB = NewSource("MusicB");
            _loopSource = NewSource("Loop");
            _loopSource.loop = true;
            for (int i = 0; i < Voices; i++) _voices.Add(NewSource("Voice" + i));
            var manifest = Resources.Load<TextAsset>("ECAudio/audio_manifest");
            if (manifest == null)
            {
                Problems.Add("audio: audio_manifest.json missing (run Tools/audio/build_audio.py)");
                Ready = true;
                return;
            }
            var root = JObject.Parse(manifest.text);
            if (root["music"] is JObject music)
                foreach (var kv in music)
                {
                    var clip = Resources.Load<AudioClip>("ECAudio/" + (string)kv.Value["file"]);
                    if (clip == null) { Problems.Add("audio: missing music " + kv.Key); continue; }
                    _music[kv.Key] = new Music { clip = clip, volume = (float?)kv.Value["volume"] ?? 0.8f, loop = (bool?)kv.Value["loop"] ?? true };
                }
            if (root["sfx"] is JObject sfx)
                foreach (var kv in sfx)
                {
                    var files = kv.Value["files"] as JArray;
                    if (files == null) continue;
                    var clips = new List<AudioClip>();
                    foreach (var f in files)
                    {
                        var clip = Resources.Load<AudioClip>("ECAudio/" + (string)f);
                        if (clip != null) clips.Add(clip);
                    }
                    if (clips.Count == 0) { Problems.Add("audio: missing sfx " + kv.Key); continue; }
                    _sfx[kv.Key] = new Sfx
                    {
                        clips = clips.ToArray(),
                        volume = (float?)kv.Value["volume"] ?? 1f,
                        pitchVar = (float?)kv.Value["pitchVar"] ?? 0f,
                        maxVoices = (int?)kv.Value["maxVoices"] ?? 4,
                        cooldown = ((float?)kv.Value["cooldownMs"] ?? 0f) / 1000f,
                        loop = (bool?)kv.Value["loop"] ?? false,
                    };
                }
            Ready = true;
        }

        private AudioSource NewSource(string n)
        {
            var go = new GameObject(n);
            go.transform.SetParent(transform, false);
            var s = go.AddComponent<AudioSource>();
            s.playOnAwake = false;
            s.spatialBlend = 0f;
            return s;
        }

        public void SetVolumes(float music, float sfx)
        {
            _musicVol = Mathf.Clamp01(music);
            _sfxVol = Mathf.Clamp01(sfx);
            ApplyMusicVolumes();
        }

        /// <summary>Temporarily lower music (e.g. under boss warnings or menus). 1 = normal.</summary>
        public void Duck(float amount)
        {
            _duck = Mathf.Clamp01(amount);
            ApplyMusicVolumes();
        }

        public void PlayMusic(string id, float fade = 1.2f)
        {
            if (!Ready || id == _currentMusic) return;
            if (!_music.TryGetValue(id, out var m)) return;
            _currentMusic = id;
            _aIsCurrent = !_aIsCurrent;
            var incoming = _aIsCurrent ? _musicA : _musicB;
            incoming.clip = m.clip;
            incoming.loop = m.loop;
            incoming.volume = 0f;
            incoming.Play();
            _fadeT = 0f;
            _fadeDur = Mathf.Max(0.01f, fade);
        }

        public void StopMusic(float fade = 1f)
        {
            _currentMusic = null;
            _aIsCurrent = !_aIsCurrent;
            var incoming = _aIsCurrent ? _musicA : _musicB;
            incoming.Stop();
            incoming.clip = null;
            _fadeT = 0f;
            _fadeDur = Mathf.Max(0.01f, fade);
        }

        private float MusicTarget(string id) => id != null && _music.TryGetValue(id, out var m) ? m.volume : 0f;

        private void ApplyMusicVolumes()
        {
            if (_musicA == null) return;
            float t = Mathf.Clamp01(_fadeT / _fadeDur);
            var cur = _aIsCurrent ? _musicA : _musicB;
            var old = _aIsCurrent ? _musicB : _musicA;
            float target = MusicTarget(_currentMusic) * _musicVol * _duck;
            cur.volume = target * t;
            old.volume = old.clip != null ? Mathf.Min(old.volume, target) * (1f - t) : 0f;
            if (t >= 1f && old.isPlaying) old.Stop();
        }

        private void Update()
        {
            if (_fadeT < _fadeDur)
            {
                _fadeT += Time.unscaledDeltaTime;
                ApplyMusicVolumes();
            }
        }

        /// <summary>Play a sound effect by id. Respects voice caps, cooldowns and the effects bus.</summary>
        public void Play(string id, float volumeScale = 1f, float pitch = 1f)
        {
            if (!Ready || _sfxVol <= 0f || id == null || !_sfx.TryGetValue(id, out var s)) return;
            float now = Time.unscaledTime;
            if (now - s.lastPlayed < s.cooldown) return;
            int playing = 0;
            AudioSource free = null, oldest = null;
            float oldestTime = float.MaxValue;
            foreach (var v in _voices)
            {
                if (v.isPlaying)
                {
                    if (_voiceOwner.TryGetValue(v, out var owner) && owner == id) playing++;
                    if (v.time < oldestTime && v.clip != null) { oldestTime = v.time; }
                    if (oldest == null || v.time > oldest.time) oldest = v;
                }
                else if (free == null) free = v;
            }
            if (playing >= s.maxVoices) return;
            var src = free ?? oldest;   // steal the voice that has played longest when all are busy
            if (src == null) return;
            s.lastPlayed = now;
            var clip = s.clips[s.next % s.clips.Length];
            s.next++;
            src.Stop();
            src.clip = clip;
            src.loop = false;
            src.volume = s.volume * _sfxVol * volumeScale;
            src.pitch = pitch * (s.pitchVar > 0f ? 1f + Random.Range(-s.pitchVar, s.pitchVar) : 1f);
            src.Play();
            _voiceOwner[src] = id;
        }

        /// <summary>A looping effect (e.g. powder fuse hiss); only one loop at a time.</summary>
        public void PlayLoop(string id)
        {
            if (!Ready || !_sfx.TryGetValue(id, out var s)) return;
            if (_loopSource.isPlaying && _loopSource.clip == s.clips[0]) return;
            _loopSource.clip = s.clips[0];
            _loopSource.volume = s.volume * _sfxVol;
            _loopSource.Play();
        }

        public void StopLoop()
        {
            if (_loopSource != null) _loopSource.Stop();
        }

        public void OnAppPaused(bool paused)
        {
            AudioListener.pause = paused;
        }
    }
}
