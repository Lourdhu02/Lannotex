# Security Policy

Lannotex is a **local-first application**: it makes no network requests and never
uploads your images or annotations. We still take security seriously.

## Reporting a vulnerability

Please **do not** open a public issue for security problems. Email
`security@lannotex.dev` with:

- A description of the vulnerability and the affected versions.
- Steps to reproduce, including any project/sample data needed.
- Impact assessment, if you have one.

We will acknowledge receipt within 48 hours and work with you on a fix and
disclosure timeline. Reports are handled confidentially.

## Security-relevant design notes

- Annotation and image data never leaves the machine; exports are written to a
  folder the user chooses.
- SQLite connections use WAL mode and `synchronous=FULL` to protect data integrity.
- Labelme import validates image dimensions against the annotation metadata and
  rejects mismatches before writing anything.
- `PRAGMA integrity_check` is run before restoring any backup.
