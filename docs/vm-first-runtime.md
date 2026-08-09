# Louis OS VM-first runtime

## Target architecture

GitHub is source control and an occasional deployment source only. Runtime availability must not depend on GitHub Actions.

Production runtime on `louis-os-worker-01`:

- `louis-os-worker`: continuous monetization/autonomy loop and Firestore command bus.
- `louis-os-browser-monitor`: persistent Chromium/Playwright health loop with browser profile and evidence stored under `/var/lib/louis-os/results`.
- `louis-os-crypto-monitor`: receive-only public crypto revenue monitor.
- `louis-os-vm-first.service`: systemd supervisor that recreates any stopped runtime container and survives VM reboot.
- Firestore: command/control plane and live state (`louis_live/current`, `louis_runtime/current`, `louis_browser/current`, `louis_vm_commands/*`).

## Runtime independence

Once installed, all of the following run on the VM without GitHub Actions:

1. Autonomous monetization cycles.
2. Browser snapshots and browser health checks.
3. Processing queued Firestore commands.
4. Persistent browser profile/evidence storage.
5. Crypto receive monitoring.
6. Container self-healing and reboot recovery.
7. Live state publishing to Firestore.

GitHub Actions is not part of the runtime critical path.

## One-time cutover

The currently deployed production image predates the persistent browser executor. One successful bootstrap deployment is required to install a current image and the VM-first systemd supervisor.

After the current repository is present at `/opt/louis-os` on the VM and the current image is available, run:

```bash
sudo GOOGLE_CLOUD_PROJECT=test-bot-499814 \
  LOUIS_IMAGE="$(curl -fsS -H 'Metadata-Flavor: Google' \
  'http://metadata.google.internal/computeMetadata/v1/instance/attributes/louis-os-image')" \
  bash /opt/louis-os/scripts/install_vm_first_supervisor.sh
```

Then verify:

```bash
systemctl is-active louis-os-vm-first.service
docker ps --format '{{.Names}} {{.Status}}' | grep '^louis-os-'
cat /var/lib/louis-os/results/browser_runtime.json
```

Expected containers:

- `louis-os-worker`
- `louis-os-browser-monitor`
- `louis-os-crypto-monitor`

Expected browser state is also published to Firestore document `louis_browser/current`.

## Browser safety

The current browser executor is deliberately read-only. It allows only explicitly allow-listed HTTPS hosts and exposes snapshot/current-page operations. It does not expose wallet signing, trading, payment, uploads, arbitrary JavaScript, or unrestricted form submission.

## Deployment policy after cutover

Normal runtime operations must use Firestore and the VM. GitHub Actions should be reserved for occasional immutable image builds/deployments. A GitHub Actions billing or quota outage must not stop Louis OS from working on already-deployed capabilities.
