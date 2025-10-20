#!/usr/bin/env python3
"""
Setup script for refactoring helpers.py into multiple modules.
This script creates the new directory structure and initial module files.

Usage:
    python scripts/setup_refactoring.py [--dry-run]
"""

import os
import sys
import argparse
from pathlib import Path

def create_module_structure(base_path: Path, dry_run: bool = False):
    """Create the new module directory structure."""

    # Define the new structure
    modules = {
        'config': {
            '__init__.py': '"""Configuration management module."""\n',
            'environment.py': '"""Environment configuration and validation."""\n\nimport os\nimport logging\nfrom typing import Dict, Any\n\nlogger = logging.getLogger(__name__)\n',
            'paths.py': '"""Path utilities and management."""\n\nimport os\nfrom pathlib import Path\nimport tempfile\nimport hashlib\n',
        },
        'browser': {
            '__init__.py': '"""Browser management module."""\n',
            'chrome.py': '"""Chrome browser lifecycle management."""\n\nimport os\nimport subprocess\nimport psutil\nfrom typing import Optional, Tuple\n',
            'driver.py': '"""WebDriver instance management."""\n\nfrom selenium import webdriver\nfrom typing import Optional\nimport logging\n\nlogger = logging.getLogger(__name__)\n',
            'devtools.py': '"""Chrome DevTools Protocol operations."""\n\nimport urllib.request\nimport json\nfrom typing import Optional, Dict\n',
            'process.py': '"""Process and port management."""\n\nimport socket\nimport psutil\nfrom typing import Optional\n',
        },
        'locking': {
            '__init__.py': '"""Multi-agent coordination and locking."""\n',
            'action_lock.py': '"""Action-level locking for coordination."""\n\nimport json\nimport time\nimport asyncio\nfrom typing import Dict, Any, Optional\n',
            'window_registry.py': '"""Window ownership and lifecycle tracking."""\n\nimport json\nimport time\nfrom typing import Dict, Any, Optional\n',
            'file_mutex.py': '"""Low-level file-based mutex operations."""\n\nimport os\nimport time\nimport fcntl if os.name != "nt" else None\nimport contextlib\n',
        },
        'actions': {
            '__init__.py': '"""High-level browser actions."""\n',
            'navigation.py': '"""URL navigation and page loading."""\n\nfrom typing import Optional\nimport asyncio\nimport logging\n\nlogger = logging.getLogger(__name__)\n',
            'elements.py': '"""Element interaction operations."""\n\nfrom selenium.webdriver.common.by import By\nfrom selenium.webdriver.support.ui import WebDriverWait\nfrom selenium.webdriver.support import expected_conditions as EC\nfrom typing import Optional, Union\nimport logging\n\nlogger = logging.getLogger(__name__)\n',
            'screenshots.py': '"""Screenshot capture and processing."""\n\nimport base64\nfrom io import BytesIO\nfrom PIL import Image\nfrom typing import Optional\n',
            'keyboard.py': '"""Keyboard and scroll operations."""\n\nfrom selenium.webdriver.common.keys import Keys\nfrom typing import Optional\nimport logging\n\nlogger = logging.getLogger(__name__)\n',
        },
        'utils': {
            '__init__.py': '"""Utility functions and helpers."""\n',
            'diagnostics.py': '"""Debug and diagnostic utilities."""\n\nimport platform\nimport traceback\nfrom typing import Optional, Dict, Any\nimport logging\n\nlogger = logging.getLogger(__name__)\n',
            'retry.py': '"""Retry logic and error handling."""\n\nimport time\nimport logging\nfrom typing import Callable, Any\n\nlogger = logging.getLogger(__name__)\n',
            'html_utils.py': '"""HTML cleaning and processing utilities."""\n\nfrom bs4 import BeautifulSoup\nfrom typing import Optional\nimport re\n',
        },
    }

    # Create directories and files
    for module_name, files in modules.items():
        module_path = base_path / module_name

        if dry_run:
            print(f"[DRY RUN] Would create directory: {module_path}")
        else:
            module_path.mkdir(exist_ok=True)
            print(f"Created directory: {module_path}")

        for filename, content in files.items():
            file_path = module_path / filename

            if dry_run:
                print(f"[DRY RUN] Would create file: {file_path}")
            else:
                if not file_path.exists():
                    file_path.write_text(content)
                    print(f"Created file: {file_path}")
                else:
                    print(f"File already exists: {file_path}")

