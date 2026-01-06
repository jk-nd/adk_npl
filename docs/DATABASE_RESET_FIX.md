# Database Reset Fix: Anonymous Volume Issue

## The Problem

When running `./start_demo.sh --clean`, the NPL engine database was **not being reset**. Old protocols (PurchaseOrders, Offers, etc.) persisted across restarts, causing:
- Approval cards from previous sessions appearing in the UI
- Agents referencing stale protocols
- Inability to test with a truly clean slate

## Root Cause

The `engine-db` service in `docker-compose.yml` was using an **anonymous Docker volume** instead of a named volume:

```yaml
# BEFORE (broken)
engine-db:
  volumes:
    - ./db_init/db_init.sh:/docker-entrypoint-initdb.d/db_init.sh
    # ❌ No named volume for /var/lib/postgresql/data
    # Docker creates anonymous volume with random hex name
```

**Impact:**
- Docker assigned a random volume name like `88c58bcd2d67093e29952d853a0c0fb449f6e92f818fbfee2c8061b4219abcdc`
- The `start_demo.sh --clean` script tried to remove `adk-demo_engine-db` (which didn't exist)
- Database data persisted because the wrong volume was targeted

## The Fix

### 1. Added Named Volume Declaration

**File: `docker-compose.yml`**

```yaml
# Define named volumes at the top level
volumes:
  engine-db: { }      # ✅ NEW: Named volume for engine database
  keycloak-db: { }
  keycloak-provisioning: { }
```

### 2. Mounted Named Volume in Service

**File: `docker-compose.yml`**

```yaml
engine-db:
  volumes:
    - engine-db:/var/lib/postgresql/data  # ✅ NEW: Use named volume
    - ./db_init/db_init.sh:/docker-entrypoint-initdb.d/db_init.sh
```

### 3. Updated Cleanup Scripts

**File: `start_demo.sh`**

```bash
# Stop both engine and database
docker-compose stop engine engine-db

# Remove the named volume (now works correctly!)
docker volume rm -f adk-demo_engine-db

# Restart with fresh volume
docker-compose up -d engine-db
sleep 5
docker-compose up -d engine
```

**File: `scripts/setup-fresh.sh`**

```bash
# Include engine-db in full cleanup
docker volume rm -f adk-demo_engine-db adk-demo_keycloak-db adk-demo_keycloak-provisioning
```

## Verification

After the fix, the named volume appears in Docker:

```bash
$ docker volume ls | grep demo
local     adk-demo_engine-db          # ✅ Named volume (can be targeted for removal)
local     adk-demo_keycloak-db
local     adk-demo_keycloak-provisioning
```

## Testing the Fix

To apply the fix to an existing setup:

1. **Stop all services:**
   ```bash
   docker-compose down
   ```

2. **Remove old anonymous volumes:**
   ```bash
   docker volume prune  # Remove all unused volumes
   ```

3. **Start services (creates new named volume):**
   ```bash
   docker-compose up -d
   ```

4. **Verify the named volume exists:**
   ```bash
   docker volume ls | grep adk-demo_engine-db
   ```

5. **Test the --clean flag:**
   ```bash
   ./start_demo.sh --clean
   ```

The NPL engine should now start with a completely empty database!

## Why This Matters

**For Development:**
- Clean testing environment on demand
- No stale data contaminating test runs
- Faster iteration (no manual database cleanup)

**For Demos:**
- Each demo starts fresh
- No confusion from old protocols
- Professional presentation

**For Debugging:**
- Isolate issues to current session
- Reproducible test scenarios
- Clear before/after comparisons

## Related Issues

This fix resolves:
- ✅ Old approvals appearing after restart
- ✅ Agents referencing products from past sessions
- ✅ Protocol memory not matching database state
- ✅ Inability to test workflow changes cleanly

## Related Files

- `docker-compose.yml` - Volume definitions
- `start_demo.sh` - Session-level cleanup with `--clean`
- `scripts/setup-fresh.sh` - Full infrastructure reset
- `docs/SESSION_MANAGEMENT.md` - Session management overview

