// Minimal stand-ins for the only Input System (com.unity.inputsystem 1.20.0) types the game
// scripts use, so they can be compiled outside Unity. Names, namespaces and member shapes were
// checked against the package source (Runtime/Devices/Keyboard.cs, Runtime/Controls/ButtonControl.cs,
// Runtime/Controls/KeyControl.cs, Runtime/Plugins/UI/InputSystemUIInputModule.cs).
// This assembly is NEVER shipped; Unity uses the real package.
namespace UnityEngine.InputSystem.Controls
{
    public class AxisControl { }

    public class ButtonControl : AxisControl
    {
        public bool isPressed => false;
        public bool wasPressedThisFrame => false;
        public bool wasReleasedThisFrame => false;
    }

    public class KeyControl : ButtonControl { }
}

namespace UnityEngine.InputSystem
{
    using UnityEngine.InputSystem.Controls;

    public class InputDevice { }

    public class Keyboard : InputDevice
    {
        public static Keyboard current { get; private set; }
        public KeyControl escapeKey => null;
    }
}

namespace UnityEngine.InputSystem.UI
{
    public class InputSystemUIInputModule : UnityEngine.EventSystems.BaseInputModule
    {
        public override void Process() { }
    }
}
