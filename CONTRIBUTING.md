# Contributing

After the one-time bootstrap, start from updated `main` on a focused branch:

```bash
git switch main
git pull --ff-only origin main
git switch -c feat/short-description
make sync
make hooks
```

Use `feat/`, `fix/`, `docs/`, `test/`, or `chore/` prefixes. Each commit should represent
one logical change, include concrete tests for behavioral changes, and leave the
repository valid. Run `make check-all` before pushing and open a draft pull request.

Never force-push, bypass hooks, push directly to `main` after bootstrap, or merge a pull
request without explicit approval from Tony Kwok.

Pull requests should explain the problem, the minimal approach, verification evidence,
and any security, privacy, licensing, migration, operational, or rollback impact.
