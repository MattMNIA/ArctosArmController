# Homing Process Comparison: c495e25 (Working) vs Current

## Summary of Key Differences

| Aspect | OLD (c495e25 - Working) | NEW (Current) |
|--------|-------------------------|---------------|
| `is_motor_running()` | Returns `True` if query fails (None != MotorStop) | Returns `False` if query fails |
| Stop motors timing | Back-to-back calls, single 0.2s sleep | 0.05s delay between calls, 0.3s sleep after |
| Wait after stop | None | Added wait loop with 3s timeout |
| Offset motion calls | Back-to-back | 0.05s delay between calls |
| Wait for offset | Simple `while` loop, 0.1s initial sleep | 0.2s initial sleep, timeout after 10s |
| Zero commands | Back-to-back | 0.1s delay before, 0.05s between |

---

## OLD VERSION (c495e25) - Joint 4 Homing Flow

### Phase 1: Move to limit switch
```
1. servo5.run_motor_in_speed_mode(direction_5, coord_speed, 150)
2. servo6.run_motor_in_speed_mode(direction_6_opposite, coord_speed, 150)
3. Loop: check io_status every 0.05s until limit_hit or 30s timeout
4. servo5.stop_motor_in_speed_mode(255)
5. servo6.stop_motor_in_speed_mode(255)   <-- IMMEDIATELY after servo5
6. time.sleep(0.2)
```

### Phase 2: Move offset
```
7. servo5.run_motor_relative_motion_by_axis(offset_speed, 150, offset5)
8. servo6.run_motor_relative_motion_by_axis(offset_speed, 150, -1*offset5)  <-- IMMEDIATELY after servo5
9. time.sleep(0.1)
10. Loop: while servo5.is_motor_running() or servo6.is_motor_running(): sleep(0.05)
```

### Phase 3: Zero
```
11. servo5.set_current_axis_to_zero()
12. servo6.set_current_axis_to_zero()   <-- IMMEDIATELY after servo5
13. logger.info("Joint 4 homing completed successfully")
```

### `is_motor_running()` behavior (OLD):
```python
def is_motor_running(self):
    return self.query_motor_status() != MotorStatus.MotorStop
    # If query_motor_status() returns None:
    # None != MotorStatus.MotorStop -> True (motor appears running)
```

### `run_motor_relative_motion_by_axis()` precondition (OLD):
```python
def run_motor_relative_motion_by_axis(self, speed, acceleration, relative_axis):
    if self.is_motor_running():           # <-- CHECKS IF MOTOR IS RUNNING
        raise motor_already_running_error("")   # <-- RAISES EXCEPTION IF TRUE
    # ... rest of function
```

---

## NEW VERSION (Current) - Joint 4 Homing Flow

### Phase 1: Move to limit switch
```
1. servo5.run_motor_in_speed_mode(direction_5, coord_speed, 150)
2. servo6.run_motor_in_speed_mode(direction_6_opposite, coord_speed, 150)
3. Loop: check io_status every 0.05s until limit_hit or 30s timeout
4. servo5.stop_motor_in_speed_mode(255)
5. time.sleep(0.05)                       <-- NEW: 50ms delay
6. servo6.stop_motor_in_speed_mode(255)
7. time.sleep(0.3)                        <-- CHANGED: 300ms instead of 200ms
8. Loop: while servo5.is_motor_running() or servo6.is_motor_running():  <-- NEW: wait loop
      if timeout > 3.0s: break
      sleep(0.1)
```

### Phase 2: Move offset
```
9. servo5.run_motor_relative_motion_by_axis(offset_speed, 150, offset5)
10. time.sleep(0.05)                       <-- NEW: 50ms delay
11. servo6.run_motor_relative_motion_by_axis(offset_speed, 150, -1*offset5)
12. time.sleep(0.2)                        <-- CHANGED: 200ms instead of 100ms
13. Loop: while servo5.is_motor_running() or servo6.is_motor_running():
       if timeout > 10.0s: break           <-- NEW: timeout
       sleep(0.1)                          <-- CHANGED: 100ms instead of 50ms
```

### Phase 3: Zero
```
14. time.sleep(0.1)                        <-- NEW: 100ms delay
15. servo5.set_current_axis_to_zero()
16. time.sleep(0.05)                       <-- NEW: 50ms delay
17. servo6.set_current_axis_to_zero()
18. logger.info("Joint 4 homing completed successfully")
```

### `is_motor_running()` behavior (NEW):
```python
def is_motor_running(self):
    status = self.query_motor_status()
    if status is None:
        return False   # <-- NEW: Returns False if query fails
    return status != MotorStatus.MotorStop
```

---

## Critical Analysis

### Issue 1: `is_motor_running()` change affects `run_motor_relative_motion_by_axis()`

**OLD behavior:**
- If CAN fails, `query_motor_status()` returns `None`
- `None != MotorStatus.MotorStop` = `True`
- `is_motor_running()` returns `True`
- `run_motor_relative_motion_by_axis()` raises `motor_already_running_error`
- Exception propagates up and homing fails visibly

**NEW behavior:**
- If CAN fails, `query_motor_status()` returns `None`
- `is_motor_running()` returns `False`
- `run_motor_relative_motion_by_axis()` passes the check
- But then the actual CAN command might fail silently
- Homing continues without actually moving

### Issue 2: Added delays may cause timing issues

The new version adds many delays (0.05s between commands). While this was intended to reduce CAN bus congestion, it may:
- Cause the motor status to change between check and command
- Create race conditions with the servo's internal state machine

### Issue 3: Wait loop after stop is problematic

```python
# NEW CODE:
while servo5.is_motor_running() or servo6.is_motor_running():
    if time.time() - stop_wait_start > 3.0:
        logger.warning("Timeout waiting for motors to stop after limit hit")
        break
    time.sleep(0.1)
```

If `is_motor_running()` returns `False` due to CAN failure (new behavior), this loop exits immediately even if motors are still running. Then `run_motor_relative_motion_by_axis()` is called while motors may still be moving.

### Issue 4: The 50ms delay between servo5 and servo6 offset commands

**OLD:** Both commands sent back-to-back
```python
servo5.run_motor_relative_motion_by_axis(offset_speed, 150, offset5)
servo6.run_motor_relative_motion_by_axis(offset_speed, 150, -1*offset5)
```

**NEW:** 50ms delay between them
```python
servo5.run_motor_relative_motion_by_axis(offset_speed, 150, offset5)
time.sleep(0.05)
servo6.run_motor_relative_motion_by_axis(offset_speed, 150, -1*offset5)
```

This delay means servo5 starts moving first, and then servo6 starts 50ms later. For coordinated coupled joint motion, this desynchronization could cause mechanical issues.

---

## Recommendations

1. **Revert `is_motor_running()` to old behavior** - The change to return `False` on failure masks CAN errors
2. **Remove the extra delays between motor commands** - They desynchronize coupled movements
3. **Remove the new wait loop after stopping** - It's not in the working version
4. **Keep commands back-to-back** like the old version

The old version worked because it was simpler and didn't try to handle errors - errors propagated up naturally. The new version's "improvements" actually hide failures and desynchronize movements.
