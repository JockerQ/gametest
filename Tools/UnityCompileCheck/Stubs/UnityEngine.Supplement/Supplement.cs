// Engine APIs that exist in Unity 6.3 but are missing from the NuGet 2021.3 reference assemblies
// used by this check (they were built from a desktop player, which leaves out handheld-only
// bindings). Each entry was checked against Unity-Technologies/UnityCsReference tag 6000.3.9f1:
//   Handheld.Vibrate()  ->  Runtime/Export/Handheld/Handheld.bindings.cs
// Compile-check only; never part of the game.
namespace UnityEngine
{
    public class Handheld
    {
        public static void Vibrate() { }
    }
}
