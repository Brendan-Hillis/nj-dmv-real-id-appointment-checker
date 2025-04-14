# nj-dmv-real-id-appointment-checker

# NJ MVC Appointment Checker

This Python script periodically checks the New Jersey Motor Vehicle Commission (NJ MVC) website for available appointments (specifically configured for Real ID by default) on or before a specified date. If suitable appointments are found, it sends an email notification using the Gmail API.

**Disclaimer:**
* **Website Terms of Service:** Please be aware of the NJ MVC website's terms of service regarding automated access and scraping. Use this script responsibly and at your own risk. Frequent checking might lead to your IP address being blocked. Consider increasing the `CHECK_INTERVAL_SECONDS` in the script.
* **Website Changes:** This script relies on the specific HTML structure of the NJ MVC website. If the website is updated, the script's scraping logic (`check_appointments_by_location_and_date` function) will likely break and require updates.
* **No Guarantees:** This tool does not guarantee you an appointment. It only notifies you about potential availability based on the information it can scrape.

## Features

* Checks for NJ MVC appointments (defaults to Real ID, URL path `/12`).
* Filters appointments based on a user-defined "need by" date.
* Sends email notifications via the Gmail API when suitable appointments are found.
* Handles Google API authentication using OAuth 2.0 (requires initial setup).
* Configurable check interval.

## Prerequisites

* Python 3.6+
* `pip` (Python package installer)
* A Google Account (for sending notifications via Gmail API)

## Installation

1.  **Clone the Repository:**
    ```bash
    git clone https://github.com/Brendan-Hillis/nj-dmv-real-id-appointment-checker
    cd nj-dmv-real-id-appointment-checker
    ```

2.  **Install Required Libraries:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

1.  **Set up Google Cloud Project & Gmail API:**
    * Go to the [Google Cloud Console](https://console.cloud.google.com/).
    * Create a new project (or select an existing one).
    * Enable the **Gmail API** for your project (APIs & Services > Library).
    * Go to APIs & Services > Credentials.
    * Click "+ CREATE CREDENTIALS" > "OAuth client ID".
    * Configure the OAuth consent screen if you haven't already (User Type: External is usually fine for personal use). Add your email as a test user.
    * Choose "Desktop app" as the Application type.
    * Give it a name (e.g., "DMV Checker Script").
    * Click "Create".
    * Click "DOWNLOAD JSON" to download the credentials file. Rename this file to `credentials.json`.
    * **Place the `credentials.json` file in the same directory as the Python script.**

2.  **Edit the Script (`nj_dmv_real_id_appointment_checker.py`):**
    * Open the Python script file (e.g., `nj_dmv_real_id_appointment_checker.py`).
    * **Mandatory:**
        * Change `EMAIL_ADDRESS_TO_SEND_MESSAGE_TO` to the email address where you want to receive notifications.
        * Change `NEED_BY_DATE_STR` to the latest date you need an appointment by (format `MM/DD/YYYY`).
    * **Optional:**
        * Adjust `CHECK_INTERVAL_SECONDS` if desired (default is 60 seconds; consider increasing this).
        * If checking for an appointment type other than Real ID, you might need to change the path appended to `DMV_URL` in the main loop (currently `f"{DMV_URL}/12"`). Find the correct path by navigating the NJ MVC website.

## Running the Script

1.  **Initial Authorization:**
    * Open a terminal or command prompt.
    * Navigate to the directory containing the script and `credentials.json`.
    * Run the script:
        ```bash
        python nj_dmv_real_id_appointment_checker.py
        ```
    * The first time you run it, the script will print messages about authentication.
    * A browser window should open, asking you to log in to your Google Account and grant the script permission to send emails.
    * **Grant permission.**
    * After successful authorization, the script will create a `token.json` file in the same directory. This file stores your authorization so you don't have to log in every time.
    * The script will then start its checking loop.

2.  **Subsequent Runs:**
    * Simply run the script again:
        ```bash
        python nj_dmv_real_id_appointment_checker.py
        ```
    * It should now use the `token.json` file to authenticate automatically (unless the token expires or is invalidated, in which case it might try to refresh or ask for authorization again).

3.  **Stopping the Script:**
    * Press `Ctrl+C` in the terminal where the script is running.

## Website Scraping & Potential Issues

The core logic for finding appointments is in the `check_appointments_by_location_and_date` function. This function parses the HTML of the NJ MVC website.

**IMPORTANT:** If the NJ MVC website changes its design or HTML structure, the script's ability to find appointment information (the scraping part) will likely break. If the script stops working or reporting appointments correctly, you may need to:

1.  Manually visit the `DMV_URL` in your browser.
2.  Use your browser's Developer Tools (usually by right-clicking and selecting "Inspect" or "Inspect Element").
3.  Examine the HTML structure around the appointment dates and location names.
4.  Update the `find_all`, `find`, `.get_text()`, IDs (`dateText12412`), and class names (`locationCardContainer`, `AppointcardHeader`) used within the `check_appointments_by_location_and_date` function in the Python script to match the new website structure.

## License

Consider adding a license file (e.g., `LICENSE`). The [MIT License](https://opensource.org/licenses/MIT) is a common and permissive choice for open-source projects.

