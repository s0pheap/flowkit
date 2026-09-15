# Flow Project Pool - Multi-Project Support for Users

This document explains how the Flow Project Pool works, allowing multiple users to have multiple Flow projects without manual RPC capture.

## Overview

**Problem**: Flow project creation via API is not currently supported (requires capturing the RPC payload from the Flow UI).

**Solution**: Create a pool of pre-made Flow project UUIDs that get automatically assigned to users when they need them.

## How It Works

### 1. Admin Creates Flow Projects (in Flow UI)

```
1. Go to https://flow.google.com
2. Click "+ New Project"
3. Create project, get UUID (from URL or project settings)
4. Repeat for as many projects as you need
```

### 2. Admin Adds Projects to Pool (via API)

```bash
curl "$FK/api/flow-pool" -X POST -H "$ADMIN_KEY" -H "Content-Type: application/json" -d '{
  "flow_project_id": "c44bcef5-de99-4b52-b8a5-27f0fe67bc67",
  "notes": "Created 2026-09-15 for production users"
}'
```

The project is now in the pool, **available** for assignment.

### 3. User Creates Their First Project (Auto-Assignment)

When a user with no Flow projects calls `POST /api/projects`:

```bash
curl "$FK/api/projects" -X POST -H "$USER_KEY" -H "Content-Type: application/json" -d '{
  "name": "My First Video",
  "description": "Test project"
}'
```

**What happens automatically:**
1. System checks: user has no Flow projects
2. Gets next available project from pool
3. Assigns it to the user
4. Grants user access via `user_project` table
5. Creates local project using that Flow UUID
6. Returns success

The user now has their own Flow project!

### 4. User Creates More Projects

For subsequent projects, the user can:
- **Reuse the same Flow project** (default behavior)
- **Get another from pool** (if admin added more and user requests)
- **Specify a different Flow project** they were granted access to

## Database Schema

### `flow_project_pool` Table

```sql
CREATE TABLE flow_project_pool (
    flow_project_id    TEXT PRIMARY KEY,           -- UUID from Flow UI
    assigned_to_user   TEXT REFERENCES api_user,   -- NULL = available
    assigned_at        TEXT,                        -- When assigned
    notes              TEXT,                        -- Optional description
    created_at         TEXT
);
```

### `api_user` Table (Enhanced)

```sql
ALTER TABLE api_user ADD COLUMN default_flow_project_id TEXT;
```

Users can set a default Flow project for convenience.

## API Endpoints

### Admin Endpoints (Flow Pool Management)

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/flow-pool` | List all projects (filter by `?assigned=true/false`) |
| POST | `/api/flow-pool` | Add a Flow project UUID to pool |
| GET | `/api/flow-pool/{id}` | Get details of a pool project |
| DELETE | `/api/flow-pool/{id}` | Remove from pool |
| POST | `/api/flow-pool/{id}/assign` | Manually assign to user |
| POST | `/api/flow-pool/{id}/unassign` | Make available again |
| GET | `/api/flow-pool/available/next` | Preview next available project |
| GET | `/api/flow-pool/user/{uid}/projects` | List user's assigned projects |

### User Workflow

Users don't interact with the pool directly. They just:

```bash
# Create project - auto-assigns if needed
POST /api/projects
{
  "name": "My Video",
  "description": "..."
}

# Or specify which Flow project to use
POST /api/projects
{
  "name": "My Video",
  "flow_project_id": "specific-uuid-here"
}
```

## Priority Logic for Flow Project Selection

When a user creates a project without specifying `flow_project_id`, the system tries in order:

1. **User's default Flow project** (if set via `default_flow_project_id`)
2. **User's only unused granted project** (if they have exactly one)
3. **Auto-assign from pool** (if user has no Flow projects yet)
4. **Error** (no options available)

This ensures:
- Experienced users keep using their preferred Flow project
- New users get automatically onboarded
- No manual assignment needed for most cases

## Example Workflows

### Workflow 1: Onboarding New User

```bash
# Admin: Add 5 Flow projects to pool
for uuid in uuid1 uuid2 uuid3 uuid4 uuid5; do
  curl "$FK/api/flow-pool" -X POST -H "$ADMIN_KEY" -d "{\"flow_project_id\":\"$uuid\"}"
done

# User1: Creates first project (gets uuid1)
curl "$FK/api/projects" -X POST -H "$USER1_KEY" -d '{"name":"Video1"}'
# System: Auto-assigned uuid1 to user1

