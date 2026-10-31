# Labelling bundle: Fixel benchmark, test split, e-broker (seed 7)

Run `20261031-093745-test-s7`: 200 screens (150 with an injected defect or control, 50 unmodified). Do not look inside the
archive before labelling: the case files hold the answers. The labelling view itself is blind.

In a checkout of the `main` branch of this repo, on your machine:

```bash
git fetch origin bench-labelling
git show origin/bench-labelling:20261031-093745-test-s7.bench.tar.gz > /tmp/test-s7.bench.tar.gz
fixel bench import /tmp/test-s7.bench.tar.gz
make serve        # open http://127.0.0.1:8765, Label tab; keys: v visible, n none, u unsure
fixel bench export 20261031-093745-test-s7
git add docs/bench/20261031-093745-test-s7/labels.json && git commit -m "labels" && git push
```

Label only what you can see: content cut off or running off the screen, text overflowing or overlapping other content, a control
covered by something, unreadable low contrast. An open menu or a badge on a button is intentional, not a defect.
