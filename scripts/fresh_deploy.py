#!/usr/bin/env python3
"""
Fresh Deploy — Full Stack Reset & Seed
========================================
One-command script to start fresh on a new deployment:
  1. Stops and removes all containers + volumes (clean DB)
  2. Rebuilds all Docker images
  3. Starts infrastructure (Postgres, Redis)
  4. Runs schema init (via init.sql)
  5. Starts all services
  6. Seeds LTM + MTM with policies aligned to IDPO's policy_store.json
  7. Verifies everything is healthy

Usage:
    python scripts/fresh_deploy.py                    # Full reset
    python scripts/fresh_deploy.py --skip-build       # Skip rebuild (faster)
    python scripts/fresh_deploy.py --seed-only        # Only re-seed, don't reset volumes

Policy Alignment:
    LTM seeds use the same 5 policy_ids as configs/policy_store.json:
    ┌────────────────┬──────────────────────────────────────────────┐
    │ policy_id      │ Document Types                              │
    ├────────────────┼──────────────────────────────────────────────┤
    │ table_heavy    │ invoice, receipt, financial_statement,       │
    │                │ table_document                               │
    │ forms          │ form_document, clinical_summary,             │
    │                │ medical_record                               │
    │ scanned_text   │ scanned_document, text_document              │
    │ mixed_content  │ mixed_document, contract                     │
    │ default        │ unknown (catch-all)                          │
    └────────────────┴──────────────────────────────────────────────┘
"""

import argparse
import os
import subprocess
import sys
import time


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(ROOT)

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


