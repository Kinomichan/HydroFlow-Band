#!/usr/bin/env python3
import os
import sys
import subprocess
import argparse

# Default port
DEFAULT_PORT = "/dev/ttyACM0"

IGNORE_PATTERNS = {
    ".git",
    ".venv",
    ".antigravitycli",
    ".gitignore",
    "sync.py",
    "pull_logs.py",
    "downloaded_logs",
    "__pycache__",
    ".DS_Store",
    ".vscode",
    ".idea",
}

def should_ignore(path, mirror_all=False):
    parts = path.split(os.sep)
    for part in parts:
        if part in IGNORE_PATTERNS or part.startswith("."):
            return True
        if not mirror_all and (part.endswith(".log") or part.endswith(".bak")):
            return True
    return False

def get_sync_items(mirror_all=False):
    dirs_to_create = []
    files_to_copy = []
    
    for root, dirs, files in os.walk("."):
        # Remove ignored directories in-place so os.walk doesn't traverse them
        dirs[:] = [d for d in dirs if not should_ignore(os.path.join(root, d), mirror_all)]
        
        rel_root = os.path.relpath(root, ".")
        if rel_root != ".":
            dirs_to_create.append(rel_root.replace(os.sep, "/"))
            
        for file in files:
            rel_file = os.path.relpath(os.path.join(root, file), ".")
            if not should_ignore(rel_file, mirror_all):
                files_to_copy.append(rel_file.replace(os.sep, "/"))
                
    return sorted(dirs_to_create), sorted(files_to_copy)

def check_port_in_use(port):
    """Checks if the port is in use and returns the command/PID using it if possible."""
    if not sys.platform.startswith("linux"):
        return None
    try:
        # Run fuser to check if port is busy
        res = subprocess.run(["fuser", port], capture_output=True, text=True)
        if res.returncode == 0:
            pid = res.stdout.strip().split()[-1]
            # Try to get the command name for this PID
            cmd_res = subprocess.run(["ps", "-p", pid, "-o", "comm="], capture_output=True, text=True)
            cmd_name = cmd_res.stdout.strip() if cmd_res.returncode == 0 else "unknown"
            return {"pid": pid, "command": cmd_name}
    except Exception:
        pass
    return None

def run_mpremote(port, args):
    # Determine the python executable inside .venv
    venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
    if not os.path.exists(venv_python):
        venv_python = "python3"
        
    cmd = [venv_python, "-m", "mpremote", f"connect", port] + args
    
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip()
        # Check if port is busy
        in_use = check_port_in_use(port)
        if in_use:
            print(f"\n[Error] Failed to connect to {port}. The port is currently in use by:")
            print(f"  PID: {in_use['pid']} ({in_use['command']})")
            if "thonny" in in_use["command"].lower() or "python" in in_use["command"].lower():
                print("  -> Thonny (or another IDE) seems to be running. Please close it or stop its serial connection.")
            sys.exit(1)
        elif "could not enter raw repl" in err_msg.lower():
            print(f"\n[Error] Failed to connect: Could not enter raw REPL.")
            print("  This often happens with ESP32-S3 native USB CDC when the device is frozen or running a tight loop.")
            print("  Please try the following:")
            print("  1. Press the physical RESET button on the M5StickS3 (small red button on the side).")
            print("  2. Unplug and replug the USB cable.")
            print("  3. Make sure Thonny or any other serial monitor is completely closed.")
            sys.exit(1)
        else:
            print(f"\n[Error] mpremote failed: {err_msg}", file=sys.stderr)
            sys.exit(e.returncode)

