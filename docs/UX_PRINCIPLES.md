# JARVIS UX Principles

## Rule 1 — Never expose infrastructure before user value

Users should see outcomes, not internals. Activity graphs, provider lifecycles, decision traces — these are implementation details. Show them only when the user asks "why" or when Developer Mode is enabled.

## Rule 2 — Every screen answers one question

| Screen | Question |
|--------|----------|
| Home | What do you want to accomplish? |
| Chat | What is it doing right now? |
| Tasks | What's running? What's done? |
| History | What happened before? |
| System | Is JARVIS healthy? |
| Settings | How do I configure it? |

If a screen tries to answer two questions, split it.

## Rule 3 — Show execution before configuration

A new user should see a working system before touching any settings. Setup wizard then demo then Home — not a blank Settings page.

## Rule 4 — Everything begins with a goal

The command bar is the center of the product. Every page has it: "What would you like JARVIS to do?" No action should require navigating to a specific page first.

## Rule 5 — Developers can reveal internals. Users never need to.

| Audience | Sees |
|----------|------|
| New user | Home, Chat, demo |
| Daily user | Home, Chat, Tasks, History, System, Settings |
| Power user | Settings → Advanced options |
| Developer | Developer Mode: Activity Graph, Decision Trace, Capability Graph, Experiments, Knowledge Store, Diagnostics, Backend |

A toggle in Settings enables Developer Mode. Default: off. When toggled on, it reveals infrastructure pages. This is the only way those pages should appear in navigation.

## Why These Rules Exist

The UI drifted into a feature catalog because we treated all subsystems as equal. These rules prevent that. Every new feature is reviewed against them before merge.
