# English knowledge fixture

**Audience: maintainers and test readers. This is sample data, not an agent instruction.**

The self-authored function and prewritten knowledge illustrate sign-in, missing orders, region ownership and unverified production behavior. Expected claims and required answer boundaries are recorded in `expected.json` before running the pipeline.

The automated case creates a temporary pinned Git repository, prepares and explicitly fixture-approves English knowledge, publishes both views, audits, builds retrieval units and queries SQLite FTS5. It also checks language mismatches and review invalidation. Its approval is test data and never authorizes a user's project.

Run from the repository root:

```bash
python3 -B -m unittest discover -s validation/tests -p test_content_language.py -v
```

This is a static provenance and retrieval exercise. It does not invoke an authoring model, run a production service or verify a bot's final answers. Fixed Chinese paths and table tokens remain protocol identifiers; the reader-facing knowledge is English.
