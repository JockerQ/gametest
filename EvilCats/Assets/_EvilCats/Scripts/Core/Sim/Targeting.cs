using System;
using System.Collections.Generic;
using EvilCats.Content;
using EvilCats.Core;

namespace EvilCats.Sim
{
    /// <summary>Pure target-selection functions (unit tested). Ties break by lowest uid for determinism.</summary>
    public static class Targeting
    {
        public static bool Valid(Enemy e) => e != null && e.alive && e.hp > 0f;

        /// <summary>
        /// Nearest = closest to the citadel. Strongest = highest current health.
        /// RangedThreat = ranged/support enemies (archers, priests, ranged bosses) first, then nearest.
        /// </summary>
        public static Enemy Select(IReadOnlyList<Enemy> enemies, Vec2 origin, float range, TargetPriority priority, int excludeUid = 0)
        {
            Enemy best = null;
            float bestKey = 0f;
            float bestDist = 0f;
            bool bestIsThreat = false;
            float r2 = range * range;
            for (int i = 0; i < enemies.Count; i++)
            {
                var e = enemies[i];
                if (!Valid(e) || e.uid == excludeUid) continue;
                float d2 = Vec2.SqrDistance(e.pos, origin);
                if (d2 > r2) continue;
                bool threat = IsThreat(e);
                bool better;
                if (best == null) better = true;
                else if (priority == TargetPriority.Strongest)
                {
                    better = e.hp > bestKey + 1e-3f || (Math.Abs(e.hp - bestKey) <= 1e-3f && (d2 < bestDist || (d2 == bestDist && e.uid < best.uid)));
                }
                else if (priority == TargetPriority.RangedThreat && threat != bestIsThreat)
                {
                    better = threat;
                }
                else
                {
                    better = d2 < bestDist - 1e-6f || (Math.Abs(d2 - bestDist) <= 1e-6f && e.uid < best.uid);
                }
                if (better)
                {
                    best = e;
                    bestKey = e.hp;
                    bestDist = d2;
                    bestIsThreat = threat;
                }
            }
            return best;
        }

        public static bool IsThreat(Enemy e) =>
            e.role == EnemyRole.Ranged || e.role == EnemyRole.Support || (e.isBoss && e.attackRange > 3.5f);

        /// <summary>Enemy with the most neighbours within clusterRadius (for chain/area modules).</summary>
        public static Enemy ClusterTarget(IReadOnlyList<Enemy> enemies, Vec2 origin, float range, float clusterRadius, TargetPriority priority)
        {
            Enemy best = null;
            int bestCount = -1;
            float bestDist = float.MaxValue;
            float r2 = range * range, c2 = clusterRadius * clusterRadius;
            for (int i = 0; i < enemies.Count; i++)
            {
                var e = enemies[i];
                if (!Valid(e) || Vec2.SqrDistance(e.pos, origin) > r2) continue;
                int count = 0;
                for (int j = 0; j < enemies.Count; j++)
                {
                    var o = enemies[j];
                    if (Valid(o) && Vec2.SqrDistance(o.pos, e.pos) <= c2) count++;
                }
                float d2 = Vec2.SqrDistance(e.pos, origin);
                if (count > bestCount || (count == bestCount && (d2 < bestDist || (d2 == bestDist && best != null && e.uid < best.uid))))
                {
                    best = e;
                    bestCount = count;
                    bestDist = d2;
                }
            }
            if (best != null && bestCount <= 1) return Select(enemies, origin, range, priority);
            return best;
        }

        /// <summary>
        /// Best point for an area effect of `radius` among enemies within `range` of origin.
        /// Score = Σ weight (ordinary 1, elite 2, boss 3 unless excluded). Returns false when nothing is in range.
        /// </summary>
        public static bool BestCluster(IReadOnlyList<Enemy> enemies, Vec2 origin, float range, float radius, bool excludeBosses,
            bool excludeImmobile, out Vec2 point, out int count)
        {
            point = Vec2.Zero;
            count = 0;
            float bestScore = 0f;
            Enemy bestCenter = null;
            float r2 = range * range, rad2 = radius * radius;
            for (int i = 0; i < enemies.Count; i++)
            {
                var e = enemies[i];
                if (!Valid(e) || Vec2.SqrDistance(e.pos, origin) > r2) continue;
                if (excludeBosses && e.isBoss) continue;
                if (excludeImmobile && e.displacementImmune) continue;
                float score = 0f;
                int n = 0;
                for (int j = 0; j < enemies.Count; j++)
                {
                    var o = enemies[j];
                    if (!Valid(o)) continue;
                    if (excludeBosses && o.isBoss) continue;
                    if (Vec2.SqrDistance(o.pos, e.pos) > rad2) continue;
                    score += o.isBoss ? 3f : (o.elite ? 2f : 1f);
                    n++;
                }
                if (score > bestScore + 1e-4f || (Math.Abs(score - bestScore) <= 1e-4f && bestCenter != null && e.uid < bestCenter.uid))
                {
                    bestScore = score;
                    bestCenter = e;
                    count = n;
                }
            }
            if (bestCenter == null) return false;
            // centroid of the enemies around the best centre, for better coverage
            Vec2 sum = Vec2.Zero;
            int m = 0;
            for (int j = 0; j < enemies.Count; j++)
            {
                var o = enemies[j];
                if (!Valid(o) || (excludeBosses && o.isBoss)) continue;
                if (Vec2.SqrDistance(o.pos, bestCenter.pos) > rad2) continue;
                sum += o.pos;
                m++;
            }
            point = m > 0 ? sum / m : bestCenter.pos;
            return true;
        }

        /// <summary>Nearest valid enemy to `from` within range that is not in `exclude` (chain hops).</summary>
        public static Enemy NearestExcluding(IReadOnlyList<Enemy> enemies, Vec2 from, float range, List<int> exclude,
            float slowedRangeMult = 1f)
        {
            Enemy best = null;
            float bestD = float.MaxValue;
            for (int i = 0; i < enemies.Count; i++)
            {
                var e = enemies[i];
                if (!Valid(e) || exclude.Contains(e.uid)) continue;
                float r = e.IsSlowed ? range * slowedRangeMult : range;
                float d2 = Vec2.SqrDistance(e.pos, from);
                if (d2 > r * r) continue;
                if (d2 < bestD || (d2 == bestD && best != null && e.uid < best.uid))
                {
                    best = e;
                    bestD = d2;
                }
            }
            return best;
        }
    }
}
