# Project Name Isolation - Multiple Users, Same Names

## Problem

Previously, if two users created projects with the same name, their files would conflict:

```
User A (Flow project UUID-A) creates "My Video" → output/my_video/
User B (Flow project UUID-B) creates "My Video" → output/my_video/  ← CONFLICT!
```

Files would overwrite each other because the directory was based only on the slug of the project name.

## Solution

### Current Implementation (Scoped Uniqueness)

The system now allows multiple users to create projects with the same name by:

1. **Scoping uniqueness checks by Flow project ID** instead of globally
2. **Supporting project-isolated directories** via `output/{project_id}/{slug}/`

### How It Works

#### Uniqueness Check (agent/api/projects.py:248-274)

```python
async def _require_unique_slug(name, project_id=None, flow_project_id=None):
    # Only checks for duplicate slugs within the SAME Flow project
    # Different Flow projects CAN have the same project names
```

**Result:**
- User A with Flow UUID-A can create "My Video"
- User B with Flow UUID-B can ALSO create "My Video"
- No conflict because they're in different Flow projects

#### Directory Structure (agent/utils/paths.py:7-19)

```python
def project_dir(project_slug: str, project_id: str = None) -> Path:
    if project_id:
        # New: output/{project_id}/{slug}/
        return OUTPUT_DIR / project_id / project_slug
    # Legacy: output/{slug}/
    return OUTPUT_DIR / project_slug
```

**Backward Compatibility:**
- Old projects without `project_id` → `output/{slug}/` (legacy path)
- New projects with `project_id` → `output/{project_id}/{slug}/` (isolated)

## File Structure Examples

### Scenario: Two users create "My Video"

**User A** (Flow project `abc-123...`):
```
output/
  abc-123.../
    my_video/
      scenes/
        scene_001_sid123.mp4
        scene_002_sid456.mp4
      tts/
        scene_001_sid123.wav
      music/
```

**User B** (Flow project `def-456...`):
```
output/
  def-456.../
    my_video/
      scenes/
        scene_001_sid789.mp4
      tts/
```

No conflicts! Each project is fully isolated.

## Migration Strategy

### For Existing Projects (Legacy)

Old projects continue to work with the flat structure (`output/{slug}/`). They:
- Still have global uniqueness enforced (to prevent file conflicts)
- Use legacy paths when `project_id` is not provided
- Will NOT automatically migrate to new structure

### For New Projects

New projects created after this change:
- Use isolated directories (`output/{project_id}/{slug}/`)
- Only need unique names within their Flow project
- Multiple users can use the same project name

## Code Changes

### 1. Path Utilities (agent/utils/paths.py)

All path functions now accept optional `project_id`:

```python
project_dir(project_slug, project_id=None)
scene_4k_path(project_slug, display_order, scene_id, project_id=None)
scene_tts_path(project_slug, display_order, scene_id, project_id=None)
scene_video_path(project_slug, display_order, scene_id, subdir, project_id=None)
resolve_4k_file(project_slug, display_order, scene_id, project_id=None)
```

### 2. Uniqueness Check (agent/api/projects.py)

```python
# Before: Global check across ALL projects
await _require_unique_slug(body.name)

# After: Scoped check within same Flow project
await _require_unique_slug(body.name, flow_project_id=flow_project_id)
```

### 3. Usage in Code

Callers can optionally pass `project_id` for isolation:

```python
# Legacy (backward compatible)
path = project_dir(slug)

# New (isolated)
path = project_dir(slug, project_id=project.id)
```

## When to Use Project Isolation

**Use `project_id` parameter when:**
- Creating new projects (ensures isolation)
- Rendering files for multi-user systems
- Want to guarantee no file conflicts

**Skip `project_id` when:**
- Working with legacy projects
- Backward compatibility required
- Single-user deployment

## Benefits

✅ **Multi-user safe** - Different users can use same project names
✅ **Backward compatible** - Old projects still work
✅ **Scalable** - Each project in its own namespace
✅ **Clean separation** - Easy to backup/delete per-project
✅ **Future-proof** - Supports multiple local projects per Flow project

## Future Work

- [ ] Add migration tool to move legacy projects to isolated structure
- [ ] Update all callers to pass `project_id` consistently
- [ ] Add admin API to list/manage project directories
- [ ] Cleanup orphaned directories when projects deleted

---

For more details, see:
- `agent/utils/paths.py` - Path resolution logic
- `agent/api/projects.py` - Project creation and validation
- `FLOW_PROJECT_POOL.md` - Flow project pool system
