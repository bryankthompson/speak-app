# speak: what every cockpit session needs to know (canonical text; embed or link, do not copy-edit)

- Speak a cockpit line as `speak "<session name>: <clause>"`, a clause from `~/speak-app/phrases/casting.json`
  spelled exactly as listed (stored clips play free; other text of 10 words or fewer is spoken once, then stored).
- A repo speaks only if it is enabled: `speak --here on` inside it (once per repo; lanes follow their main checkout).
  Not enabled means `speak` prints `skipped: ...` and exits 0. `speak --here` shows the state.
- Warnings that must be heard in every repo (errors, safety blocks, spend or credit limits, disk or key problems) use
  `speak --alert "text"`. Everything else follows the repo's setting.
- `speak --profiles` lists voices and who has which; `speak --repos` shows who spoke or was skipped in the last 7 days.
- Details: docs/VOICES.md and docs/VOICES-COCKPIT.md in the speak-app checkout.
