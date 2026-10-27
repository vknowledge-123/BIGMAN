from pathlib import Path
import re, html
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, PageBreak, Preformatted, KeepTogether
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import fitz
pdfmetrics.registerFont(TTFont('GuideMono','C:/Windows/Fonts/consola.ttf'))

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'output/pdf/AshuChart_GCP_Deployment_Guide.pdf'
CONTENT = r'''
@page AshuChart deployment handbook
Beginner edition | Google Cloud | 27 October 2026

Deploy one independent trading application per VM, in your own project or a client's project. Add another app without changing an existing installation.

This handbook is based on your actual deployment scripts and the successful installations and recovery logs you shared. It includes the IAM roles, copyable commands, expected results and decision points needed to repeat the process.

### Release covered by this guide
```text
Repository: https://github.com/vknowledge-123/finalI.git
Commit: e9a8218b683481cb1806f9425638007c1e35bff0
Region: asia-south1 (Mumbai)
Zone: asia-south1-b
```
### What is implemented
Fresh installations, independent VM/IP per app, generated secrets, Redis, Nginx, six application services, administrator setup, option caching, deployment checks and manual backup creation.

### What is not implemented
Automatic upgrades across all clients, a general rollback tool, automatic off-VM backups, and the permanent fix for the interrupted-installer restart-order issue. The recovery procedure in this guide is for an unfinished installation, not an unattended production upgrade.

IMPORTANT: Commands are intended for the named environment. Read each step and its expected result before continuing. Do not paste terminal prompts or example output as commands.

This guide preserves your requested raw-IP HTTP access. HTTP browser traffic is not encrypted. SSH administration uses IAP; it does not add encryption to the public dashboard connection.

@page How to use this handbook
### Contents
02  How to use this handbook
03  Architecture, names and operating rules
04  Client project, billing and capacity
05  IAM roles and access setup
06  Open Cloud Shell and authenticate
07  Enter and check installation details
08  Fetch code and pin the release
09  Run installation and answer prompts
10  Verify deployment and dashboard setup
11  Another client or another app
12  Server files, services and secrets
13  Create and copy a backup
14  Missing account, billing and access errors
15  IAP, quotas and other failures
16  Cloud Shell disconnected: diagnose first
17  Recover an installer waiting for a password
18  Recover the Redis/worker restart sequence
19  Installation complete, cleanup failed
20  Operations and service troubleshooting
21  Future code updates across clients
22  Deployment record and handover checklist
23  References and evidence boundaries

### Follow the correct path
First deployment: read pages 3-10 in sequence, then create a backup using page 13.

Another installation: use page 11, then repeat the verification and backup steps.

An error: stop at the failing step and use pages 14-19. Do not repeatedly start installers, reset counters or delete resources without diagnosing the failure.

### Command notation
Cloud Shell is the browser terminal with @cloudshell in its prompt. Inside VM is the terminal after SSH, showing the VM name. Browser means the Google Cloud Console or application website.

A backslash at the end of a command line continues the command onto the next line. Copy the whole block and do not add spaces after the backslash. Do not copy the labels above command blocks. If copied text looks garbled, press Ctrl+C and paste one command at a time.

@page Architecture, names and operating rules
### The deployment model
One app label in one Google Cloud project identifies one installation. Each new installation has its own VM, static IP, Redis data, encryption key, webhook secret and dashboard account. This is separate installations, not a shared multi-tenant platform.

The automation reuses its matching VPC, subnet and firewall rules within a project. Separate projects have their own resources. All installations use the same code release unless deliberately deployed otherwise.

```text
Your PC -> GitHub release -> Cloud Shell deployment script
                                  |
                           IAP SSH / file copy
                                  |
Client project -> static IP -> VM -> Nginx -> application services
                                              |
                                         local Redis
```
### Three different identities
Project ID selects the Google Cloud project that owns the infrastructure and receives charges. An app label such as client1-app1 selects the installation. The dashboard admin email selects the application login account.

The Google account used by Cloud Shell is the deployment operator. It may differ from the dashboard admin email. IAM access does not create a dashboard account.

### Rules to keep
- Run one deployment at a time. Use a new label for another app in the same project.
- A retry uses exactly the same project, label, email, IP identity and Git release.
- Check hostname before changing services. Identical service names exist on every VM.
- Never copy one client's .env or Redis database into another client as deployment setup.
- Do not commit real passwords, API tokens, .env files or backup archives to Git.
- Keep generated encryption keys with their matching data backups.
- A passing installer checks infrastructure and app startup, not live broker correctness.
- Two apps using one broker account still share broker positions and account limits.

@page Client project, billing and capacity
### Before running commands
The client signs into Google Cloud Console and selects or creates their project. Record its Project ID; the display name "My First Project" is not sufficient to identify it.

To create one: open the project selector at the top > New Project, enter a project name, choose the permitted organization/location if requested, and click Create. Wait for creation and select that project. If creation is restricted, the client's authorized project administrator must do this. [S2]

In Billing, confirm that the project is linked to an active, open billing account. The billing administrator must resolve closed accounts, unpaid balances, payment verification or suspension notices. Your VM/IAP roles do not automatically grant billing administration. [S3]

If billing is not linked, use Link a billing account or the available billing-account selection action, select the client's intended active account, and confirm. If no eligible account is available, the client must finish billing-account setup or ask their billing administrator. [S3]

### Resources created per new app
- VM: e2-standard-2, 2 vCPUs and 8 GB RAM.
- OS: Ubuntu 24.04; Python 3.12 environment.
- Boot disk: 30 GB pd-balanced.
- One regional static external IP in asia-south1.
- VM zone: asia-south1-b.

Allow sufficient regional CPU, disk and external-IP quota for every additional app. Availability and organization policies can still block creation. Use the Console's Quotas & System Limits page to inspect the actual limit named by an error. Do not change machine type or region in this pinned installer without reviewing the code.

### Billing and resource lifetime
Each extra VM, disk and IP adds cost. This guide does not promise a fixed monthly price. Review current pricing and billing reports in the client's project. A budget alert is a notification, not an automatic spending cap.

The installer intentionally retains the boot disk when a VM is deleted. Retained disks and reserved addresses can continue to incur charges. This handbook does not provide bulk deletion commands; deletion is not a repair for an installation error.

### Project network policy
The script creates a custom network and subnet. It allows public TCP port 80 to tagged app VMs, and SSH port 22 from the IAP range 35.235.240.0/20. Redis and app ports 6379, 8005 and 8010 stay on VM loopback. No VM service account is attached by this installer.

If client organization policy prohibits public HTTP, external IPs or custom VPC creation, obtain an approved architecture adjustment before deploying. Do not weaken the policy to force this script through.

@page IAM roles and access setup
### The client administrator performs this step
In the correct client project: IAM & Admin > IAM > Grant access. Add your operator email, or edit its existing entry. For your previous deployments, the operator was charpe.amol193@gmail.com.

Assign the following predefined roles if equivalent permissions are not already present. These are the deployment script's operational needs, not a request for unrestricted Owner access.

```text
Compute Instance Admin (v1)
roles/compute.instanceAdmin.v1
  VM, disk and SSH metadata operations

Compute Network Admin
roles/compute.networkAdmin
  Network, subnet and static IP operations

Compute Security Admin
roles/compute.securityAdmin
  Firewall rules

Service Usage Admin
roles/serviceusage.serviceUsageAdmin
  Enable Compute and IAP APIs

IAP-secured Tunnel User
roles/iap.tunnelResourceAccessor
  SSH and file copy through IAP
```
Save the changes. "IAP-secured Tunnel Destination Group Editor" is a different role; select the exact Tunnel User role above. IAP access and VM login permissions are separate requirements. [S1, S2]

### If OS Login is enabled or enforced
The operator also needs Compute OS Admin Login (roles/compute.osAdminLogin) for SSH with sudo. An operator outside the client's organization may need Compute OS Login External User (roles/compute.osLoginExternalUser), granted at the organization level by its administrator. [S4]

If your account receives setIamPolicy access denied, ask the client administrator to grant the roles. Do not keep attempting to grant yourself permissions. Changes may take time to propagate.

@page Open Cloud Shell and authenticate
### Browser: open the correct terminal
Sign into Google Cloud Console with the operator account granted access. Click Activate Cloud Shell (>_). Approve the Cloud Shell authorization prompt if shown. You do not need to install gcloud on your Windows PC for this workflow.

### Cloud Shell: identify and select your account
```bash
gcloud auth list
```
Look for the ACTIVE marker. If your email is listed but not active, select it. The command below uses your existing operator account; use a different email only if that is the authorized operator.
```bash
gcloud config set account charpe.amol193@gmail.com
gcloud auth list --filter=status:ACTIVE --format='value(account)'
```
If no valid credentials are available, run the following and complete the Google sign-in flow. Do not share verification codes or tokens.
```bash
gcloud auth login
```
### List accessible projects
```bash
gcloud projects list
```
Check the exact Project ID against the client's record. Seeing a project in this list alone does not prove that billing or every deployment permission is configured.

### Terminal differences
```text
Cloud Shell:  user@cloudshell:~ (project-id)$
Inside VM:    user@ashuchart-client1-app1-vm:~$
Windows:      PS E:\finalI>
```
To leave an SSH session and return to Cloud Shell, type exit. Closing Cloud Shell does not delete a VM. Variables entered in one shell may be missing after a new session starts; re-enter them using page 7.

@page Enter and check installation details
### Cloud Shell: copy these commands exactly
Do not replace the variable names at the end of read commands with your answers. Run each command, then type its answer at the prompt.
```bash
read -r -p "Client project ID: " CLIENT_PROJECT
read -r -p "Unique app label: " CLIENT_LABEL
read -r -p "Dashboard admin email: " CLIENT_ADMIN_EMAIL
```
Example answers: the client's actual project ID, a label such as rahul-app1, and the person's desired dashboard login email. Never type a password into these email or label prompts.

The label must be 1-25 characters, lowercase letters/numbers/hyphens, start with a letter and end with a letter or number. It names resources; it does not change the AshuChart branding inside the dashboard.

### Review the selected values
```bash
printf 'Project: %s\nApp: %s\nAdmin: %s\n' \
  "$CLIENT_PROJECT" "$CLIENT_LABEL" "$CLIENT_ADMIN_EMAIL"
gcloud projects describe "$CLIENT_PROJECT" \
  --format='table(projectId,name)'
gcloud config set project "$CLIENT_PROJECT"
```
Expected: the intended client project and email. If any value is empty or wrong, repeat that read command before continuing. Every deployment command still specifies --project explicitly.

### Check for a naming collision
If Compute Engine is already enabled, list existing VMs:
```bash
gcloud compute instances list --project="$CLIENT_PROJECT" \
  --format='table(name,status)'
```
For a brand-new app, ashuchart-LABEL-vm must not already be an existing installation. If it exists, decide whether this is a retry or choose a genuinely unused label. Never use another app's label to create a second app.

On a new project, Compute may not yet be enabled. The installer enables it in page 9; complete billing and IAM first. An access-denied error is not proof that a VM is absent.

@page Fetch code and pin the release
### Cloud Shell: choose the applicable branch
If ~/finalI already exists:
```bash
cd ~/finalI
git remote get-url origin
git status --short
```
The remote should be your vknowledge-123/finalI repository. No output from status means clean. If modified/untracked files appear, preserve and review them before proceeding; do not reset or delete them blindly.

If the folder does not exist:
```bash
cd ~
git clone https://github.com/vknowledge-123/finalI.git
cd ~/finalI
```
If a private repository requires authentication, use the repository account's browser login, then retry the clone:
```bash
gh auth login --hostname github.com --git-protocol https --web
gh auth setup-git
```
### Select this handbook's exact release
```bash
git fetch origin
git switch --detach e9a8218b683481cb1806f9425638007c1e35bff0
git status --short
git rev-parse HEAD
python3 deploy/gcp/deploy_client.py --help
```
Expected: clean status, the exact hash above, and help listing --project, --client and --admin-email. Detached HEAD is intentional: it selects a fixed release. If the commit is unavailable, stop and inspect the remote/repository access; do not silently substitute another version.

No new commit or push is needed to reuse this published release. Future releases require review and testing. A new git pull is not part of retrying this pinned deployment.

The VM receives a Git archive over SSH. /opt/finalI on the VM is not a Git checkout. GitHub credentials remain in Cloud Shell.

@page Run installation and answer prompts
### Cloud Shell: deploy
Recheck the three variables on page 7 if you reopened the terminal. Run this from ~/finalI:
```bash
python3 deploy/gcp/deploy_client.py \
  --project="$CLIENT_PROJECT" \
  --client="$CLIENT_LABEL" \
  --admin-email="$CLIENT_ADMIN_EMAIL"
```
Review the printed project, label, VM, release and admin email. The script enables APIs, creates/reuses its matching infrastructure, waits for IAP SSH, uploads code, and installs packages, Redis, services and Nginx. No manual service-file or .env creation is needed.

### Complete the interactive password step
```text
Admin password (at least 12 characters):
Repeat password:
```
Type a new password, press Enter, type it again, and press Enter. Characters and asterisks are hidden. A blank-looking input is normal; do not assume installation is stuck. Mismatched or short passwords trigger another prompt.

The admin account is created on VM loopback before the installer exposes the dashboard through Nginx. The plaintext password is not written to the environment file.

### Understand normal messages
"Requirement already satisfied" means a package is already installed. "Warming the public Dhan option master" means downloading instrument definitions, not placing orders or retrieving live bid/ask prices. The NumPy warning concerns optional IAP upload performance.

### Completion evidence
```text
Services, Redis, Nginx, admin auth, webhook protection
and option cache: OK
Installation complete: http://NEW_IP/auth
Deployment verified on VM. Open http://NEW_IP/auth
```
The final wrapper message follows temporary-file cleanup. If installation completed but only cleanup failed, use page 19. Keep Cloud Shell open until done. If disconnected, use page 16 before starting another installer.

@page Verify deployment and dashboard setup
### Cloud Shell: retrieve the actual address
```bash
gcloud compute addresses describe "ashuchart-${CLIENT_LABEL}-ip" \
  --project="$CLIENT_PROJECT" --region=asia-south1 \
  --format='value(address)'
```
Open http://PRINTED_IP/auth in your browser. PRINTED_IP is an explanation, not text to type literally. Use the address printed by your own deployment, not an older client's IP.

### Connect for a final check
```bash
gcloud compute ssh "ashuchart-${CLIENT_LABEL}-vm" \
  --project="$CLIENT_PROJECT" --zone=asia-south1-b \
  --tunnel-through-iap
```
Inside VM:
```bash
hostname
sudo cat /etc/ashuchart-deployment.json
sudo systemctl is-active redis-server nginx \
  ashuchart-api ashuchart-alert ashuchart-execution \
  ashuchart-market-feed ashuchart-reconciliation ashuchart-turnover
sudo systemctl list-timers ashuchart-option-cache.timer \
  --all --no-pager
exit
```
Expected: correct VM identity, manifest status complete, eight active service results, and a scheduled cache timer. Cache refresh runs weekdays at 08:00 Asia/Kolkata, with Persistent=true for missed scheduling.

### Browser: finish setup
Sign in using your chosen email/password; complete Google Authenticator setup. Store recovery information privately. Configure broker credentials, alerts, quantity and risk settings. Use this app's generated webhook URL in Chartink. Check any broker-side IP/callback settings against this new installation.

Verify market-feed connectivity, webhook intake and paper-mode behavior before controlled live validation. Check the app's actual paper-mode behavior and broker requirements. Installer health checks do not prove a real order lifecycle. No old broker credentials, alerts or history are imported by a fresh installation.

@page Another client or another app
### Another client in their own project
Repeat billing and IAM setup in that client's project. In Cloud Shell, repeat page 7 with their Project ID, an unused label and their dashboard email. Reuse the same clean, pinned repository and deployment command from page 9. You do not reinstall tools in Cloud Shell or manually duplicate server configuration.

### Another app for the same client
Use the SAME project, but a NEW app label. Example below is for a future unused label, not an instruction to redeploy your existing app4:
```bash
CLIENT_PROJECT="project-07af7c42-10d0-4eb8-b3b"
read -r -p "New unused app label: " CLIENT_LABEL
read -r -p "New app dashboard email: " CLIENT_ADMIN_EMAIL
gcloud compute instances list --project="$CLIENT_PROJECT" \
  --format='table(name,status)'
```
Confirm the label is unused, then follow pages 8-10. Example label vikasahir-app5 produces ashuchart-vikasahir-app5-vm and ashuchart-vikasahir-app5-ip. The dashboard title stays AshuChart.

Each app has independent storage and secrets. The same dashboard email can be used on separate installations, but each has its own password/authenticator setup. A shared broker account is not isolated by VM separation; coordinate order ownership and reconciliation before simultaneous trading.

### Historical installation record - verify before use
In project project-07af7c42-10d0-4eb8-b3b, logs shared through 26 October 2026 showed:
```text
vikasahir       34.47.252.92    installation verified
vikasahir-app2  34.100.144.141  verified after recovery
vikasahir-app4  35.200.131.66   installed; cleanup auth error
```
No successful app3 deployment was shown. The ashtradeapk / ashutoshapp attempt stopped because its billing account was not open; no later success was supplied. These are historical observations, not a live inventory. List current resources before acting.

@page Server files, services and secrets
### Files created by the installer
```text
/opt/finalI/                         application code (root-owned)
/opt/finalI/myvenv/                  Python virtual environment
/etc/ashuchart.env                   secrets and settings; root:root 600
/etc/ashuchart-deployment.json       identity, release and install state
/etc/nginx/sites-available/ashuchart Nginx configuration
/etc/redis/redis.conf                Redis configuration
/etc/systemd/system/ashuchart-*.service
/etc/systemd/system/ashuchart-option-cache.timer
/usr/local/bin/restart-ashuchart.sh  restricted restart helper
/etc/sudoers.d/ashuchart-restart     exact helper authorization
/var/lib/ashuchart/dhan-options.json option-instrument definitions
/var/lib/redis/                      Redis persistent data
/var/backups/ashuchart/              locally created backup archives
```
Systemd reads /etc/ashuchart.env for the services. The unprivileged ashuchart user cannot directly read a root-owned mode-600 file; that alone is not an application fault. Do not loosen permissions to make diagnostic commands work.

### Service responsibilities
- ashuchart-api: dashboard/API on 127.0.0.1:8005.
- ashuchart-alert: alert intake on 127.0.0.1:8010.
- ashuchart-execution: consumes queued work and executes trading logic.
- ashuchart-market-feed: broker market-feed processing.
- ashuchart-reconciliation: broker/application state reconciliation.
- ashuchart-turnover: read-only turnover ranking.

Nginx sends the exact /webhook/chartink route to alert intake and other routes, including dashboard WebSockets, to the API. Redis requires authentication; AOF every second plus RDB is configured, with 2 GB maxmemory and noeviction. vm.overcommit_memory=1 is persisted.

Dhan option definitions and option trading are Dhan-specific in this release. Zerodha has core stock-trading integration but not equivalent advanced option execution. Installation does not mean all broker features are interchangeable.

@page Create and copy a backup
### After configuration, and before planned maintenance
Use page 10 to SSH into the intended VM. Confirm hostname. The backup includes secrets and the matching encryption key. Keep it private; do not attach it to chats or commit it to Git.

Inside VM:
```bash
sudo /opt/finalI/myvenv/bin/python \
  /opt/finalI/deploy/gcp/backup_vm.py
```
Only after success, copy the archive to your SSH user's home:
```bash
BACKUP_PATH="$(sudo python3 - <<'PY'
import json
with open('/var/backups/ashuchart/latest.json') as f:
    print(json.load(f)['file'])
PY
)"
sudo install -o "$(id -un)" -g "$(id -gn)" -m 600 \
  "$BACKUP_PATH" "$HOME/ashuchart-backup.tar.gz"
exit
```
Cloud Shell: ensure CLIENT_PROJECT and CLIENT_LABEL still name that VM. Re-enter them using page 7 if needed.
```bash
umask 077
mkdir -p ~/ashuchart-private-backups
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
BACKUP_LOCAL="$HOME/ashuchart-private-backups"
BACKUP_LOCAL="$BACKUP_LOCAL/${CLIENT_PROJECT}-${CLIENT_LABEL}-${STAMP}.tar.gz"
gcloud compute scp \
  "ashuchart-${CLIENT_LABEL}-vm:~/ashuchart-backup.tar.gz" \
  "$BACKUP_LOCAL" --project="$CLIENT_PROJECT" \
  --zone=asia-south1-b --tunnel-through-iap
ls -lh "$BACKUP_LOCAL"
```
This is an off-VM copy in Cloud Shell, not yet a file on your Windows PC. To download to your PC, use Cloud Shell's Download file action and supply the full path printed by the command. Store it in a protected backup location.

The snapshot represents one point in time. It does not capture subsequent broker activity. No automatic off-VM schedule is installed. Restore requires an explicit stopped-service, Redis-persistence and broker-reconciliation plan; do not drop an old RDB into a running AOF-enabled system.

@page Missing account, billing and access errors
### No active account selected
In Cloud Shell:
```bash
gcloud auth list
gcloud config set account charpe.amol193@gmail.com
gcloud auth list --filter=status:ACTIVE --format='value(account)'
```
Use the account that actually has client access. If credentials are absent/expired, run gcloud auth login and complete browser authorization. Recheck the target project before retrying. Do not share authorization codes.

If this happens after "Installation complete", use page 19. An account error during temporary cleanup does not undo completed VM installation.

### Billing account is not open
This is a billing blocker, not missing IAP permissions. Ask the client's billing administrator to inspect Billing, resolve payment/verification problems and reopen an eligible closed account or link the intended active account. [S3]
```bash
gcloud billing projects describe "$CLIENT_PROJECT"
```
Look for billingEnabled: true. If you cannot view billing, the administrator should verify it in Console. Do not grant yourself extra roles or substitute another person's billing account without authorization.

If failure occurred at gcloud.services.enable, this attempt had not reached VM creation. After billing is corrected, retry the same installation identity from the same release.

### Permission denied
Read the named permission/API and project. Confirm the active account first. setIamPolicy denied means the caller cannot change project IAM; ask the administrator. A resource-creation permission error should be mapped to page 5, rather than granting broad Owner access.

### Wrong or empty variable
Repeat the read prompts on page 7 and print the selected values. Error "not a valid identifier" means an answer was pasted where the variable name belongs. Do not put the Project ID at the end of the read command.

@page IAP, quotas and other failures
### IAP SSH authorization failure
Confirm the active operator has IAP-secured Tunnel User on the target resource/project. Check OS Login requirements if enabled. The matching firewall must permit IAP to reach TCP 22; do not open SSH to the whole internet. [S1, S4]

For an existing RUNNING VM, test from Cloud Shell:
```bash
gcloud compute ssh "ashuchart-${CLIENT_LABEL}-vm" \
  --project="$CLIENT_PROJECT" --zone=asia-south1-b \
  --tunnel-through-iap \
  --command='sudo -n true && echo SSH_AND_SUDO_OK'
```
Expected: SSH_AND_SUDO_OK. Failure of sudo is distinct from failure of the tunnel. Share the exact error, not just "SSH failed".

### HTTP 429: Service Usage mutate requests
The observed error was a per-minute API rate limit, not a limit of two/four apps. Wait two minutes without repeated retries, then retry once if no installer is active. Service Usage documents 120 mutate requests per minute as its default. [S5]

If it persists, inspect the quota-consumer project named by the error. In your observed failure that project number differed from the target project; do not assume which account owns it or blindly request quota increases on the target.

### VM quota, capacity or configuration conflict
Read the exact quota or resource named by the error. An existing-resource mismatch is an intentional protection: do not remove its labels, overwrite its environment or delete it to bypass the check. A release/identity mismatch requires review of the original deployment record.

### NumPy warning / package messages
The optional IAP NumPy warning is not an installation failure. "No broken requirements found" is a dependency check, not the final success message. A RUNNING VM does not prove its application is installed or healthy.

For unexpected failures, preserve the terminal output and service logs. Redact credentials before sharing. Do not manually mark the deployment complete.

@page Cloud Shell disconnected: diagnose first
Closing Cloud Shell does not delete the VM. The installer may still be running, waiting for a password, or stopped. Do not immediately rerun it.

### Cloud Shell: restore identity and inspect the VM
Use pages 6-7 to restore your account and original project/label/email. Then:
```bash
gcloud compute instances describe "ashuchart-${CLIENT_LABEL}-vm" \
  --project="$CLIENT_PROJECT" --zone=asia-south1-b \
  --format='table(name,status)'
```
If RUNNING, connect using page 10. If TERMINATED, review why it stopped before starting it. If absent or access is denied, investigate instead of assuming installation completed.

### Inside VM: collect evidence
```bash
hostname
sudo pgrep -af '[a]shuchart-install-|[a]pt-get|[d]pkg|[p]ip install'
sudo cat /etc/ashuchart-deployment.json
sudo systemctl is-active redis-server nginx \
  ashuchart-api ashuchart-alert ashuchart-execution \
  ashuchart-market-feed ashuchart-reconciliation ashuchart-turnover
curl --fail --silent --show-error --max-time 10 \
  http://127.0.0.1:8005/auth/state
```
### Choose the next action
- Active package/install work: allow it to finish; do not kill apt/dpkg or launch another installer.
- CREATE_ADMIN, services up, Nginx down, installer waiting on old terminal: inspect page 17.
- No installer, manifest preparing/installing: use the controlled incomplete-install recovery on page 18 if services were already started; otherwise investigate the actual stopping error.
- Manifest complete: verify services; handle only remaining cleanup using page 19.
- Missing manifest despite existing app files/secrets: stop for investigation. Do not regenerate keys.

The installer holds a local file lock to block simultaneous installs, but that is not a substitute for identifying the existing process.

@page Recover an installer waiting for a password
### Only use this for the confirmed waiting-password case
On your app2 incident, auth/state was CREATE_ADMIN, the services were up, Nginx was inactive, and the Python installer had been attached to an old terminal for 46 minutes. This matched its password prompt stage. CREATE_ADMIN alone does not prove a hung process.

Inside VM: inspect the current Python installer PID shown by pgrep on page 16. Do not reuse PID 1433 from historical logs. Enter the current PID and inspect it:
```bash
read -r -p "Current Python installer PID: " INSTALL_PID
sudo ps -p "$INSTALL_PID" \
  -o pid,ppid,tty,stat,etime,wchan:32,args
```
Confirm it is the ashuchart-install script for this exact app, not apt/dpkg or another application's process. sudo wrapper processes can surround a single Python installer; multiple lines do not necessarily mean multiple installs.

If the old terminal can be recovered, answer its password prompt there. Otherwise, after confirming it is only waiting for input and not doing package work, stop only that Python installer:
```bash
sudo kill -TERM "$INSTALL_PID"
sudo pgrep -af '[a]shuchart-install-'
```
Expected: no installer remains. If it still appears, inspect before doing anything further. Do not escalate to kill -9 as a routine step.

### Prepare a clean retry
Because services are already running on this unfinished installation, follow page 18 to stop them before resuming. A blind retry can restart Redis underneath the worker and repeat the restart-check failure.

Then exit to Cloud Shell, verify the same clean Git release, and rerun the same identity. Type the password when prompted even though the terminal shows no characters. It must be at least 12 characters and match the confirmation.

Never manually start Nginx to get past an unfinished administrator setup. Do not paste a password into process arguments, chat or the deployment command.

@page Recover the Redis/worker restart sequence
### Scope: an unfinished fresh installation only
Use this procedure after confirming no installer remains and that the app has not entered live trading. For an operational trading app with positions/orders, plan maintenance and reconciliation first; do not apply these stop commands blindly.

The observed sequence was Redis restarting while execution still ran, a lost Redis connection, then EXECUTION_WORKER_ALREADY_RUNNING_OR_RECOVERING until the 30-second lease expired. The installer subsequently rejected nonzero NRestarts. The permanent installer-order fix is not in this release.

### Inside VM: stop the app before Redis is restarted
```bash
hostname
sudo systemctl stop nginx ashuchart-api ashuchart-alert \
  ashuchart-execution ashuchart-market-feed \
  ashuchart-reconciliation ashuchart-turnover
sudo systemctl is-active nginx ashuchart-api ashuchart-alert \
  ashuchart-execution ashuchart-market-feed \
  ashuchart-reconciliation ashuchart-turnover
```
Confirm the correct hostname and seven inactive results. is-active returns a nonzero exit status for inactive units; this is expected here. If stopping fails or a unit remains active, investigate. Leave Redis running.
```bash
sleep 35
sudo systemctl reset-failed ashuchart-api ashuchart-alert \
  ashuchart-execution ashuchart-market-feed \
  ashuchart-reconciliation ashuchart-turnover
exit
```
The wait lets the lease expire naturally. reset-failed establishes a new restart-counter baseline; it is not itself a fix for a crash. It also does not erase the journal. Only reset after reviewing and addressing the cause. [S6]

### Cloud Shell: same-release retry
Restore the original variables (page 7); confirm the original release (page 8).
```bash
cd ~/finalI
python3 deploy/gcp/deploy_client.py \
  --project="$CLIENT_PROJECT" --client="$CLIENT_LABEL" \
  --admin-email="$CLIENT_ADMIN_EMAIL"
```
An already-created admin account skips password creation. Verify full success on page 10. If execution restarts again, collect its journal; do not repeatedly reset the counter to force a pass.

@page Installation complete, cleanup failed
### Recognize the app4 incident
The VM printed Installation complete and passed its checks. Then the Cloud Shell wrapper lost its active account when running an SSH command to remove the uploaded archive and installer. Application installation was complete; temporary cleanup was not.

Cloud Shell: restore your active account (page 6), original variables (page 7) and connect to the intended VM (page 10). Inside VM:
```bash
sudo cat /etc/ashuchart-deployment.json
sudo systemctl is-active redis-server nginx \
  ashuchart-api ashuchart-alert ashuchart-execution \
  ashuchart-market-feed ashuchart-reconciliation ashuchart-turnover
sudo pgrep -af '[a]shuchart-install-'
```
Proceed only if the manifest has the expected identity and status complete, services are healthy, and no installer is running. If it says installing, use pages 16-18 instead.

### Remove only the two known temporary files
These are in the SSH user's home, not /opt/finalI. This block is specifically for the release covered by this handbook:
```bash
RELEASE="e9a8218b683481cb1806f9425638007c1e35bff0"
rm -f -- "$HOME/ashuchart-${RELEASE}.tar.gz" \
  "$HOME/ashuchart-install-${RELEASE}.py"
exit
```
Do not use recursive deletion or remove application/state directories. No reinstall is required just to finish this cleanup.

### Final browser check
Open the app's own /auth URL. Complete authenticator setup if pending. In app4's supplied log the address was http://35.200.131.66/auth; retrieve the current reserved address instead of assuming historical addresses remain valid forever.

If the manifest is complete but a service is unhealthy, inspect its journal as on page 20. A manifest is a record of past installation checks, not proof of current broker or runtime health.

@page Operations and service troubleshooting
### Inside the intended VM: read-only checks
```bash
hostname
sudo systemctl show ashuchart-execution.service \
  -p ActiveState -p SubState -p NRestarts -p Result \
  -p ExecMainStatus -p ExecMainStartTimestamp
sudo journalctl -u ashuchart-execution.service \
  --since "1 hour ago" -n 150 --no-pager -o short-iso
sudo journalctl -u redis-server.service \
  --since "1 hour ago" -n 60 --no-pager -o short-iso
sudo nginx -t
curl --fail --silent --show-error --max-time 10 \
  http://127.0.0.1:8010/health
sysctl vm.overcommit_memory
df -h /
free -h
```
Replace the journal unit with the failing service as needed. Logs can contain sensitive information; redact before sharing. An active state is a snapshot. Compare restart count and start time later if investigating instability.

### Option-cache checks and manual refresh
```bash
sudo systemctl list-timers ashuchart-option-cache.timer \
  --all --no-pager
sudo journalctl -u ashuchart-option-cache.service -n 40 --no-pager
```
If a manual refresh is actually needed:
```bash
sudo systemctl start ashuchart-option-cache.service
sudo journalctl -u ashuchart-option-cache.service -n 40 --no-pager
```
Instrument cache is contract metadata, not live market depth. The timer refreshes it on weekdays; it is not a full daily application restart.

Service restart helper: /usr/local/bin/restart-ashuchart.sh queues all six app restarts asynchronously. Use it only during planned maintenance with trading state considered; check readiness afterward. This release can temporarily encounter an execution lease on restart. Never bypass that safety lock by deleting Redis keys.

@page Future code updates across clients
### Current behavior
Pushing to GitHub does not change deployed VMs. Each installation contains a fixed extracted release; /opt/finalI has no .git directory. The bootstrap intentionally refuses conflicting releases/identities on an existing installation.

Do not run git pull inside /opt/finalI. Do not delete a healthy client VM just to update code. Do not modify the deployment manifest to bypass its release check.

### The missing update workflow
A separate updater is not implemented in this release. It should use an inventory of project IDs, VM names, app labels and installed commits, then perform these steps:
- Test the proposed feature and existing behavior locally.
- Publish and select an exact release commit.
- Deploy to a test installation and validate broker/application behavior.
- Schedule production maintenance, accounting for open orders and positions.
- Back up each installation and its matching secrets.
- Pause intake, handle queued/in-flight work and stop services in dependency order.
- Install code, compatible dependencies and reviewed data migrations.
- Start services, verify recovery, and record the new installed release.
- Proceed one client at a time; stop the rollout on a failure.

### Preserve client identity
An ordinary upgrade should retain VM/IP, admin account, authenticator configuration, broker credentials, encryption keys, alerts and trading records. A migration may transform data but must not silently discard it.

Rollback must account for data migrations and broker activity. Restoring an old Redis backup can discard records of orders placed after that snapshot. Reverting code and restoring trading data are different operations.

No update_clients.py command is supplied here because it does not exist. The next engineering work is to implement and test this upgrade workflow and the installer retry-order fix. This guide documents deployment of the pinned release, not a promise that future releases are backward-compatible.

@page Deployment record and handover checklist
### Fill in for every installation
Keep this record without plaintext passwords or tokens. The client email, project ID and VM name are operational identifiers; the actual credentials belong in a protected credential store.

Client/person: ______________________________________________
Operator Google account: ____________________________________
Project ID: _________________________________________________
App label: __________________________________________________
VM name: ____________________________________________________
Zone: _______________________________________________________
Static IP reservation: _______________________________________
Dashboard URL: ______________________________________________
Dashboard admin email: ______________________________________
Full release commit: ________________________________________
Deployment date/time: _______________________________________
Backup location/date: _______________________________________
Credential storage reference: _______________________________

### Handover checks
- Correct client project, active billing and required operator access confirmed.
- Correct release and app identity recorded; no concurrent installer remains.
- Manifest complete, services active, no unexplained recurring restarts.
- Dashboard login and authenticator setup verified.
- Broker credentials configured for the intended account.
- Alert directions, quantities, risk settings and webhook URL reviewed.
- Feed, alert intake and controlled trading validation completed separately.
- Backup created and copied off the VM; restore requirements understood.
- Client understands raw-IP HTTP access and resource costs.
- Separate apps sharing a broker account have an agreed ownership/recovery plan.
- Recovery contact and maintenance procedure recorded.

This list is a completion record, not an instruction to activate live trading automatically. Record any unverified item explicitly rather than treating installation success as proof.

@page References and evidence boundaries
### Official references checked for this guide
[S1] Google Cloud: IAP TCP forwarding and SSH access requirements.
https://docs.cloud.google.com/iap/docs/using-tcp-forwarding

[S2] Google Cloud: enable/disable APIs and required permissions.
https://docs.cloud.google.com/service-usage/docs/enable-disable

[S3] Google Cloud: reopen billing and manage project billing.
https://docs.cloud.google.com/billing/docs/how-to/close-or-reopen-billing-account
https://docs.cloud.google.com/billing/docs/how-to/modify-project

[S4] Google Cloud: OS Login setup and roles.
https://docs.cloud.google.com/compute/docs/oslogin/set-up-oslogin

[S5] Google Cloud: Service Usage rate quotas.
https://docs.cloud.google.com/service-usage/docs/quotas

[S6] systemd: systemctl reset-failed and restart counters.
https://www.freedesktop.org/software/systemd/man/latest/systemctl.html

### Application sources
Repository: https://github.com/vknowledge-123/finalI.git
Reviewed deployment behavior: deploy/gcp/deploy_client.py, install_vm.py, backup_vm.py and docs/GCP_DEPLOYMENT.md. Worker lease behavior: app/execution_service.py and app/order_locks.py. Cache schedule: deploy/ashuchart-option-cache.timer.

The handbook combines those source files with the terminal logs and pasted deployment conversation you supplied. The disconnect recovery and cleanup sections reflect observed incidents, not hypothetical success reports.

### Limits and maintenance
No Google Cloud resources were created, modified or live-inspected while preparing this PDF. Historical IPs and installation status are based on supplied logs. Recheck current state before operating a VM.

The IAM and Console interface may change after the publication date. The command examples target the pinned application release; review the guide when code, dependency versions, cloud policies or broker behavior change. The remaining installer and update-tool limitations are described on pages 18 and 21.
'''

