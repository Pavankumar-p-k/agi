# Desktop AI Specialist Boundary

Desktop AI is the native Windows computer specialist. It owns computer
interaction and desktop-specific reasoning, but it does not own global JARVIS
coordination.

## Owned by Desktop AI

- Windows and application observations
- UI Automation, mouse, keyboard, clipboard, screenshots, and OCR
- Filesystem, process, and window operations
- Desktop safety, consent, verification, recovery, and rollback
- Desktop routines, task packs, and desktop execution history

## Kept outside Desktop AI

- The user's global objective and cross-specialist task graph
- Coding, research, and global knowledge state
- Capability acquisition and global memory
- Coordination between Desktop AI and other future specialists

## Delegation contract

`core.desktop.specialist.DesktopSpecialist` accepts a
`DesktopExecutionRequest` containing a goal and optional desktop context. It
returns a `DesktopExecutionResult` containing:

- `status`: completed, partial, failed, blocked, or verification_failed
- `result` and desktop observations
- actions taken with evidence and verification state
- recovery attempts, errors, and remaining work

The boundary enforces a no-false-success invariant: a handler response marked
`completed` is normalized to `verification_failed` unless its postcondition is
verified. Permission failures are `blocked`; timeouts and cancellation retain
`partial` status; unexpected implementation errors are returned as `failed`.

`DesktopLocalState` stores active task information, observations, and execution
history for the desktop specialist process. It is not a replacement for global
JARVIS state.

The current agent loop remains the execution backend. Migration toward this
contract is incremental so the existing safety and verification behavior is not
replaced in one risky rewrite.
