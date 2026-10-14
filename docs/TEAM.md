# Team projects

Solo projects remain independent and work offline. Team mode is an explicit connection
to one project host. Every desktop has the same native annotation interface; no browser
is required. The host owns the SQLite database. Do not put a live database on a shared
network drive or edit the host database from multiple machines.

## Host a project

1. Create a project and select **Team**, or open an existing solo project and choose **Team**.
2. Import source images and configure the pipeline/classes on the host computer.
3. In **Team**, start hosting on `0.0.0.0`, port `8765`. The service starts only when requested.
4. Invite each reviewer by name. Give each person their own private token and your host URL,
   such as `http://192.168.1.20:8765`. Do not use `0.0.0.0` as the client URL.
5. The host must remain running. Closing the desktop stops its service. A firewall may
   require an explicit inbound rule; the application does not change firewall rules.

Desktop hosting uses HTTP and is intended for a trusted LAN or private VPN. For TLS:

```powershell
lannotex invite D:\Projects\dataset "Alice"
lannotex host D:\Projects\dataset --bind 0.0.0.0 --port 8765 --cert server.pem --key server-key.pem
```

Clients verify HTTPS certificates with the system trust store. There is no insecure
certificate bypass. Internet deployment, reverse proxies, rate limits and service
supervision require a separate deployment review; this is not a hosted SaaS release.

## Join and continue

Choose **Join team** on Home, enter the URL and your token, and choose an empty private
local cache directory. The app synchronizes metadata and fetches original images as
you open them. It never changes source images. A 256 MiB per-image transfer ceiling
prevents unbounded downloads. A token is not saved to disk; enter it again using
**Team → Reconnect** after restarting. Existing cached projects remain usable offline.

Completed local saves go into the outbox. Synchronization runs every four seconds
when no other file job is active. Network failure retains local work. Distinguish
**Saved locally · queued** from **Synced to team**. The host supplies classes and tasks;
reviewers cannot alter taxonomy, import files into the host, or administer members.

## Conflicts and recovery

Reviewers can annotate different images concurrently. Saving the same image checks
the base revision atomically; the second stale save becomes a conflict. No silent
last-writer-wins replacement occurs. Open **Team** and select a conflict:

- **Use team version** replaces the local conflicting version after confirmation.
- **Publish my version** explicitly replaces the current team version, with another
  revision check in case it changed during resolution.

Saved host versions retain reviewer name, time, revision, annotation JSON and negative
status in `team_audit`. Unsaved edits stay in recovery drafts. Undo history is bounded
to 100 operations for the currently open image; it is not a cross-session history UI.
Host owners receive the same revision-conflict protection when a remote save arrives.
Use **Team → Resolve my current image** if their local draft conflicts.

Tokens can be revoked from the host's Team panel. Revocation blocks subsequent
requests; it does not remotely delete cached images. Reviewers have access to the
whole shared project. The current model has no per-image assignments, blind double
review, approval roles or locked company releases. Those remain separate from local
editable annotation work.

## Exports and backups

Export on the host for a complete dataset; a reviewer cache may not have downloaded
every image, and exports report those records as missing. Backups contain annotations,
drafts, settings, audit history and token hashes, but not source image bytes. Protect
backup files as project data. Source images must also be backed up independently.