styles = {
 'toc': ParagraphStyle('toc',fontName='Helvetica',fontSize=10,leading=14,spaceAfter=2,textColor=colors.HexColor('#243746')),
 'title': ParagraphStyle('title',fontName='Helvetica-Bold',fontSize=25,leading=29,textColor=colors.HexColor('#12334A'),spaceAfter=16),
 'h': ParagraphStyle('h',fontName='Helvetica-Bold',fontSize=12,leading=15,textColor=colors.HexColor('#087F8C'),spaceBefore=10,spaceAfter=6,keepWithNext=True),
 'body': ParagraphStyle('body',fontName='Helvetica',fontSize=10,leading=14,spaceAfter=8,textColor=colors.HexColor('#243746')),
 'bullet': ParagraphStyle('bullet',fontName='Helvetica',fontSize=10,leading=14,leftIndent=12,firstLineIndent=-10,spaceAfter=5,textColor=colors.HexColor('#243746')),
}
def para(t,style='body'):
    esc=html.escape(t)
    if t.startswith('https://'):
        esc=f'<link href="{html.escape(t,quote=True)}" color="#087F8C">{esc}</link>'
    return Paragraph(esc, styles[style])

pages=[]
for part in CONTENT.split('@page ')[1:]:
    title,body=part.split('\n',1)
    pages.append((title,body))

