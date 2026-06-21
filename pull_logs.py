#!/usr/bin/env python3
import os
import sys
import subprocess
import argparse
import datetime
import ast

# Default settings
DEFAULT_PORT = "/dev/ttyACM0"
DEFAULT_OUTPUT_DIR = "downloaded_logs"

def check_port_in_use(port):
    """Checks if the serial port is in use and returns the command/PID using it if possible."""
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
    """Helper function to run mpremote inside the virtual environment."""
    # Determine the python executable inside .venv
    venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
    if not os.path.exists(venv_python):
        venv_python = "python3"
        
    cmd = [venv_python, "-m", "mpremote", "connect", port] + args
    
    try:
        return subprocess.run(cmd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        err_msg = e.stderr.strip()
        # Check if port is busy
        in_use = check_port_in_use(port)
        if in_use:
            print(f"\n[Error] Failed to connect to {port}. The port is currently in use by:")
            print(f"  PID: {in_use['pid']} ({in_use['command']})")
            print("  -> Please close Thonny or any other serial monitor and try again.")
            sys.exit(1)
        elif "could not enter raw repl" in err_msg.lower():
            print(f"\n[Error] Failed to connect: Could not enter raw REPL.")
            print("  This often happens with ESP32-S3 native USB CDC when the device is frozen or running a tight loop.")
            print("  Please try the following:")
            print("  1. Press the physical RESET button on the M5StickS3.")
            print("  2. Unplug and replug the USB cable.")
            sys.exit(1)
        else:
            print(f"\n[Error] mpremote failed: {err_msg}", file=sys.stderr)
            sys.exit(e.returncode)

def main():
    parser = argparse.ArgumentParser(description="Pull log files from M5StickS3 to the local PC with timestamp suffixes.")
    parser.add_argument("-p", "--port", default=DEFAULT_PORT, help=f"Serial port of M5StickS3 (default: {DEFAULT_PORT})")
    parser.add_argument("-o", "--output-dir", default=DEFAULT_OUTPUT_DIR, help=f"Local directory to save logs (default: {DEFAULT_OUTPUT_DIR})")
    parser.add_argument("-c", "--clear", action="store_true", help="Delete the log files on the M5StickS3 after copying them")
    parser.add_argument("-y", "--yes", action="store_true", help="Skip confirmation prompt for clearing logs")
    args = parser.parse_args()

    # Step 1: Scan for log files on the device
    print(f"Scanning for log files on M5StickS3 via {args.port}...")
    
    # Recursive folder scanner python snippet to run on MicroPython device
    py_code = (
        "import os\n"
        "def find_logs(d=''):\n"
        "    logs = []\n"
        "    try:\n"
        "        for entry in os.listdir(d):\n"
        "            path = (d + '/' + entry) if d else entry\n"
        "            try:\n"
        "                os.listdir(path)\n"
        "                logs.extend(find_logs(path))\n"
        "            except OSError:\n"
        "                if path.endswith('.log') or path.endswith('.log.bak'):\n"
        "                    logs.append(path)\n"
        "    except OSError:\n"
        "        pass\n"
        "    return logs\n"
        "print(find_logs())"
    )
    
    res = run_mpremote(args.port, ["exec", py_code])
    
    try:
        remote_logs = ast.literal_eval(res.stdout.strip())
    except Exception as e:
        print(f"[Error] Failed to parse remote log files list: {e}")
        sys.exit(1)

    if not remote_logs:
        print("No log files (*.log, *.log.bak) found on the device.")
        return

    print(f"Found {len(remote_logs)} log file(s) on the device:")
    for log in remote_logs:
        print(f"  - {log}")

    # Ensure local output directory exists
    os.makedirs(args.output_dir, exist_ok=True)

    # Step 2: Download each log file with timestamp suffix
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    downloaded_files = []

    print(f"\nDownloading files to '{args.output_dir}'...")
    for remote_path in remote_logs:
        # Extract filename and extension
        base_name = os.path.basename(remote_path)
        name_parts = os.path.splitext(base_name)
        
        # If it's a backup like gsr_readings.log.bak, handle double extensions (.log.bak)
        if name_parts[1] == ".bak" and name_parts[0].endswith(".log"):
            inner_name = os.path.splitext(name_parts[0])[0]
            local_filename = f"{inner_name}_{timestamp}.log.bak"
        else:
            local_filename = f"{name_parts[0]}_{timestamp}{name_parts[1]}"
            
        local_path = os.path.join(args.output_dir, local_filename)
        
        print(f"  Copying remote:{remote_path} -> local:{local_path} ...")
        run_mpremote(args.port, ["cp", f":{remote_path}", local_path])
        downloaded_files.append((remote_path, local_path))

    print("Download complete!")

    # Step 3: Clear logs on the device if requested
    if args.clear:
        if not args.yes:
            ans = input("\nDo you want to delete these log files from the M5StickS3 to free up space? [y/N]: ").strip().lower()
            if ans not in ("y", "yes"):
                print("Logs kept on the device.")
                return

        print("\nDeleting log files from the device...")
        for remote_path, _ in downloaded_files:
            print(f"  Deleting remote:{remote_path} ...")
            run_mpremote(args.port, ["rm", f":{remote_path}"])
        print("Logs deleted from device successfully.")

if __name__ == "__main__":
    main()
