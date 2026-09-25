// Stand-in for the one Unity Test Framework type the game's tests use ([UnityTest] from
// com.unity.test-framework, UnityEngine.TestRunner/NUnitExtensions/Attributes/UnityTestAttribute.cs).
// Compile-check only; Unity uses the real package.
namespace UnityEngine.TestTools
{
    [System.AttributeUsage(System.AttributeTargets.Method)]
    public class UnityTestAttribute : System.Attribute { }
}