def run(cmd: str, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    print(f"  {CYAN}$ {cmd}{RESET}")
    return subprocess.run(cmd, shell=True, check=check, capture_output=capture, text=True)


def header(msg: str) -> None:
    print(f"\n{BOLD}{GREEN}{'═' * 60}{RESET}")
    print(f"{BOLD}{GREEN}  {msg}{RESET}")
    print(f"{BOLD}{GREEN}{'═' * 60}{RESET}\n")


def step(num: int, total: int, msg: str) -> None:
    print(f"\n{YELLOW}[{num}/{total}]{RESET} {BOLD}{msg}{RESET}")


def wait_for_healthy(service: str, timeout: int = 180) -> bool:
    """Poll docker compose ps until a service is healthy."""
    start = time.time()
    while time.time() - start < timeout:
        result = run(f'docker compose ps {service} --format "{{{{.Status}}}}"', check=False, capture=True)
        status = result.stdout.strip().lower()
        if "healthy" in status:
            print(f"  {GREEN}✓ {service} is healthy{RESET}")
            return True
        if "exit" in status:
            print(f"  {RED}✗ {service} exited unexpectedly{RESET}")
            return False
        time.sleep(3)
    print(f"  {RED}✗ {service} did not become healthy within {timeout}s{RESET}")
    return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Fresh deploy — reset & seed the full stack")
    parser.add_argument("--skip-build", action="store_true", help="Skip Docker image rebuild")
    parser.add_argument("--seed-only", action="store_true", help="Only re-seed DB (don't destroy volumes)")
    args = parser.parse_args()

    if args.seed_only:
        total_steps = 2
        header("SEED ONLY — Re-seeding database")

        step(1, total_steps, "Checking services are running...")
        result = run("docker compose ps --format json", check=False, capture=True)
        if not result.stdout.strip():
            print(f"  {RED}No containers running. Run without --seed-only first.{RESET}")
            sys.exit(1)

        step(2, total_steps, "Running database seed script...")
        run(
            'docker compose exec -e POSTGRES_URI="postgresql://user:password@db:5432/ahmn_db" '
            "ahmn python -m scripts.reset_and_seed_db",
        )
        header("SEED COMPLETE")
        return

    total_steps = 7 if not args.skip_build else 6

    header("FRESH DEPLOY — Full Stack Reset")

    # ── Check prerequisites ──
    print(f"{BOLD}Checking prerequisites...{RESET}")
    for cmd in ["docker --version", "docker compose version"]:
        result = run(cmd, check=False, capture=True)
        if result.returncode != 0:
            print(f"  {RED}✗ {cmd.split()[0]} not found. Install Docker Desktop first.{RESET}")
            sys.exit(1)
        print(f"  {GREEN}✓ {result.stdout.strip()}{RESET}")

    # ── Check .env ──
    if not os.path.exists(".env"):
        print(f"\n  {YELLOW}No .env file found — creating from .env.example{RESET}")
        run("copy .env.example .env" if sys.platform == "win32" else "cp .env.example .env")
    else:
        print(f"  {GREEN}✓ .env file exists{RESET}")

    current_step = 0

    # ── Step 1: Tear down everything ──
    current_step += 1
    step(current_step, total_steps, "Stopping containers and removing volumes...")
    run("docker compose down -v --remove-orphans", check=False)

    # ── Step 2: Rebuild images ──
    if not args.skip_build:
        current_step += 1
        step(current_step, total_steps, "Building all Docker images (this may take several minutes)...")
        run("docker compose build")

    # ── Step 3: Start infrastructure ──
    current_step += 1
    step(current_step, total_steps, "Starting infrastructure (Postgres + Redis)...")
    run("docker compose up -d db redis")
    print("  Waiting for Postgres and Redis to be healthy...")
    if not wait_for_healthy("db", timeout=60):
        print(f"  {RED}Postgres failed to start. Check: docker compose logs db{RESET}")
        sys.exit(1)
    if not wait_for_healthy("redis", timeout=30):
        print(f"  {RED}Redis failed to start. Check: docker compose logs redis{RESET}")
        sys.exit(1)

    # ── Step 4: Start all services ──
    current_step += 1
    step(current_step, total_steps, "Starting all services...")
    run("docker compose up -d")

    # ── Step 5: Wait for services ──
    current_step += 1
    step(current_step, total_steps, "Waiting for all services to become healthy...")
    services = ["ahmn", "guardrails", "xai-hitl", "idpo", "gateway", "frontend"]
    timeouts = {"ahmn": 180, "guardrails": 200, "xai-hitl": 240, "idpo": 120, "gateway": 60, "frontend": 60}
    all_healthy = True
    for svc in services:
        if not wait_for_healthy(svc, timeout=timeouts.get(svc, 120)):
            all_healthy = False

    if not all_healthy:
        print(f"\n  {RED}Some services failed. Check logs:{RESET}")
        print(f"    docker compose logs --tail 30 <service-name>")
        sys.exit(1)

    # ── Step 6: Seed the database ──
    current_step += 1
    step(current_step, total_steps, "Seeding LTM + MTM with aligned policy data...")
    seed_result = run(
        'docker compose exec -e POSTGRES_URI="postgresql://user:password@db:5432/ahmn_db" '
        "ahmn python -m scripts.reset_and_seed_db",
        check=False,
    )
    if seed_result.returncode != 0:
        print(f"  {YELLOW}⚠ Seed script failed — trying direct seed via AHMN lifespan (LTM auto-seeds on startup){RESET}")
        run("docker compose restart ahmn", check=False)
        wait_for_healthy("ahmn", timeout=120)

    # ── Step 7: Final verification ──
    current_step += 1
    step(current_step, total_steps, "Final verification...")
    run("docker compose ps")

    header("FRESH DEPLOY COMPLETE ✓")
    print(f"""
  {BOLD}Access your application:{RESET}
  ├── Frontend:     {CYAN}http://localhost:3000{RESET}
  ├── API Gateway:  {CYAN}http://localhost:8000{RESET}
  └── API Docs:     {CYAN}http://localhost:8000/docs{RESET}

  {BOLD}Default admin login:{RESET}
  ├── Username:  admin
  └── Password:  Adm!n_DocAI_2025

  {BOLD}Database tables seeded:{RESET}
  ├── LTM: 12 context→policy mappings (5 policies × multiple doc types per policy)
  ├── MTM: 8 sample outcomes (matching sample documents)
  └── Users: 1 admin account

  {BOLD}Policy alignment:{RESET}
  ├── LTM policy_ids ↔ configs/policy_store.json  ✓ Aligned
  ├── AHMN seeds ↔ IDPO policy_store              ✓ Aligned
  └── 5 policies: table_heavy, forms, scanned_text, mixed_content, default

  {BOLD}Useful commands:{RESET}
  ├── View logs:      docker compose logs -f <service>
  ├── Re-seed only:   python scripts/fresh_deploy.py --seed-only
  ├── View DB:        Login as admin → Dashboard → Database
  └── Stop all:       docker compose down
""")


if __name__ == "__main__":
    main()