story=[]
for idx,(title,body) in enumerate(pages,1):
    if idx>1: story.append(PageBreak())
    story.append(para(title,'title'))
    chunks=re.split(r'(```[^\n]*\n.*?\n```)',body,flags=re.S)
    for chunk in chunks:
        if chunk.startswith('```'):
            code=chunk.split('\n',1)[1].rsplit('\n```',1)[0]
            maxwidth=max(stringWidth(line,'GuideMono',9) for line in code.splitlines())
            fs=min(9,9*463/maxwidth) if maxwidth else 9
            if fs<7: raise ValueError('Code too wide: '+code)
            st=ParagraphStyle('code',fontName='GuideMono',fontSize=fs,leading=fs+3,
                leftIndent=9,rightIndent=9,spaceBefore=5,spaceAfter=10,
                backColor=colors.HexColor('#EEF4F7'),borderPadding=8,
                textColor=colors.HexColor('#102A43'))
            story.append(KeepTogether([Preformatted(code,st)]))
        else:
            for block in re.split(r'\n\s*\n',chunk.strip()):
                if not block: continue
                lines=block.splitlines()
                for line in lines:
                    if line.startswith('### '):story.append(para(line[4:],'h'))
                    elif line.startswith('- '):story.append(para('- '+line[2:],'bullet'))
                    elif re.match(r'^\d\d  ',line):story.append(para(line,'toc'))
                    elif len(lines)>1:story.append(para(line))
                    else:story.append(para(block))

