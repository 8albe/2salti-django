#!/bin/bash

# ==============================================================================
# OFFICIAL SAFE DEPLOY SCRIPT - 2SALTI (FINAL)
# ==============================================================================
# Source: /home/alberto (Git Repo)
# Target: /opt/2salti/backend (Production Runtime)
#
# PROTECTION SUMMARY:
# - db.sqlite3 is PRESERVED and NOT overwritten.
# - media/ is PRESERVED and NOT overwritten.
# - .env is PRESERVED and NOT overwritten.
# - Note: These runtime assets are NOT included in the code-layer backups.
# ==============================================================================

set -euo pipefail

# --- CONFIGURATION ---
SOURCE_DIR="/home/alberto"
TARGET_DIR="/opt/2salti/backend"
BACKUP_BASE_DIR="/home/alberto/backups/deploy_backups"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_PATH="${BACKUP_BASE_DIR}/backup_${TIMESTAMP}"

# Targeted application directories to sync
SYNC_APPS=("matches" "core" "accounts" "management" "templates")

# Exclude patterns for rsync (Critical for protecting data)
RSYNC_EXCLUDES=(
    "--exclude=__pycache__/"
    "--exclude=*.pyc"
    "--exclude=.git/"
    "--exclude=.venv/"
    "--exclude=db.sqlite3"
    "--exclude=media/"
    "--exclude=.env"
    "--exclude=staticfiles/"
    "--exclude=scripts/"
)

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# --- OPTIONS ---
DRY_RUN=false
SKIP_TESTS=false

usage() {
    echo "Usage: $0 [options]"
    echo "Options:"
    echo "  --dry-run      Show what would be done without making changes"
    echo "  --skip-tests   Skip the production test suite"
    echo "  --help         Show this help message"
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --dry-run) DRY_RUN=true; shift ;;
        --skip-tests) SKIP_TESTS=true; shift ;;
        --help) usage; exit 0 ;;
        *) echo "Unknown option: $1"; usage; exit 1 ;;
    esac
done

log() { echo -e "${BLUE}[INFO]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }
success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }

# --- PRE-CHECKS ---
log "Starting pre-deployment checks..."

if [[ ! -d "$SOURCE_DIR" ]]; then error "Source directory $SOURCE_DIR not found."; fi
if [[ ! -d "$TARGET_DIR" ]]; then error "Target directory $TARGET_DIR not found."; fi
if [[ "$SOURCE_DIR" == "$TARGET_DIR" ]]; then error "Source and target directories cannot be the same."; fi

# Verify target is a Django project
if [[ ! -f "${TARGET_DIR}/manage.py" ]]; then
    error "Target $TARGET_DIR does not appear to be a Django project (manage.py missing)."
fi

# Mandatory Sudo Check (Passwordless sudo required for automation)
log "Verifying sudo permissions for systemctl..."
if ! sudo -n systemctl is-active 2salti.service >/dev/null 2>&1; then
    error "Passwordless sudo is not available for 'systemctl is-active 2salti.service'. Automation aborted."
fi

success "Pre-checks passed."

# --- PRE-DEPLOY SAFETY ---
if [ "$DRY_RUN" = false ]; then
    # Automatic safety copy of ai_services.py if it exists
    AI_SERVICES_PATH="${TARGET_DIR}/matches/ai_services.py"
    if [[ -f "$AI_SERVICES_PATH" ]]; then
        log "Backing up opt-only ai_services.py..."
        cp "$AI_SERVICES_PATH" "${AI_SERVICES_PATH}.pre_sync_backup"
        success "ai_services.py backed up to .pre_sync_backup"
    fi
fi

# --- BACKUP (CODE LAYER ONLY) ---
log "Creating pre-deployment directory backup of code-level files..."
mkdir -p "$BACKUP_BASE_DIR"

if [ "$DRY_RUN" = true ]; then
    log "[DRY-RUN] Would create directory backup at $BACKUP_PATH"
else
    # Create directory backup with rsync
    # Note: We explicitly EXCLUDE media, db, and .env from the code backup
    rsync -a "${RSYNC_EXCLUDES[@]}" "$TARGET_DIR/" "$BACKUP_PATH/"
    success "Code backup created at $BACKUP_PATH"
fi

# --- SYNC CODE ---
log "Synchronizing application code surgical-style..."

for app in "${SYNC_APPS[@]}"; do
    SRC_APP_DIR="${SOURCE_DIR}/${app}/"
    TGT_APP_DIR="${TARGET_DIR}/${app}/"

    # Verify source directory exists before sync
    if [[ ! -d "$SRC_APP_DIR" ]]; then
        error "Source app directory $SRC_APP_DIR missing! Aborting to prevent partial sync."
    fi

    if [ "$DRY_RUN" = true ]; then
        log "[DRY-RUN] Would sync $app via rsync"
        rsync -avn --exclude='__pycache__/' "$SRC_APP_DIR" "$TGT_APP_DIR"
    else
        log "Syncing ${app}..."
        rsync -av --exclude='__pycache__/' "$SRC_APP_DIR" "$TGT_APP_DIR"
    fi
done

success "Code synchronization complete."

if [ "$DRY_RUN" = true ]; then
    log "[DRY-RUN] Dry run complete. Skipping migrations, checks, and restart."
    exit 0
fi

# --- MIGRATIONS ---
log "Running database migrations on production target..."
cd "$TARGET_DIR"
source .venv/bin/activate
python manage.py migrate
success "Migrations applied."

# --- DJANGO CHECK ---
log "Running Django system check..."
python manage.py check
success "System check passed."

# --- TESTS ---
if [ "$SKIP_TESTS" = true ]; then
    warn "Skipping regression tests as requested."
else
    log "Running focused production regression suite..."
    TEST_TARGETS=(
        "matches.tests_api"
        "matches.tests_public_read"
        "matches.tests_publishing"
        "matches.tests_stats_integrity"
    )
    if python manage.py test "${TEST_TARGETS[@]}"; then
        success "Tests passed."
    else
        error "Regression tests failed! Deployment halted before restart."
    fi
fi

# --- SERVICE RESTART & HEALTH CHECK ---
log "Restarting 2salti service..."
if sudo systemctl restart 2salti.service; then
    log "Verifying service health..."
    # Micro-fix: consistent sudo for health checks
    if sudo systemctl is-active --quiet 2salti.service; then
        success "Service healthy and active."
    else
        warn "Service is not active. Dumping recent logs:"
        sudo journalctl -u 2salti.service -n 50 --no-pager
        error "Service health check failed!"
    fi
else
    error "Failed to restart 2salti.service."
fi

# --- FINAL REPORT ---
echo -e "\n${BLUE}==============================================================================${NC}"
echo -e "${GREEN}DEPLOYMENT COMPLETE${NC}"
echo -e "Timestamp: $TIMESTAMP"
echo -e "Backup:    $BACKUP_PATH"
echo -e "Target:    $TARGET_DIR"
echo -e "Status:    ${GREEN}SUCCESS${NC}"
echo -e "------------------------------------------------------------------------------"
echo -e "${YELLOW}RUNTIME ASSETS PRESERVATION RECORD:${NC}"
echo -e "- db.sqlite3: [PRESERVED] (Excluded from sync & backup)"
echo -e "- media/:      [PRESERVED] (Excluded from sync & backup)"
echo -e "- .env:        [PRESERVED] (Excluded from sync & backup)"
echo -e "${BLUE}==============================================================================${NC}\n"
