using EvilCats.Content;
using NUnit.Framework;

namespace EvilCats.Tests
{
    public class ContentTests
    {
        [Test]
        public void ContentLoadsWithoutErrors()
        {
            var c = TestContent.Load();
            Assert.That(c.LoadErrors, Is.Empty, string.Join("\n", c.LoadErrors));
        }

        [Test]
        public void ContentPassesValidation()
        {
            var report = ContentValidator.Validate(TestContent.Load());
            TestContext.WriteLine(report.ToString());
            Assert.That(report.Errors, Is.Empty, report.ToString());
        }

        [Test]
        public void ScopeMatchesVersionOne()
        {
            var c = TestContent.Load();
            Assert.That(c.Modules.Count, Is.EqualTo(6));
            Assert.That(c.Perks.Count, Is.EqualTo(30));
            Assert.That(c.Bosses.Count, Is.EqualTo(3));
            Assert.That(c.Missions.Count, Is.EqualTo(12));
            Assert.That(c.Upgrades.Count, Is.EqualTo(6));
            int ordinary = 0;
            foreach (var e in c.Enemies) if (!e.isUnitOnly) ordinary++;
            Assert.That(ordinary, Is.EqualTo(8));
            Assert.That(c.Progression.achievements.Count, Is.GreaterThanOrEqualTo(18));
        }

        [Test]
        public void ValidatorCatchesDuplicateIdsAndBrokenReferences()
        {
            var c = TestContent.Fresh();
            c.Perks.Add(new PerkDef { id = "arc_forked_bolt", family = "arc", rarity = "common", maxStacks = 1 });
            c.Missions[3].requiresMission = "m99";
            c.Perks[0].requiresModules.Add("laser_cat");
            c.BuildIndexes();
            var r = ContentValidator.Validate(c);
            Assert.That(r.Errors.Exists(e => e.Contains("duplicate perk id")), Is.True, r.ToString());
            Assert.That(r.Errors.Exists(e => e.Contains("m04") && e.Contains("previous mission")), Is.True, r.ToString());
            Assert.That(r.Errors.Exists(e => e.Contains("laser_cat")), Is.True, r.ToString());
        }

        [Test]
        public void ValidatorCatchesImpossiblePerkRequirements()
        {
            var c = TestContent.Fresh();
            var p = c.Perk("frost_shatter");
            p.requiresAnyPerk.Add("frost_shatter");
            var r = ContentValidator.Validate(c);
            Assert.That(r.Errors.Exists(e => e.Contains("requires itself")), Is.True, r.ToString());
        }

        [Test]
        public void ValidatorCatchesUnreachableEnemies()
        {
            var c = TestContent.Fresh();
            c.Enemy("crow_archer").attackRange = 9.5f;
            var r = ContentValidator.Validate(c);
            Assert.That(r.Errors.Exists(e => e.Contains("crow_archer") && e.Contains("unreachable")), Is.True, r.ToString());
        }

        [Test]
        public void PerkDescriptionsShowExactValues()
        {
            var c = TestContent.Load();
            string pct = TextFormat.Percent(c.Perk("arc_static_mark").p["bonus"]);
            Assert.That(TextFormat.Perk(c, c.Perk("arc_static_mark")), Does.Contain("+" + pct + " Arc damage"), "description follows the data value");
            Assert.That(TextFormat.Perk(c, c.Perk("arc_overcharged_crown")), Does.Contain("-15%").And.Contain("+30%"));
            Assert.That(TextFormat.Perk(c, c.Perk("gravity_unstable_singularity")), Does.Contain("+35%"));
            Assert.That(TextFormat.Perk(c, c.Perk("frost_frozen_oath")), Does.Contain("need 1 fewer"));
            foreach (var p in c.Perks) Assert.That(TextFormat.Perk(c, p), Does.Not.Contain("{"), p.id);
        }
    }
}
