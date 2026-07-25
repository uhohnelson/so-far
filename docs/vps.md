# Oracle VPS guide

How to reach and manage the Always Free VM that runs Sofar.

## Specs

| Item | Value |
|------|--------|
| Provider | Oracle Cloud (Always Free) |
| Shape | `VM.Standard.E2.1.Micro` |
| CPU | 1 OCPU (shows as ~2 CPUs in Cockpit) |
| RAM | ~1 GB |
| Swap | 1 GB (`/swapfile`) |
| Disk | ~50 GB boot volume (~43 GB free at last check) |
| Region | Germany Central (Frankfurt) |
| Public IP | `141.144.228.144` |
| OS | Ubuntu 22.04 |
| SSH user | `ubuntu` |

This box is small. Fine for Sofar + Cockpit. Do not run heavy builds or a full remote desktop here.

## SSH (simplest)

On the Mac, SSH config already has a short alias:

```bash
ssh vps
```

That uses:

- Host: `141.144.228.144`
- User: `ubuntu`
- Key: `~/Downloads/Code_and_Config/ssh-key-2026-07-21.key`

If the alias is missing, add this to `~/.ssh/config`:

```text
Host vps
  HostName 141.144.228.144
  User ubuntu
  IdentityFile ~/Downloads/Code_and_Config/ssh-key-2026-07-21.key
```

Then:

```bash
chmod 400 ~/Downloads/Code_and_Config/ssh-key-2026-07-21.key
ssh vps
```

## Cockpit (web console)

Cockpit is installed for a browser UI: overview, logs, services, terminal, updates.

URL on the server: port **9090**.

### Recommended access (SSH tunnel)

Do **not** need to open 9090 on the public internet.

1. Set a password once (Cockpit needs it; SSH key login alone is not enough for the web login):

```bash
ssh vps
sudo passwd ubuntu
exit
```

2. Open a tunnel from your Mac:

```bash
ssh -L 9090:localhost:9090 vps
```

3. In the browser open: [https://localhost:9090](https://localhost:9090)

4. Accept the self-signed certificate warning.

5. Log in as `ubuntu` with the password you set.

Leave the tunnel terminal open while you use Cockpit.

### Optional: public Cockpit URL

Only if you want `https://141.144.228.144:9090` without a tunnel.

1. Oracle Cloud Console → Networking → VCN → Security List (or NSG for the instance).
2. Add **Ingress**: TCP **9090**, source = your home IP if possible (safer than `0.0.0.0/0`).
3. Open `https://141.144.228.144:9090` and log in as `ubuntu`.

Prefer the tunnel unless you really need public access.

### Optional package

Cockpit may show: missing `cockpit-pcp` for metrics history.

Skip it on this 1 GB box unless you want historical graphs. To install:

```bash
ssh vps
sudo apt update
sudo apt install -y cockpit-pcp
sudo systemctl restart cockpit
```

## What runs on this VPS

### Sofar bot (active)

| Item | Path / unit |
|------|-------------|
| App directory | `/home/ubuntu/so-far` |
| Env file | `/home/ubuntu/so-far/.env` (chmod 600) |
| Database | `/home/ubuntu/so-far/data/sofar.db` |
| systemd unit | `sofar-bot.service` |
| Memory cap | ~350 MB max (see unit file) |

Useful commands:

```bash
ssh vps
sudo systemctl status sofar-bot
sudo systemctl restart sofar-bot
sudo systemctl stop sofar-bot
journalctl -u sofar-bot -f
cd /home/ubuntu/so-far && bash deploy/update.sh
```

First-time install details: see [README.md](../README.md#deploy-on-a-vps-systemd-no-docker).

**Important:** only one Sofar bot process should poll Telegram. If the bot is running on the VPS, stop it on your Mac (and the other way around).

### Kaygram (optional / parked)

Older checkout may still exist at `/home/ubuntu/apps/kaygram`. Not required for Sofar. Do not run Kaygram and Sofar bots in a way that fights over the same machine resources without checking RAM first.

## Firewall notes

- Sofar bot: **no inbound ports**. Outbound HTTPS to Telegram + TMDB is enough.
- Cockpit: **9090** only if you open it in Oracle Security Lists / NSG.
- SSH: **22** should already be allowed (how you log in).

OS-level `ufw` may not be in use; Oracle’s cloud security list is the gate that usually blocks public ports.

## Backup (Sofar data)

From your Mac:

```bash
scp vps:/home/ubuntu/so-far/data/sofar.db ~/Desktop/sofar-backup-$(date +%F).db
```

To restore:

```bash
ssh vps 'sudo systemctl stop sofar-bot'
scp ~/path/to/sofar.db vps:/home/ubuntu/so-far/data/sofar.db
ssh vps 'sudo systemctl start sofar-bot'
```

## Quick checklist

| Task | Command / place |
|------|------------------|
| SSH in | `ssh vps` |
| Cockpit | `ssh -L 9090:localhost:9090 vps` then https://localhost:9090 |
| Sofar logs | `journalctl -u sofar-bot -f` |
| Update Sofar | `cd /home/ubuntu/so-far && bash deploy/update.sh` |
| Backup DB | `scp vps:/home/ubuntu/so-far/data/sofar.db .` |

## Safety

- Never commit `.env` or the SSH private key.
- Prefer Cockpit over SSH tunnel instead of opening 9090 to the whole internet.
- This VM is low on RAM - watch Cockpit’s memory panel before adding more services.