def frame(c,doc):
    w,h=A4
    c.setStrokeColor(colors.HexColor('#D6E2E8'));c.line(48,47,w-48,47)
    c.setFont('Helvetica',8);c.setFillColor(colors.HexColor('#577080'))
    c.drawString(48,32,'ASHUCHART  /  GCP OPERATIONS  /  27 OCT 2026')
    c.drawRightString(w-48,32,f'{doc.page:02d}')
    if doc.page>1:
        c.setFont('Helvetica-Bold',8);c.drawString(48,h-28,'DEPLOYMENT HANDBOOK  |  RELEASE e9a8218')

doc=SimpleDocTemplate(str(OUT),pagesize=A4,leftMargin=48,rightMargin=48,
    topMargin=48,bottomMargin=62,title='AshuChart Google Cloud Deployment Handbook',
    author='AshuChart operations guide',subject='Beginner deployment, IAM, recovery and backup guide')
doc.build(story,onFirstPage=frame,onLaterPages=frame)
pdf=fitz.open(OUT)
pdf.set_toc([[1,title,i] for i,(title,_) in enumerate(pages,1)])
pdf.saveIncr()
print('Pages:',len(pdf),'Expected:',len(pages))
assert len(pdf)==len(pages), 'Unexpected overflow: adjust layout'
for i,p in enumerate(pdf):
    txt=p.get_text()
    assert pages[i][0] in ' '.join(txt.split()), (i,txt[:100])
    for block in p.get_text('dict')['blocks']:
        for line in block.get('lines',[]):
            for span in line.get('spans',[]):
                x0,y0,x1,y1=span['bbox']
                assert x0>=35 and x1<=A4[0]-35 and y0>=10 and y1<=A4[1]-20,(i,span)
    p.get_pixmap(matrix=fitz.Matrix(1.2,1.2)).save(ROOT/f'tmp/pdfs/page-{i+1:02}.png')
print('Saved:',OUT)
