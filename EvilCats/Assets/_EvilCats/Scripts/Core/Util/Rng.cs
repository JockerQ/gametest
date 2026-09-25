using System;
using System.Collections.Generic;

namespace EvilCats.Core
{
    /// <summary>Serializable RNG state so runs can be checkpointed and resumed exactly.</summary>
    [Serializable]
    public struct RngState
    {
        public ulong state;
        public ulong inc;
    }

    /// <summary>
    /// PCG32 random number generator (O'Neill). Deterministic on every platform because it
    /// only uses 64-bit integer arithmetic. Never use System.Random or UnityEngine.Random
    /// inside the simulation.
    /// </summary>
    public sealed class Rng
    {
        private ulong _state;
        private ulong _inc;

        public Rng(ulong seed, ulong stream = 54u)
        {
            _state = 0;
            _inc = (stream << 1) | 1u;
            NextUInt();
            _state += seed;
            NextUInt();
        }

        public Rng(RngState s)
        {
            _state = s.state;
            _inc = s.inc | 1u;
        }

        public RngState State => new RngState { state = _state, inc = _inc };

        public void Restore(RngState s)
        {
            _state = s.state;
            _inc = s.inc | 1u;
        }

        public uint NextUInt()
        {
            ulong old = _state;
            _state = unchecked(old * 6364136223846793005UL + _inc);
            uint xorshifted = (uint)(((old >> 18) ^ old) >> 27);
            int rot = (int)(old >> 59);
            return (xorshifted >> rot) | (xorshifted << ((-rot) & 31));
        }

        /// <summary>Uniform float in [0, 1).</summary>
        public float NextFloat() => (NextUInt() >> 8) * (1.0f / 16777216.0f);

        /// <summary>Uniform float in [min, max).</summary>
        public float Range(float min, float max) => min + (max - min) * NextFloat();

        /// <summary>Uniform int in [min, maxExclusive). Unbiased (rejection sampling).</summary>
        public int Range(int min, int maxExclusive)
        {
            if (maxExclusive <= min) return min;
            uint bound = (uint)(maxExclusive - min);
            uint threshold = (uint)((0x100000000UL - bound) % bound);
            while (true)
            {
                uint r = NextUInt();
                if (r >= threshold) return min + (int)(r % bound);
            }
        }

        public bool Chance(float p) => p > 0f && (p >= 1f || NextFloat() < p);

        public T Pick<T>(IList<T> list) => list[Range(0, list.Count)];

        public int WeightedIndex(IList<float> weights)
        {
            float total = 0f;
            for (int i = 0; i < weights.Count; i++) total += Math.Max(0f, weights[i]);
            if (total <= 0f) return -1;
            float r = NextFloat() * total;
            for (int i = 0; i < weights.Count; i++)
            {
                float w = Math.Max(0f, weights[i]);
                if (r < w) return i;
                r -= w;
            }
            for (int i = weights.Count - 1; i >= 0; i--) if (weights[i] > 0f) return i;
            return -1;
        }

        public void Shuffle<T>(IList<T> list)
        {
            for (int i = list.Count - 1; i > 0; i--)
            {
                int j = Range(0, i + 1);
                T tmp = list[i];
                list[i] = list[j];
                list[j] = tmp;
            }
        }

        /// <summary>Derive an independent seed for a sub-stream (e.g. per wave).</summary>
        public static ulong Mix(ulong a, ulong b)
        {
            unchecked
            {
                ulong z = a ^ (b + 0x9E3779B97F4A7C15UL + (a << 6) + (a >> 2));
                z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9UL;
                z = (z ^ (z >> 27)) * 0x94D049BB133111EBUL;
                return z ^ (z >> 31);
            }
        }
    }

    public static class Hash
    {
        /// <summary>FNV-1a 64-bit hash of a string (UTF-16 code units). Stable across platforms.</summary>
        public static ulong Fnv1a64(string s)
        {
            unchecked
            {
                ulong h = 14695981039346656037UL;
                if (s == null) return h;
                for (int i = 0; i < s.Length; i++)
                {
                    char c = s[i];
                    h ^= (byte)(c & 0xFF);
                    h *= 1099511628211UL;
                    h ^= (byte)(c >> 8);
                    h *= 1099511628211UL;
                }
                return h;
            }
        }

        public static string ToHex(ulong v) => v.ToString("x16");
    }
}