def main():
    parser = argparse.ArgumentParser(description="Sync files and directories from current workspace to M5StickS3.")
    parser.add_argument("-p", "--port", default=DEFAULT_PORT, help=f"Serial port of M5StickS3 (default: {DEFAULT_PORT})")
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt")
    parser.add_argument("-c", "--clean", action="store_true", help="Delete files on device that do not exist locally (mirroring)")
    parser.add_argument("-m", "--mirror-all", action="store_true", help="Completely mirror all files including .log and .bak (except boot.py)")
    args = parser.parse_args()

    clean_mode = args.clean or args.mirror_all

    # Find files to sync
    dirs, files = get_sync_items(args.mirror_all)
    
    # 1. Retrieve remote files if clean option is requested
    remote_items = []
    files_to_delete = []
    dirs_to_delete = []
    
    if clean_mode:
        print("Scanning files on M5StickS3...")
        # Recursive walk snippet
        py_code = (
            "import os\n"
            "def walk(d):\n"
            "    items = []\n"
            "    try:\n"
            "        for entry in os.listdir(d):\n"
            "            path = (d + '/' + entry) if d else entry\n"
            "            try:\n"
            "                os.listdir(path)\n"
            "                items.append((path, True))\n"
            "                items.extend(walk(path))\n"
            "            except OSError:\n"
            "                items.append((path, False))\n"
            "    except OSError:\n"
            "        pass\n"
            "    return items\n"
            "print(walk(''))"
        )
        res = run_mpremote(args.port, ["exec", py_code])
        # Parse output safely
        try:
            import ast
            remote_items = ast.literal_eval(res.stdout.strip())
        except Exception as e:
            print(f"[Warning] Failed to parse remote files: {e}. Skipping cleanup.")
            remote_items = []

        # Identify files/dirs to delete
        for r_path, is_dir in remote_items:
            # Protect boot.py unless it is explicitly in our local files list
            if r_path == "boot.py" and "boot.py" not in files:
                continue
            
            # If not in mirror-all mode, protect .log and .bak files on the device from deletion
            if not args.mirror_all:
                if r_path.endswith(".log") or r_path.endswith(".bak"):
                    continue
            
            if is_dir:
                if r_path not in dirs:
                    dirs_to_delete.append(r_path)
            else:
                if r_path not in files:
                    files_to_delete.append(r_path)

        # Sort directories to delete by depth descending so nested dirs are deleted first
        dirs_to_delete.sort(key=lambda d: d.count('/'), reverse=True)

    if not dirs and not files and not files_to_delete and not dirs_to_delete:
        print("No changes to sync.")
        return
        
    print("Files/folders to sync:")
    if dirs:
        print("  Folders to create:")
        for d in dirs:
            print(f"    + {d}/")
    if files:
        print("  Files to copy/update:")
        for f in files:
            print(f"    -> {f}")
            
    if clean_mode and (files_to_delete or dirs_to_delete):
        print("\nFiles/folders to delete from M5StickS3 (Mirroring):")
        if dirs_to_delete:
            for d in dirs_to_delete:
                print(f"    - {d}/")
        if files_to_delete:
            for f in files_to_delete:
                print(f"    - {f}")
        
    if not args.yes:
        ans = input("\nDo you want to proceed with sync? [y/N]: ").strip().lower()
        if ans not in ("y", "yes"):
            print("Sync canceled.")
            return

    # Delete remote files first
    if clean_mode and files_to_delete:
        print("\nDeleting remote files...")
        for f in files_to_delete:
            print(f"  Deleting {f}...")
            run_mpremote(args.port, ["rm", f":{f}"])

    # Delete remote directories
    if clean_mode and dirs_to_delete:
        print("\nDeleting remote directories...")
        for d in dirs_to_delete:
            print(f"  Deleting folder {d}/...")
            run_mpremote(args.port, ["rmdir", f":{d}"])

    # 2. Create directories on the device
    if dirs:
        print("\nCreating directories on device...")
        # We send a small MicroPython snippet to create folders recursively if they don't exist
        # This prevents mpremote from erroring out if directories already exist.
        dir_list_str = str(dirs)
        py_code = (
            f"import os\n"
            f"dirs = {dir_list_str}\n"
            f"for d in dirs:\n"
            f"    parts = d.split('/')\n"
            f"    acc = ''\n"
            f"    for p in parts:\n"
            f"        if not p: continue\n"
            f"        acc = (acc + '/' + p) if acc else p\n"
            f"        try:\n"
            f"            os.mkdir(acc)\n"
            f"        except OSError:\n"
            f"            pass\n"
        )
        run_mpremote(args.port, ["exec", py_code])
        print("Directories verified/created.")

    # 3. Copy files to the device
    print("\nCopying files...")
    for f in files:
        print(f"  Copying {f}...")
        run_mpremote(args.port, ["cp", f, f":{f}"])
    print("All files copied successfully!")

    # Synchronize device clock with PC
    print("\nSynchronizing device RTC with host PC time...")
    try:
        run_mpremote(args.port, ["rtc"])
        print("RTC synchronized successfully.")
    except Exception as e:
        print(f"Warning: Could not sync RTC: {e}")

    # 4. Soft-reset the device to restart main.py
    print("\nResetting device to run updated code...")
    run_mpremote(args.port, ["soft-reset"])
    print("Device soft-reset complete.")

if __name__ == "__main__":
    main()