# User2: Creates first project (gets uuid2)
curl "$FK/api/projects" -X POST -H "$USER2_KEY" -d '{"name":"Video2"}'
# System: Auto-assigned uuid2 to user2

# User1: Creates second project (reuses uuid1)
curl "$FK/api/projects" -X POST -H "$USER1_KEY" -d '{"name":"Video3"}'
# System: Uses same uuid1 (already granted)
```

### Workflow 2: Power User with Multiple Flow Projects

```bash
# Admin: Assign 3 Flow projects to one user
curl "$FK/api/flow-pool/uuid1/assign" -X POST -H "$ADMIN_KEY" -d '{"user_id":"user123"}'
curl "$FK/api/flow-pool/uuid2/assign" -X POST -H "$ADMIN_KEY" -d '{"user_id":"user123"}'
curl "$FK/api/flow-pool/uuid3/assign" -X POST -H "$ADMIN_KEY" -d '{"user_id":"user123"}'

# User: Set default
# (Not implemented via API yet, but stored in DB)

# User: Create project in specific Flow project
curl "$FK/api/projects" -X POST -H "$USER_KEY" -d '{
  "name":"Video1",
  "flow_project_id":"uuid2"
}'
```

### Workflow 3: Admin Monitoring

```bash
# Check available projects
curl "$FK/api/flow-pool?assigned=false" -H "$ADMIN_KEY"

# Check who's using what
curl "$FK/api/flow-pool?assigned=true" -H "$ADMIN_KEY"

# Get next available
curl "$FK/api/flow-pool/available/next" -H "$ADMIN_KEY"

# Reclaim a project (if user left)
curl "$FK/api/flow-pool/{uuid}/unassign" -X POST -H "$ADMIN_KEY"
```

## Advantages of This Approach

✅ **No RPC capture needed** - Works with current Flow API limitations
✅ **Zero-config for users** - Auto-assignment is transparent
✅ **Scales easily** - Admin adds more projects as needed
✅ **Flexible** - Users can have multiple Flow projects
✅ **Auditable** - Track which projects are assigned to whom
✅ **Recoverable** - Unassign and reassign projects as needed

## Limitations

⚠️ **Flow projects must be pre-created** - Admin work required
⚠️ **Pool can run dry** - If no available projects, user gets error
⚠️ **Not fully automated** - Can't create Flow projects on-demand (yet)

## Migration Path

If/when Flow project creation RPC is captured:

1. Implement `create_project_request()` in `flow_batch.py`
2. Update `flow_client.create_project()` to use it
3. Add option to auto-create instead of using pool
4. Keep pool system as fallback/alternative

The pool system and RPC-based creation can coexist!

## Monitoring & Maintenance

### Check pool status:
```bash
curl "$FK/api/flow-pool" -H "$ADMIN_KEY" | jq '.[] | select(.assigned_to_user == null) | .flow_project_id'
# Shows available project UUIDs
```

### Replenish pool:
```bash
# When available projects < 5, create more in Flow UI and add:
curl "$FK/api/flow-pool" -X POST -H "$ADMIN_KEY" -d '{"flow_project_id":"new-uuid"}'
```

### Audit assignments:
```bash
curl "$FK/api/flow-pool?assigned=true" -H "$ADMIN_KEY" | jq -r '.[] | "\(.assigned_to_user) -> \(.flow_project_id)"'
```

## Troubleshooting

### "No Flow projects available"
**Cause**: Pool is empty or all projects assigned
**Fix**: Add more Flow projects to pool

### "Flow project {id} already in pool"
**Cause**: Trying to add duplicate
**Fix**: Check existing pool, or use different UUID

### User doesn't get auto-assigned
**Cause**: User already has Flow projects granted
**Fix**: This is expected behavior - auto-assign only for new users

### Want to give user a fresh Flow project
**Solution**:
1. Add new project to pool
2. Manually assign: `POST /api/flow-pool/{new-uuid}/assign`
3. Or user requests it: `POST /api/projects` with `flow_project_id`

## Future Enhancements

- [ ] Dashboard UI for pool management
- [ ] Auto-refill: Create X Flow projects when pool < threshold
- [ ] User API to view their Flow projects
- [ ] User API to set default Flow project
- [ ] Metrics: projects per user, pool utilization
- [ ] Alerts when pool running low

---

For more details on Flow Kit architecture, see `CLAUDE.md` and `ARCHITECTURE.md`.
