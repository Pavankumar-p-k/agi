# RC3.3 — Naive-User Testing Protocol

## Before the session

1. **Prepare a clean machine** — fresh OS install or dedicated test VM. No existing Python/JARVIS.
2. **Reset `~/.jarvis/`** — `Move-Item ~/.jarvis ~/.jarvis_bk` (Windows) or `mv ~/.jarvis ~/.jarvis_bk` (Linux)
3. **Set up screen recording** — OBS, Loom, or built-in OS recorder. Capture full screen + audio.
4. **Open the observation sheet** — `observer_sheet.md` ready for note-taking.
5. **Do not prepare any shortcuts, bookmarks, or pinned tabs.**

## Session instructions (read aloud)

> "I'd like you to try installing a tool I've been working on and do something useful with it.
>
> I'm not going to give you any instructions. Just see what happens.
>
> Please think out loud — say whatever comes to mind as you go.
>
> I'll be sitting over here taking notes. If you get stuck, keep trying before asking me.
>
> There's no time limit. Ready?"

## After they agree

**Do not speak unless:**
- They are clearly distressed (not just confused)
- They ask for clarification
- You need to stop the session for safety reasons

**When they ask a question, answer with:**
- "What do you think?"
- "Try whatever feels right."
- "I can't answer that during the test, but we can talk about it after."

**Never say:**
- "Click here"
- "Type this"
- "That's the wrong button"
- "Let me explain what JARVIS can do"

## Tasks

### Task 1 — Install and setup
Goal: Get JARVIS installed and running for the first time.

**User prompt:** None — just the initial description above.

**Success criteria:**
- Installed with `pip install jarvis-ai`
- Ran `jarvis` or `jarvis chat` or similar
- Completed or partially completed setup wizard
- Understood what JARVIS is (in their own words)

### Task 2 — Do something useful
Goal: Complete a real task in under 10 minutes.

**User prompt (only if they ask "What should I do?"):**
> "Build me a portfolio website."

**Success criteria:**
- Creates a project or starts a build
- Makes reasonable progress
- Understands the output

### Task 3 — Explore
Goal: Find any feature without being told about it.

**Success criteria:**
- Discovers at least one feature they didn't know existed
- Tries it without being prompted

## When to end the session

- User completes all 3 tasks
- 30 minutes elapsed
- User asks to stop
- User is visibly frustrated

## After the session

1. Save the screen recording as `RC3_3_{participant_number}_{date}.mp4`
2. Fill in the scoring sheet (`scoring.md`)
3. Ask the post-session questions (`post_session_questions.md`)
4. Write a one-paragraph summary of anything surprising
