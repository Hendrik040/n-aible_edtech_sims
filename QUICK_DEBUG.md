# Quick Debug Reference

## 🚀 Fastest Way to Debug

### Option 1: VS Code Debugger (Best for Step-by-Step)
1. Open `backend/api/publishing.py`
2. Set breakpoint at line **1756** (publish start) or **1566** (save start)
3. Press **F5** → Select "Python: FastAPI (Backend)"
4. Click publish button in browser
5. Code will pause at breakpoint - use F10/F11 to step through

### Option 2: Terminal with Logs (Best for Quick Check)
```bash
cd backend
./run_debug.sh
# OR manually:
source venv/bin/activate
python -m uvicorn main:app --reload
```
Then watch terminal for `[PUBLISH]`, `[SAVE]`, `[SCENE_UPDATE]` logs

### Option 3: Add pdb Breakpoint (Quick & Dirty)
Add this line in `publishing.py` where you want to pause:
```python
import pdb; pdb.set_trace()
```

## 🔍 Key Log Tags to Watch

- `[PUBLISH]` - Publish endpoint activity
- `[SAVE]` - Save operations  
- `[SCENE_UPDATE]` - Scene matching/updates
- `[SCENE_DELETE]` - Scene deletions
- `⚠️ WARNING` - Race conditions or issues

## 📍 Strategic Breakpoint Locations

**In `backend/api/publishing.py`:**
- Line **1756**: Publish endpoint entry
- Line **1566**: Save endpoint entry  
- Line **1182**: Scene matching logic
- Line **1503**: Scene deletion logic
- Line **1224**: Scene existence verification

## 🐛 Common Issues

1. **"Scene no longer exists"** → Race condition - scene deleted while updating
2. **"Scenario not found"** → Wrong scenario ID
3. **Save fails** → Check `[SAVE]` logs for errors

## 💡 Pro Tips

- **Filter logs**: `grep -E "\[PUBLISH\]|\[SAVE\]"` in terminal
- **Check browser console**: Look for `[PUBLISH]` logs there too
- **Database check**: Verify scenario/scenes exist before debugging

