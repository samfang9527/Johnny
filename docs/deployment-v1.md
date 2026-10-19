# Production deployment v1

This runbook describes the current production architecture. A future architecture change will be documented as deployment v2. GitHub Actions builds release artifacts after validation, and an operator starts each deployment through **Deploy production v1**.

## Setup

Run `bash scripts/setup-production.sh` from the repository root. It guides the operator through AWS account and domain details, creates Terraform state storage, shows the infrastructure plan, stores the required secrets in Parameter Store, sets GitHub Actions variables, and gives the Google OAuth callback to authorize. The script is intentionally interactive and has not been run by CI.

The Parameter Store paths are `/johnny/production/database-password`, `/johnny/production/openai-api-key`, `/johnny/production/google-oauth-client-secret`, `/johnny/production/garmin-credential-master-key`, and `/johnny/production/admin-token`. The EC2 role alone retrieves them during startup and deployment. `/etc/johnny/production.env` contains public settings created by instance bootstrap. The loader writes per-service runtime files to `/run/johnny` with root-only access. Docker still exposes container environment variables to host administrators; restrict root and Docker access accordingly.

The first Terraform apply launches a `t4g.small` EC2 instance in Tokyo and mounts the retained EBS data volume. Nginx runs on the host and proxies HTTPS requests to the API container. CPU credits use standard mode to cap compute charges; sustained high CPU can reduce throughput. The instance has a 1 GiB swap file to absorb short memory spikes; check memory and swap usage after launch and increase the instance size if the worker causes sustained swapping or out-of-memory restarts. If instance bootstrap fails, inspect `/var/log/cloud-init-output.log` through SSM before deploying. Confirm that `mountpoint /srv/johnny/data`, `docker compose version`, and `systemctl status amazon-ssm-agent` succeed. Do not start PostgreSQL if the data volume is not mounted.

## Release

Pull requests run backend and frontend checks, a disposable PostgreSQL migration, and a frontend build. Passing pushes to `main` build an ARM64 backend image, upload the frontend and deployment bundle under `production/v1/<sha>/` in the private release bucket, and publish a manifest containing the commit SHA and immutable image digest. The build job is enabled once the wizard sets the GitHub variables.

Run **Deploy production v1** in GitHub Actions with the full SHA of a completed release. The workflow verifies that the commit belongs to `main`, then sends one SSM command. The EC2 script fetches secrets, pulls the image, obtains the API TLS certificate if needed, places the API in maintenance mode, stops the scheduler and worker, uploads a database backup, runs Alembic, starts the services, and checks `/ready`. PostgreSQL stays on its EBS volume. After SSM reports success, the workflow uploads frontend assets first, publishes `index.html` last, and invalidates CloudFront. Old hashed assets remain for already open browser tabs.

`/ready` checks PostgreSQL access and the tables required by the running image. The deployment script separately checks that Alembic reached the new image's migration head. `GET /health` remains a simple process check. A backend or secret-only release does not require a frontend publish, though the current workflow publishes the matching frontend artifact for each release.

## Backups and rollback

The instance runs a `pg_dump -Fc` backup to the private S3 backup bucket every six hours and immediately before a migration. The backup bucket lifecycle removes backups after 14 days. Check the timer with `systemctl list-timers johnny-backup.timer` and verify recent backup objects in S3. Rehearse restoring a backup to a separate disposable PostgreSQL instance before launch; the deployment script does not automatically restore a database.

The release bucket holds each release manifest, frontend build, and EC2 deployment scripts for 90 days; ECR holds the backend image and keeps the latest 100 images. This gives a manual deployment or rollback a complete, commit-specific artifact set. A rollback SHA must still have both its release artifact and image digest. Existing hashed frontend assets remain available to open browser tabs.

S3 object versioning is disabled for the frontend, release, backup, and Terraform state buckets. Backups expire after 14 days. Keep access to the state bucket restricted: without object versions, deleting or overwriting its state cannot be undone from S3 history.

To roll back the application, run **Deploy production v1** with a prior validated SHA and select `rollback`. This restores its backend image and frontend assets without running older migrations. Use it only if the prior code supports the current database schema; migrations should remain additive across one release boundary. A failed migration or readiness check leaves the API in maintenance mode for inspection. Do not automatically downgrade Alembic or restore a backup, because either operation can discard user data.

Changing the PostgreSQL password requires coordinating the database role password with Parameter Store and a service restart. Replacing the Garmin encryption key without migrating stored credentials can make them unreadable. Rotate those two secrets using a separate migration procedure.

If EC2 is replaced, the protected data volume remains, but the new root volume needs a fresh deployment. Update the `EC2_INSTANCE_ID` GitHub variable from Terraform output, verify the data volume mount, and deploy the latest validated SHA. The wizard's state bucket and backup bucket are retained independently of EC2.
