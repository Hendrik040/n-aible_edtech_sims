# Debugging Guide for Publish Button Issue

## Quick Start - Debugging Steps

### Method 1: VS Code Debugger (Recommended)

1. **Set Breakpoints**:
   - Open `backend/api/publishing.py`
   - Click in the left margin to set breakpoints at:
     - Line 1756: `[PUBLISH] 🚀 Starting publish`
     - Line 1566: `[SAVE] 💾 Starting save_scenario_draft`
     - Line 1182: Scene matching logic
     - Line 1503: Scene deletion logic

2. **Start Debugging**:
   - Press `F5` or go to Run > Start Debugging
   - Select "Python: FastAPI (Backend)"
   - The server will start with debugging enabled
   - Breakpoints will pause execution when hit

3. **Debug Actions**:
   - **F10**: Step Over
   - **F11**: Step Into
   - **Shift+F11**: Step Out
   - **F5**: Continue
   - **Shift+F5**: Stop debugging

### Method 2: Terminal with Virtual Environment

1. **Activate Virtual Environment**:
   ```bash
   cd backend
   source venv/bin/activate  # On Mac/Linux
   # OR
   .\venv\Scripts\activate   # On Windows
   ```

2. **Run with Debug Logging**:
   ```bash
   python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
   ```

3. **Watch Logs**:
   - All debug logs will appear in the terminal
   - Look for tags: `[PUBLISH]`, `[SAVE]`, `[SCENE_UPDATE]`, `[SCENE_DELETE]`

### Method 3: Add Python Debugger (pdb) Breakpoints

Add this line where you want to pause:
```python
import pdb; pdb.set_trace()
```

Example in `publishing.py`:
```python
@router.post("/publish/{scenario_id}")
async def publish_scenario(...):
    import pdb; pdb.set_trace()  # Breakpoint here
    debug_log(f"[PUBLISH] 🚀 Starting publish for scenario {scenario_id}")
    # ... rest of code
```

Then run normally - it will pause at the breakpoint.

## What to Look For

### In Browser Console (F12):
- `[PUBLISH] 🚀 Starting publish flow`
- `[PUBLISH] 💾 Saving scenario first...`
- `[PUBLISH] 📤 Sending publish request`
- `[PUBLISH] ❌` - Any errors

### In Backend Terminal:
- `[PUBLISH] 🚀 Starting publish for scenario X`
- `[SAVE] 💾 Starting save_scenario_draft`
- `[SCENE_UPDATE] 🔄 Found existing scene`
- `[SCENE_UPDATE] ⚠️ WARNING` - Race condition detected
- `[SCENE_DELETE] 🗑️ Safely deleting X scenes`

## Common Issues to Check

1. **Scene Deletion Race Condition**:
   - Look for: `[SCENE_UPDATE] ⚠️ WARNING: Scene X was deleted before update`
   - This means a scene was deleted while being updated

2. **Missing Scenario**:
   - Look for: `[PUBLISH] ❌ Scenario X not found`
   - The scenario ID might be wrong

3. **Save Fails Before Publish**:
   - Look for: `[SAVE]` errors
   - Check if `handleSave()` completes successfully

## Debugging Tips

1. **Filter Logs**: Use `grep` to filter:
   ```bash
   # In terminal, filter for publish-related logs
   python -m uvicorn main:app --reload 2>&1 | grep -E "\[PUBLISH\]|\[SAVE\]|\[SCENE"
   ```

2. **Check Database State**:
   - Before clicking publish, note the scenario ID
   - Check if scenes exist for that scenario
   - Verify scene IDs match what's being deleted

3. **Step Through Code**:
   - Use VS Code debugger to step through line by line
   - Watch variable values in the Variables panel
   - Check the Call Stack to see execution flow

## Quick Debug Checklist

When publish breaks:
- [ ] Check browser console for `[PUBLISH]` errors
- [ ] Check backend terminal for `[SCENE_UPDATE]` warnings
- [ ] Verify scenario exists in database
- [ ] Check if scenes are being deleted prematurely
- [ ] Look for race condition warnings
- [ ] Verify `handleSave()` completes before publish

