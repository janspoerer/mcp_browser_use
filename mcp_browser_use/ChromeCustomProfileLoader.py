import os
import time
import shutil
import tempfile
import traceback
import pandas as pd
from PIL import Image                   # Ensure Pillow is installed: pip install pillow
import mysql.connector
from sys import platform
from datetime import datetime
from selenium import webdriver
from pathlib import Path, WindowsPath
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, SessionNotCreatedException, WebDriverException


class ChromeCustomProfileLoader:
    """Launch ChromeDriver against a custom profile location."""

    @staticmethod
    def launch_with_custom_profile(
        custom_data_dir: str, # The path to the custom user data directory
        profile_folder: str = "Default", # The profile folder name within the custom dir
        is_headless: bool = False
    ) -> webdriver.Chrome:
        print(f"Using custom user data directory: {custom_data_dir}")
        print(f"Targeting profile folder: {profile_folder}")

        options = webdriver.ChromeOptions()
        # *** Use the custom user data directory where you pasted the Default profile ***
        options.add_argument(f"--user-data-dir={custom_data_dir}")
        # *** Specify the 'Default' profile folder within the custom directory ***
        options.add_argument(f"--profile-directory={profile_folder}") # This should now load the copied Default profile

        # Keep the --no-proxy-server argument
        options.add_argument("--no-proxy-server")

        # Keep other potentially helpful arguments
        # options.add_argument("--disable-extensions") # This argument disables extensions installed via web store normally,
                                                    # but extensions within a loaded profile are often an exception.
                                                    # Keep it for compatibility, but be aware the VPN might work despite it.
        # options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        # options.add_argument("--disable-dev-shm-usage")

        # Optional: Keep logging enabled for troubleshooting if needed
        log_directory = os.path.join(os.path.expanduser("~"), "Documents")
        log_file = os.path.join(log_directory, f"chromedriver_custom_{profile_folder}_log.txt")
        service_args = ['--verbose', f'--log-path={log_file}']
        # print(f"ChromeDriver service args: {service_args}") # Keep commented unless needed for debugging
        # print(f"Logging to: {log_file}") # Keep commented unless needed for debugging

        # Optional: Enable Chrome internal verbose logging (might create chrome_debug.log)
        options.add_argument("--verbose")


        if is_headless:
             options.add_argument("--headless=new")

        print(f"Chrome Options being used: {options.arguments}")

        try:
            chrome_driver_path = ChromeDriverManager().install()
            # print(f"Using ChromeDriver at: {chrome_driver_path}") # Keep commented unless needed

            service = Service(executable_path=chrome_driver_path)#, service_args=service_args) # Keep service_args commented unless needed

            print(f"Attempting to launch Chrome with custom profile at {custom_data_dir}...")
            # Add a small delay before initiating the session - important for extensions
            time.sleep(1)

            driver = webdriver.Chrome(service=service, options=options)
            print(f"Chrome launched successfully with custom profile!")
            return driver
        except Exception as e:
            print(f"Failed to launch Chrome with custom profile: {e}")
            # print(f"Check the ChromeDriver log file at {log_file} for details.") # Keep commented unless needed
            # print("Also check for Chrome internal log files (e.g., chrome_debug.log in the custom data dir or temp).") # Keep commented
            raise # Re-raise the exception