def create_migration_tracker(base_path: Path, dry_run: bool = False):
    """Create a migration tracking file."""

    tracker_content = """# Migration Tracker for helpers.py Refactoring

## Status Legend
- ⬜ Not started
- 🟨 In progress
- ✅ Completed
- 🔄 Testing
- ✔️ Verified

## Function Migration Status

### config/environment.py
- ⬜ get_env_config()
- ⬜ profile_key()
- ⬜ is_default_user_data_dir()

### config/paths.py
- ⬜ rendezvous_path()
- ⬜ start_lock_dir()
- ⬜ chromedriver_log_path()
- ⬜ _lock_paths()
- ⬜ _same_dir()

### browser/chrome.py
- ⬜ _resolve_chrome_executable()
- ⬜ _chrome_binary_for_platform()
- ⬜ chrome_running_with_userdata()
- ⬜ find_chrome_process_by_port()
- ⬜ get_chrome_version()
- ⬜ _launch_chrome_with_debug()
- ⬜ start_or_attach_chrome_from_env()

### browser/driver.py
- ⬜ create_webdriver()
- ⬜ _ensure_driver()
- ⬜ _ensure_driver_and_window()
- ⬜ _ensure_singleton_window()
- ⬜ close_singleton_window()
- ⬜ _cleanup_own_blank_tabs()
- ⬜ _close_extra_blank_windows_safe()

### browser/devtools.py
- ⬜ _read_devtools_active_port()
- ⬜ devtools_active_port_from_file()
- ⬜ _devtools_user_data_dir()
- ⬜ _verify_port_matches_profile()
- ⬜ is_debugger_listening()
- ⬜ _ensure_debugger_ready()

### browser/process.py
- ⬜ get_free_port()
- ⬜ _is_port_open()
- ⬜ ensure_process_tag()
- ⬜ make_process_tag()
- ⬜ read_rendezvous()
- ⬜ write_rendezvous()
- ⬜ clear_rendezvous()

### locking/action_lock.py
- ⬜ get_intra_process_lock()
- ⬜ _renew_action_lock()
- ⬜ _read_softlock()
- ⬜ _write_softlock()
- ⬜ _acquire_softlock()
- ⬜ _release_action_lock()
- ⬜ _acquire_action_lock_or_error()

### locking/window_registry.py
- ⬜ _window_registry_path()
- ⬜ _read_window_registry()
- ⬜ _write_window_registry()
- ⬜ _register_window()
- ⬜ _update_window_heartbeat()
- ⬜ _unregister_window()
- ⬜ cleanup_orphaned_windows()

### locking/file_mutex.py
- ⬜ _file_mutex()
- ⬜ acquire_start_lock()
- ⬜ release_start_lock()

### actions/navigation.py
- ⬜ navigate_to_url()
- ⬜ _wait_document_ready()
- ⬜ wait_for_element()
- ⬜ get_current_page_meta()

### actions/elements.py
- ⬜ find_element()
- ⬜ _wait_clickable_element()
- ⬜ get_by_selector()
- ⬜ click_element()
- ⬜ fill_text()
- ⬜ debug_element()

### actions/screenshots.py
- ⬜ take_screenshot()
- ⬜ _make_page_snapshot()

### actions/keyboard.py
- ⬜ send_keys()
- ⬜ scroll()

### utils/diagnostics.py
- ⬜ collect_diagnostics()
- ⬜ get_debug_diagnostics_info()

### utils/retry.py
- ⬜ retry_op()
- ⬜ _read_json()

### utils/html_utils.py
- ⬜ remove_unwanted_tags()
- ⬜ get_cleaned_html()

## Notes
- Update this file as functions are migrated
- Add any issues or dependencies discovered during migration
"""

    tracker_path = base_path.parent / "MIGRATION_TRACKER.md"

    if dry_run:
        print(f"[DRY RUN] Would create tracker: {tracker_path}")
    else:
        tracker_path.write_text(tracker_content)
        print(f"Created migration tracker: {tracker_path}")

def create_compatibility_layer(base_path: Path, dry_run: bool = False):
    """Create the initial compatibility layer in helpers.py."""

    compat_content = '''"""
Compatibility layer for helpers.py refactoring.
This file will maintain backward compatibility during the migration.

During migration:
1. Functions are moved to their new modules
2. This file imports them and re-exports
3. Once migration is complete, this becomes a thin compatibility shim
"""

# Phase 1: Import existing helpers content
# (This will be replaced gradually as we migrate functions)

# During migration, we'll add imports like:
# from .config.environment import get_env_config
# from .browser.chrome import start_or_attach_chrome_from_env
# etc.

# For now, maintain a warning for developers
import warnings

def _migration_in_progress():
    warnings.warn(
        "helpers.py is being refactored into multiple modules. "
        "Please import from the specific modules instead.",
        DeprecationWarning,
        stacklevel=2
    )

# The original helpers.py content will be preserved here initially
# and gradually replaced with imports from the new modules
'''

    helpers_backup = base_path.parent / "helpers_original.py.bak"
    helpers_path = base_path.parent / "helpers.py"

    if dry_run:
        print(f"[DRY RUN] Would backup helpers.py to: {helpers_backup}")
        print(f"[DRY RUN] Would create compatibility stub at: {base_path.parent / 'helpers_compat.py'}")
    else:
        # Create a backup of the original
        if helpers_path.exists() and not helpers_backup.exists():
            import shutil
            shutil.copy2(helpers_path, helpers_backup)
            print(f"Backed up original helpers.py to: {helpers_backup}")

        # Create compatibility stub (don't overwrite actual helpers.py yet)
        compat_path = base_path.parent / "helpers_compat.py"
        compat_path.write_text(compat_content)
        print(f"Created compatibility stub: {compat_path}")

def main():
    parser = argparse.ArgumentParser(description="Setup refactoring structure for helpers.py")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be created without creating files")
    parser.add_argument("--base-path", type=str, help="Base path for src/mcp_browser_use",
                       default="src/mcp_browser_use")

    args = parser.parse_args()

    base_path = Path(args.base_path)

    if not base_path.exists():
        print(f"Error: Base path does not exist: {base_path}")
        sys.exit(1)

    print(f"Setting up refactoring structure in: {base_path}")
    print(f"Dry run: {args.dry_run}")
    print("-" * 50)

    # Create the module structure
    create_module_structure(base_path, args.dry_run)

    # Create migration tracker
    create_migration_tracker(base_path, args.dry_run)

    # Create compatibility layer
    create_compatibility_layer(base_path, args.dry_run)

    print("-" * 50)
    if args.dry_run:
        print("Dry run complete. No files were created.")
        print("Run without --dry-run to create the structure.")
    else:
        print("Refactoring structure created successfully!")
        print("\nNext steps:")
        print("1. Review the created structure")
        print("2. Start migrating functions according to MIGRATION_TRACKER.md")
        print("3. Update imports in __main__.py as you migrate")
        print("4. Run tests after each migration phase")

if __name__ == "__main__":
    main()