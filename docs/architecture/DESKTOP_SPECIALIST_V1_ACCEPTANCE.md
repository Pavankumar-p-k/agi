# Desktop Specialist v1 Acceptance Baseline

**Status:** Hardened Specialist v1  
**Scope:** Native Windows desktop specialist only  

## Acceptance gates

| Gate | Result |
|---|---|
| Desktop-named unit tests | 67 passed |
| Foundation, specialist, and safety tests | 17 passed |
| Adapter, task-pack, and registry gates | 26 passed |
| Desktop module compilation | Passed |
| Concurrent specialist execution | 5 concurrent requests, 5 history records |
| Live UI Automation enumeration | 7 UIA windows observed |
| Live window observation | 8 titled windows observed |
| Physical controller smoke test | Mouse/window observation passed |
| Safety regression | Excessive mouse speed correctly denied |

## Frozen architecture

Desktop AI remains a native computer specialist. Its stable boundary is
`DesktopSpecialist`, which accepts a desktop goal and context and returns
structured status, observations, actions, verification, errors, recovery
attempts, and remaining work.

The specialist owns desktop-local state and desktop safety. It does not own
global JARVIS coordination, cross-specialist planning, research knowledge, or
coding state.

The existing desktop agent remains the execution backend. Tool migration is
incremental through the canonical `ToolRegistry`; the proven legacy runtime is
not replaced by a parallel general-purpose reasoning system.

## Known environmental boundary

The broader repository test collection contains unrelated pre-existing import
failures outside the desktop specialist scope. They are not part of this
acceptance baseline and were not changed as part of the desktop freeze.
