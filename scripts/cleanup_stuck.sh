#!/bin/bash
# Kill collector processes running more than 6 hours
find /proc -maxdepth 1 -type d -name '[0-9]*' 2>/dev/null | while read pid_dir; do
    pid=$(basename "$pid_dir")
    if ps -p "$pid" -o args= 2>/dev/null | grep -q "etl.collector_cian"; then
        # Check if running more than 6 hours (21600 seconds)
        elapsed=$(ps -p "$pid" -o etimes= 2>/dev/null | tr -d ' ')
        if [ -n "$elapsed" ] && [ "$elapsed" -gt 21600 ]; then
            echo "Killing stuck process $pid (running ${elapsed}s)"
            kill "$pid" 2>/dev/null
        fi
    fi
done
echo "Cleanup done at $(date)"
