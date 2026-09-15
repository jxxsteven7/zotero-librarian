# Contributing

Issues and pull requests are both welcome — especially taxonomies for other fields, eval results on other libraries, and reports from other
agents or Zotero setups. If you have not done this on GitHub before, this is the whole procedure:

**Report a bug or ask for a feature — open an issue.** Go to the repository's *Issues* tab, *New issue*, pick the
template. For a bug, paste the output of `python3 zl.py setup` and of the command that failed (the scripts never print
your API key, but check before pasting), and say which agent and OS you use. For a feature, say what you would type
and what should happen. An issue is also the right place to discuss a change before writing it, so nobody codes
something that won't be merged.

**Contribute code — open a pull request.**

1. *Fork* the repository (button top right) and clone your fork: `git clone https://github.com/<you>/zotero-librarian.git`.
2. Make a branch for the one thing you are changing: `git checkout -b my-change`.
3. Change it. Keep the rules in `AGENTS.md`: standard library only; runs on Ubuntu, macOS and Windows; skills stay
   agent-neutral and `.agents/skills` / `.claude/skills` identical (`python3 zl.py setup --sync-skills`); everything in
   English.
4. Check it: `python3 zl.py setup --offline` and `python3 -m unittest discover -s tests` pass (neither needs a Zotero
   library; CI runs both on Ubuntu, macOS and Windows for every PR, so a failure there is not a surprise), and if you
   touched `taxonomy.toml` or the classifier, `python3 tools/eval_classify.py` before and after (precision must not
   drop; paste both numbers in the PR). A new rule or a fixed corner case gets a synthetic case in `tests/`.
5. Commit and push to your fork: `git commit` with a message written the way Google's
   [*Writing good CL descriptions*](https://google.github.io/eng-practices/review/developer/cl-descriptions.html)
   says — a first line that is a short imperative summary standing on its own ("Add a taxonomy for NLP" rather than
   "changes"), a blank line, then *what* and *why* (the problem, your approach, limitations, numbers) — and
   `git push -u origin my-change`.
6. On GitHub, *Compare & pull request*. The template asks what changed, why, how you tested it and on which
   platform / agent. One feature per PR; small PRs are reviewed faster.
7. Review follows Google's [*The Standard of Code Review*](https://google.github.io/eng-practices/review/reviewer/standard.html):
   a PR is approved once it clearly improves the code overall, even if it isn't perfect; facts and data over opinions;
   `AGENTS.md` and consistency with the existing code settle style; comments marked `Nit:` are optional. The
   maintainer may ask for changes (push more commits to the same branch), then merges with a `vX.Y: ...` commit that
   bumps `__version__` and adds your line to `CHANGELOG.md`. You don't need to touch the version yourself.

A taxonomy for another field is the most useful contribution: copy `taxonomy.toml`, replace the collections and
values, run the eval on your own tagged library, and send it as `taxonomies/<field>.toml` with the numbers.
