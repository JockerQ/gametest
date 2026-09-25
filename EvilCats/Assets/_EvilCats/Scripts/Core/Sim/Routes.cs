using System;
using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Core;

namespace EvilCats.Sim
{
    /// <summary>
    /// A curved approach route: control points from the arena edge towards the citadel,
    /// smoothed with Catmull-Rom and resampled by arc length so enemies move at a
    /// constant speed. Routes end at the approach radius; enemies then take a ring slot.
    /// </summary>
    public sealed class Route
    {
        public readonly string id;
        public readonly string tag;
        private readonly List<Vec2> _pts = new List<Vec2>();
        private readonly List<float> _cum = new List<float>();
        public float Length { get; private set; }
        public Vec2 Start => _pts[0];
        public Vec2 End => _pts[_pts.Count - 1];
        public IReadOnlyList<Vec2> Points => _pts;

        public Route(RouteDef def, int samplesPerSegment = 10)
        {
            id = def.id;
            tag = string.IsNullOrEmpty(def.tag) ? "any" : def.tag;
            var ctrl = new List<Vec2>();
            foreach (var p in def.points) ctrl.Add(new Vec2(p[0], p[1]));
            if (ctrl.Count < 2) throw new ArgumentException($"route {def.id} needs at least 2 points");
            for (int i = 0; i < ctrl.Count - 1; i++)
            {
                Vec2 p0 = ctrl[Math.Max(0, i - 1)], p1 = ctrl[i], p2 = ctrl[i + 1], p3 = ctrl[Math.Min(ctrl.Count - 1, i + 2)];
                for (int s = 0; s < samplesPerSegment; s++)
                {
                    float t = s / (float)samplesPerSegment;
                    _pts.Add(CatmullRom(p0, p1, p2, p3, t));
                }
            }
            _pts.Add(ctrl[ctrl.Count - 1]);
            _cum.Add(0f);
            for (int i = 1; i < _pts.Count; i++) _cum.Add(_cum[i - 1] + Vec2.Distance(_pts[i - 1], _pts[i]));
            Length = _cum[_cum.Count - 1];
        }

        private static Vec2 CatmullRom(Vec2 p0, Vec2 p1, Vec2 p2, Vec2 p3, float t)
        {
            float t2 = t * t, t3 = t2 * t;
            return 0.5f * ((2f * p1) + (-1f * p0 + p2) * t + (2f * p0 - 5f * p1 + 4f * p2 - p3) * t2 + (-1f * p0 + 3f * p1 - 3f * p2 + p3) * t3);
        }

        /// <summary>Position at arc-length distance d (clamped), plus the unit tangent.</summary>
        public Vec2 Sample(float d, out Vec2 tangent)
        {
            if (d <= 0f)
            {
                tangent = (_pts[1] - _pts[0]).Normalized;
                return _pts[0];
            }
            if (d >= Length)
            {
                tangent = (_pts[_pts.Count - 1] - _pts[_pts.Count - 2]).Normalized;
                return _pts[_pts.Count - 1];
            }
            int lo = 0, hi = _cum.Count - 1;
            while (hi - lo > 1)
            {
                int mid = (lo + hi) >> 1;
                if (_cum[mid] <= d) lo = mid; else hi = mid;
            }
            float seg = _cum[hi] - _cum[lo];
            float t = seg > 1e-6f ? (d - _cum[lo]) / seg : 0f;
            tangent = (_pts[hi] - _pts[lo]).Normalized;
            return Vec2.Lerp(_pts[lo], _pts[hi], t);
        }

        public Vec2 Sample(float d) => Sample(d, out _);

        /// <summary>Position including a lateral offset (perpendicular to the path).</summary>
        public Vec2 SampleOffset(float d, float lateral)
        {
            Vec2 p = Sample(d, out var tan);
            return p + tan.Perp * lateral;
        }
    }

    public sealed class RouteSet
    {
        public readonly List<Route> routes = new List<Route>();
        public readonly string layoutId;

        public RouteSet(RouteLayoutDef layout)
        {
            layoutId = layout.id;
            foreach (var r in layout.routes) routes.Add(new Route(r));
        }

        public List<int> IndicesWithTag(string tag)
        {
            var list = new List<int>();
            for (int i = 0; i < routes.Count; i++)
                if (tag == "any" || routes[i].tag == tag) list.Add(i);
            if (list.Count == 0) for (int i = 0; i < routes.Count; i++) list.Add(i);
            return list;
        }
    }
}
