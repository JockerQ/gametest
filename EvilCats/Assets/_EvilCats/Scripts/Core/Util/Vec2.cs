using System;

namespace EvilCats.Core
{
    /// <summary>Minimal 2D vector for the simulation (world units, +y up). No UnityEngine dependency.</summary>
    [Serializable]
    public struct Vec2 : IEquatable<Vec2>
    {
        public float x;
        public float y;

        public Vec2(float x, float y)
        {
            this.x = x;
            this.y = y;
        }

        public static readonly Vec2 Zero = new Vec2(0f, 0f);
        public static readonly Vec2 Up = new Vec2(0f, 1f);

        public float SqrLength => x * x + y * y;
        public float Length => MathF.Sqrt(x * x + y * y);

        public Vec2 Normalized
        {
            get
            {
                float l = Length;
                return l > 1e-6f ? new Vec2(x / l, y / l) : Zero;
            }
        }

        public static Vec2 operator +(Vec2 a, Vec2 b) => new Vec2(a.x + b.x, a.y + b.y);
        public static Vec2 operator -(Vec2 a, Vec2 b) => new Vec2(a.x - b.x, a.y - b.y);
        public static Vec2 operator -(Vec2 a) => new Vec2(-a.x, -a.y);
        public static Vec2 operator *(Vec2 a, float s) => new Vec2(a.x * s, a.y * s);
        public static Vec2 operator *(float s, Vec2 a) => new Vec2(a.x * s, a.y * s);
        public static Vec2 operator /(Vec2 a, float s) => new Vec2(a.x / s, a.y / s);

        public static float Dot(Vec2 a, Vec2 b) => a.x * b.x + a.y * b.y;
        public static float Cross(Vec2 a, Vec2 b) => a.x * b.y - a.y * b.x;
        public static float Distance(Vec2 a, Vec2 b) => (a - b).Length;
        public static float SqrDistance(Vec2 a, Vec2 b) => (a - b).SqrLength;
        public static Vec2 Lerp(Vec2 a, Vec2 b, float t) => new Vec2(a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t);
        public Vec2 Perp => new Vec2(-y, x);

        public static Vec2 FromAngle(float radians, float length = 1f) =>
            new Vec2(MathF.Cos(radians) * length, MathF.Sin(radians) * length);

        public float Angle => MathF.Atan2(y, x);

        /// <summary>Move from a toward b by at most maxStep.</summary>
        public static Vec2 MoveTowards(Vec2 a, Vec2 b, float maxStep)
        {
            Vec2 d = b - a;
            float l = d.Length;
            if (l <= maxStep || l < 1e-6f) return b;
            return a + d * (maxStep / l);
        }

        /// <summary>Squared distance from point p to segment ab.</summary>
        public static float SqrDistanceToSegment(Vec2 p, Vec2 a, Vec2 b)
        {
            Vec2 ab = b - a;
            float len2 = ab.SqrLength;
            if (len2 < 1e-8f) return SqrDistance(p, a);
            float t = MathX.Clamp01(Dot(p - a, ab) / len2);
            return SqrDistance(p, a + ab * t);
        }

        public bool Equals(Vec2 o) => x == o.x && y == o.y;
        public override bool Equals(object obj) => obj is Vec2 v && Equals(v);
        public override int GetHashCode() => (x.GetHashCode() * 397) ^ y.GetHashCode();
        public override string ToString() => $"({x:0.##}, {y:0.##})";
    }

    public static class MathX
    {
        public const float Pi = 3.14159265358979f;
        public const float TwoPi = Pi * 2f;
        public const float Deg2Rad = Pi / 180f;

        public static float Clamp(float v, float min, float max) => v < min ? min : (v > max ? max : v);
        public static int Clamp(int v, int min, int max) => v < min ? min : (v > max ? max : v);
        public static float Clamp01(float v) => v < 0f ? 0f : (v > 1f ? 1f : v);
        public static float Lerp(float a, float b, float t) => a + (b - a) * t;
        public static float InverseLerp(float a, float b, float v) => Math.Abs(b - a) < 1e-9f ? 0f : Clamp01((v - a) / (b - a));
        public static float Approach(float v, float target, float step) => v < target ? Math.Min(v + step, target) : Math.Max(v - step, target);
        public static int CeilToInt(double v) => (int)Math.Ceiling(v - 1e-9);
        public static int FloorToInt(double v) => (int)Math.Floor(v + 1e-9);
        public static int RoundToInt(float v) => (int)Math.Round(v, MidpointRounding.AwayFromZero);

        /// <summary>Wrap an angle to (-pi, pi].</summary>
        public static float WrapAngle(float a)
        {
            while (a > Pi) a -= TwoPi;
            while (a <= -Pi) a += TwoPi;
            return a;
        }

        public static float SmoothStep(float t)
        {
            t = Clamp01(t);
            return t * t * (3f - 2f * t);
        }
    }
}
