# Security policy

Report suspected vulnerabilities through GitHub private vulnerability reporting when
available, or contact a repository owner through a private channel listed on their
GitHub profile. Do not disclose suspected vulnerabilities in a public issue.

Include affected revisions, impact, reproduction steps, and suggested mitigations. Do
not include credentials, personal data, proprietary database contents, production
prompts, or model inputs in a report.

Before release or deployment, confirm that:

- provider keys and other secrets remain outside the repository and browser bundles;
- logs and traces redact personal data, prompts, tokens, and credentials;
- data retention and deletion behavior is documented;
- dependencies and workflows have passed `make check-all`; and
- incident ownership, rollback, and security-reporting paths are documented.
