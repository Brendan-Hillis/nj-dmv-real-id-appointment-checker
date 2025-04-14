# Required Libraries
import requests # For making HTTP requests to the DMV website
from bs4 import BeautifulSoup # For parsing HTML content
import time # For pausing execution (e.g., between checks)
import base64 # For encoding email messages for the Gmail API
from email.message import EmailMessage # For constructing email messages
import os.path # For checking if files exist (e.g., token.json)
import google.auth.transport.requests # Google Auth libraries for handling API authentication
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build # For interacting with Google APIs (Gmail)
from googleapiclient.errors import HttpError # For handling API errors
import datetime # For handling dates and times

# --- User Configuration ---
# ==============================================================================
# === MANDATORY SETTINGS =======================================================
# ==============================================================================

# The base URL for the NJ MVC Appointment Wizard.
# The script will append specific paths (like '/12' for Real ID) as needed.
DMV_URL = 'https://telegov.njportal.com/njmvc/AppointmentWizard'

# Email address where appointment notifications will be sent.
EMAIL_ADDRESS_TO_SEND_MESSAGE_TO = 'YOUR_EMAIL_ADDRESS_HERE' # <--- CHANGE THIS TO YOUR EMAIL

# The latest date by which you need an appointment (Format: MM/DD/YYYY).
# The script will only notify you about appointments on or before this date.
NEED_BY_DATE_STR = '05/09/2025' # <--- CHANGE THIS TO YOUR DESIRED DATE

# ==============================================================================
# === OPTIONAL SETTINGS ========================================================
# ==============================================================================

# How often (in seconds) the script should check the DMV website.
# Be mindful of the website's terms of service; checking too frequently
# might lead to your IP being blocked. 60 seconds is frequent.
# Consider increasing this to 300 (5 minutes) or more.
CHECK_INTERVAL_SECONDS = 60

# User-Agent string to mimic a web browser. Helps avoid being blocked by simple anti-bot measures.
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'

# --- Gmail API Configuration (Do Not Change These Directly) ---
# Scope defines the level of access needed for the Gmail API.
# 'gmail.send' allows the script to send emails on your behalf.
SCOPES = ['https://www.googleapis.com/auth/gmail.send']
# Default filename for the credentials file downloaded from Google Cloud Console.
# Must be in the same directory as the script.
CREDENTIALS_FILE = 'credentials.json'
# Default filename where the script stores the authorization token after successful login.
# This avoids needing to re-authorize every time the script runs.
TOKEN_FILE = 'token.json'

# --- Functions ---

def get_gmail_service():
    """
    Authenticates with the Gmail API using OAuth 2.0 credentials.

    This function handles the OAuth 2.0 flow:
    1. Tries to load existing credentials from `TOKEN_FILE`.
    2. If credentials exist but are expired, it attempts to refresh them using the refresh token.
    3. If no valid credentials exist, it initiates the OAuth 2.0 flow using `CREDENTIALS_FILE`:
       - Prompts the user to authorize the application via a browser window.
       - Saves the new credentials (including access and refresh tokens) to `TOKEN_FILE`.
    4. Builds and returns an authorized Gmail API service object.

    Returns:
        googleapiclient.discovery.Resource: An authorized Gmail API service instance
                                            if authentication is successful, otherwise None.
    """
    creds = None
    # Check if the token file exists (stores previously granted authorization)
    if os.path.exists(TOKEN_FILE):
        try:
            # Load credentials from the token file
            creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
            print(f"Loaded credentials from {TOKEN_FILE}")
        except Exception as e:
            print(f"Error loading credentials from {TOKEN_FILE}: {e}")
            print("Will attempt to re-authenticate.")
            creds = None # Ensure re-authentication if loading fails

    # If credentials are not loaded or not valid, initiate authentication
    if not creds or not creds.valid:
        # If credentials exist but are expired AND have a refresh token
        if creds and creds.expired and creds.refresh_token:
            try:
                print("Credentials expired, attempting to refresh...")
                # Request a token refresh
                creds.refresh(google.auth.transport.requests.Request())
                print("Credentials refreshed successfully.")
                # Save the refreshed credentials back to the token file
                with open(TOKEN_FILE, 'w') as token:
                    token.write(creds.to_json())
                print(f"Refreshed credentials saved to {TOKEN_FILE}")
            except Exception as e:
                print(f"Error refreshing credentials: {e}")
                print("Proceeding with full authentication flow.")
                creds = None # Force re-authentication if refresh fails
        else:
            # --- Initiate full OAuth 2.0 flow ---
            # Check if the credentials file from Google Cloud Console exists
            if not os.path.exists(CREDENTIALS_FILE):
                print(f"FATAL ERROR: Credentials file '{CREDENTIALS_FILE}' not found.")
                print("Please download it from your Google Cloud Console project")
                print("and place it in the same directory as this script.")
                return None # Cannot proceed without credentials file

            try:
                print(f"Credentials not found or invalid in {TOKEN_FILE}.")
                print("Starting authentication flow...")
                print("A browser window may open asking you to log in and grant permissions.")
                # Create the OAuth flow from the client secrets file
                flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
                # Run the flow, opening a local server to capture the authorization code
                creds = flow.run_local_server(port=0)
                print("Authentication successful.")
                # Save the newly obtained credentials to the token file for future use
                with open(TOKEN_FILE, 'w') as token:
                    token.write(creds.to_json())
                print(f"Credentials saved to {TOKEN_FILE}")
            except FileNotFoundError:
                 # This case should be caught by the os.path.exists check above, but included for safety
                 print(f"ERROR: {CREDENTIALS_FILE} not found during authentication flow.")
                 return None
            except Exception as e:
                print(f"An error occurred during the authentication flow: {e}")
                return None

    # If authentication (or refresh) was successful, build the Gmail API service
    try:
        service = build('gmail', 'v1', credentials=creds)
        print("Gmail API service built successfully.")
        return service
    except Exception as e:
        print(f"Failed to build Gmail service: {e}")
        return None


def check_appointments_by_location_and_date(target_date_str, url):
    """
    Checks a specific NJ MVC appointment page for available slots
    at various locations, filtering by a target date.

    Args:
        target_date_str (str): The latest acceptable appointment date in 'MM/DD/YYYY' format.
        url (str): The full URL of the specific appointment type page to check
                   (e.g., DMV_URL + '/12' for Real ID).

    Returns:
        list: A list of dictionaries, where each dictionary represents an available
              appointment slot at a location on or before the target date.
              Returns an empty list if no suitable appointments are found.
              Returns None if an error occurs during fetching or parsing.

    Note:
        This function relies heavily on the specific HTML structure of the NJ MVC website.
        If the website layout changes, **this function will likely break** and need updating.
        The HTML parsing logic (finding 'div' with class 'locationCardContainer',
        'dateText12412', 'AppointcardHeader', etc.) is specific to the observed
        structure at the time of writing.
    """
    headers = {'User-Agent': USER_AGENT}
    available_appointments = []
    print(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking URL for appointments: {url}")

    try:
        # Convert the target date string to a date object for comparison
        target_date = datetime.datetime.strptime(target_date_str, '%m/%d/%Y').date()
        print(f"Looking for appointments on or before: {target_date.strftime('%m/%d/%Y')}")

        # Fetch the webpage content
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status() # Raise an error for bad HTTP status codes (4xx, 5xx)
        soup = BeautifulSoup(response.content, 'html.parser')

        # --- Web Scraping Logic ---
        # Find all containers that seem to hold location appointment info
        location_cards = soup.find_all('div', class_='locationCardContainer')
        if not location_cards:
            print("Could not find any 'locationCardContainer' divs. Website structure may have changed.")
            return None # Indicate potential issue

        print(f"Found {len(location_cards)} potential location cards.")

        for card in location_cards:
            # Attempt to find the specific elements holding date and location info
            # These IDs and classes are specific to the website's structure and might change!
            date_text_div = card.find('div', id='dateText12412') # Specific ID observed
            location_header = card.find('span', class_='AppointcardHeader')

            if date_text_div and location_header:
                location_name = location_header.get_text(strip=True).split('<br>')[0].strip()
                appointment_info = date_text_div.get_text(strip=True)

                # Check if the location explicitly states no appointments
                if "No Appointments Available" not in appointment_info:
                    appointment_date = None
                    appointment_time_str = 'N/A'

                    # Try to parse the date if "Next Available:" is present
                    if "Next Available:" in appointment_info:
                        # Extract the date part (assuming format like "MM/DD/YYYY HH:MM AM/PM")
                        parts = appointment_info.split("Next Available:")[1].strip().split()
                        if parts:
                            date_part = parts[0].strip()
                            try:
                                appointment_date = datetime.datetime.strptime(date_part, '%m/%d/%Y').date()
                                # Try to extract time if available
                                if len(parts) >= 3 and ':' in parts[-2]:
                                     appointment_time_str = f"{parts[-2]} {parts[-1]}"
                            except ValueError:
                                print(f"Warning: Could not parse date '{date_part}' for location '{location_name}'. Info: '{appointment_info}'")
                                appointment_date = None # Could not parse
                    else:
                        # Handle cases where it just says "X Appointments Available"
                        # We can't know the date, so we assume it *might* be suitable
                        # and mark it as ASAP. User needs to verify manually.
                        print(f"Info for '{location_name}' doesn't specify 'Next Available'. Treating as potentially available soon. Info: '{appointment_info}'")
                        appointment_date = target_date # Assume it meets the criteria for notification purposes

                    # If we have a valid date, check if it meets the user's requirement
                    if appointment_date and appointment_date <= target_date:
                        print(f"  Found potential appointment at '{location_name}' on {appointment_date.strftime('%m/%d/%Y')}")
                        available_appointments.append({
                            'location': location_name,
                            'details': appointment_info,
                            'date': appointment_date.strftime('%m/%d/%Y'),
                            'time': appointment_time_str
                        })
                    elif appointment_date:
                         print(f"  Appointment found at '{location_name}' on {appointment_date.strftime('%m/%d/%Y')} (after target date).")

            else:
                # This might happen if a card has a different structure
                print("Warning: Skipping a location card - could not find expected date/header elements.")
        # --- End Web Scraping Logic ---

        if not available_appointments:
            print(f"Result: No appointments found on or before {target_date.strftime('%m/%d/%Y')}.")

        return available_appointments # Return list (empty if none found)

    except requests.exceptions.RequestException as e:
        print(f"ERROR: Could not connect to the website at {url}. Error: {e}")
        return None
    except ValueError as e:
        print(f"ERROR: Could not parse target date string '{target_date_str}'. Ensure format is MM/DD/YYYY. Error: {e}")
        return None
    except Exception as e:
        # Catch any other unexpected errors during parsing or processing
        print(f"ERROR: An unexpected error occurred while checking appointments: {e}")
        import traceback
        traceback.print_exc() # Print detailed traceback for debugging
        return None

def check_real_id_availability_findall(url):
    """
    (UNUSED in current main loop)
    Attempts to find the specific 'REAL ID' appointment count on the main wizard page.

    Args:
        url (str): The URL of the main NJ MVC Appointment Wizard page.

    Returns:
        str: The text indicating appointment availability (e.g., "X Appointments Available")
             if found, otherwise None.

    Note:
        This function also relies heavily on specific HTML structure (finding spans
        with text 'REAL ID', class 'text-black cardButtonCount') and is prone to breaking
        if the website changes.
    """
    headers = {'User-Agent': USER_AGENT}
    print(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] Checking main page for REAL ID count: {url}")
    try:
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')

        # Find the span element containing the exact text 'REAL ID'
        real_id_span = soup.find('span', string='REAL ID')

        if real_id_span:
            # Navigate to the parent container (adjust based on actual structure if needed)
            # This assumes the count is within the same logical block as the "REAL ID" text.
            # Inspect the HTML carefully to find the correct parent/sibling relationship.
            parent_container = real_id_span.find_parent('div') # Example: Adjust as needed

            if parent_container:
                # Find the specific span holding the appointment count within that container
                # The class 'text-black cardButtonCount' was observed previously.
                count_span = parent_container.find('span', class_='text-black cardButtonCount')

                if count_span:
                    appointment_text = count_span.get_text(strip=True)
                    print(f"  Found REAL ID Appointment Count: '{appointment_text}'")
                    return appointment_text
                else:
                    print("  Could not find the appointment count span (e.g., class 'text-black cardButtonCount') within the REAL ID container.")
                    return None
            else:
                print("  Could not find a suitable parent container for the 'REAL ID' span.")
                return None
        else:
            print("  Could not find the span element with the exact text 'REAL ID'.")
            return None

    except requests.exceptions.RequestException as e:
        print(f"ERROR: Could not connect to the website at {url}. Error: {e}")
        return None
    except Exception as e:
        print(f"ERROR: An unexpected error occurred while checking REAL ID count: {e}")
        return None

def send_notification(message_body):
    """
    Sends an email notification using the authenticated Gmail API service.

    Args:
        message_body (str): The plain text content of the email message.
    """
    print("-" * 20)
    print(f"Attempting to send notification via Gmail API to {EMAIL_ADDRESS_TO_SEND_MESSAGE_TO}")
    # print(f"Message Body:\n{message_body}") # Uncomment for debugging message content
    print("-" * 20)

    if not EMAIL_ADDRESS_TO_SEND_MESSAGE_TO or '@' not in EMAIL_ADDRESS_TO_SEND_MESSAGE_TO:
         print("ERROR: Notification email address is not configured correctly in EMAIL_ADDRESS_TO_SEND_MESSAGE_TO.")
         return

    try:
        # Get the authorized Gmail API service instance
        service = get_gmail_service()
        # If authentication failed, service will be None
        if not service:
            print("ERROR: Failed to get authorized Gmail service. Cannot send notification.")
            return

        # Create the email message object using email.message library
        message = EmailMessage()
        message.set_content(message_body) # Set the email body
        message['To'] = EMAIL_ADDRESS_TO_SEND_MESSAGE_TO # Set the recipient
        # message['From'] = 'your_sending_email@gmail.com' # Optional: Set sender if needed (defaults to authenticated user)
        message['Subject'] = 'NJ MVC Appointment Alert!' # Set the email subject

        # Encode the message object into base64url format required by Gmail API
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        # Prepare the body for the API request
        create_message = {'raw': encoded_message}

        # Use the Gmail API's users().messages().send() method to send the email
        # 'userId="me"' refers to the authenticated user's mailbox.
        send_message = service.users().messages().send(userId='me', body=create_message).execute()
        print(f"Notification sent successfully via Gmail API. Message ID: {send_message.get('id')}")

    except HttpError as error:
        # Handle errors specifically from the Google API
        print(f'ERROR: An HTTP error occurred while sending notification: {error}')
        # You might want to add more specific error handling here based on status codes
    except Exception as e:
        # Handle any other unexpected errors during the sending process
        print(f"ERROR: An unexpected error occurred during notification sending: {e}")
        import traceback
        traceback.print_exc()


# --- Main Execution Loop ---
if __name__ == "__main__":
    print("==================================================")
    print(" NJ MVC Appointment Checker (using Gmail API)")
    print("==================================================")
    print(f"Checking for appointments on or before: {NEED_BY_DATE_STR}")
    print(f"Sending notifications to: {EMAIL_ADDRESS_TO_SEND_MESSAGE_TO}")
    print(f"Check Interval: {CHECK_INTERVAL_SECONDS} seconds")
    print("--------------------------------------------------")


    # --- Initial Authentication Check ---
    # Try to authenticate with Gmail API right at the start.
    # This ensures the user completes the OAuth flow immediately if needed,
    # rather than waiting for the first notification attempt.
    print("Performing initial check for Gmail API authentication...")
    initial_service = get_gmail_service()
    if not initial_service:
        print("--- FATAL ERROR ---")
        print("Failed to authenticate with Gmail API. Cannot proceed.")
        print(f"Ensure '{CREDENTIALS_FILE}' is present and valid.")
        print("If running for the first time, complete the authorization")
        print("process when prompted (check console output/browser).")
        print("Exiting.")
        exit(1) # Exit with an error code if authentication fails
    else:
        print("Initial Gmail API authentication successful.")
        # We don't need to keep the service object here, it will be fetched again by send_notification
        del initial_service

    print("--------------------------------------------------")
    print("Starting the main checking loop... Press Ctrl+C to stop.")
    print("--------------------------------------------------")

    # Optional: Send a test notification on startup
    # print("Sending startup test notification...")
    # send_notification('NJ MVC Appointment Checker script has started successfully.')
    # print("--------------------------------------------------")


    # --- Continuous Checking Loop ---
    while True:
        try:
            current_time_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n===== Loop Start: {current_time_str} =====")

            # Construct the specific URL for Real ID appointments (typically ID 12)
            # Modify '/12' if checking for a different appointment type
            real_id_url = f"{DMV_URL}/12"

            # Check for available appointments at different locations for the specific type
            available_appointments = check_appointments_by_location_and_date(NEED_BY_DATE_STR, real_id_url)

            # If the check function returned a list (even if empty)
            if isinstance(available_appointments, list):
                if available_appointments:
                    # --- Appointments Found! ---
                    print(f"\n*** SUCCESS: Found {len(available_appointments)} appointments matching criteria! ***")
                    # Prepare the notification message
                    appointments_message_lines = [
                        f"NJ MVC Appointment Alert!",
                        f"Found appointments on or before {NEED_BY_DATE_STR} at:",
                        f"Checked URL: {real_id_url}",
                        f"Checked Time: {current_time_str}",
                        "--------------------"
                    ]
                    for appointment in available_appointments:
                        appointments_message_lines.append(f"- Location: {appointment['location']}")
                        appointments_message_lines.append(f"  Details: {appointment['details']}")
                        appointments_message_lines.append(f"  Date: {appointment['date']}")
                        if appointment['time'] != 'N/A':
                            appointments_message_lines.append(f"  Time: {appointment['time']}")
                        appointments_message_lines.append("--------------------")

                    appointments_message = "\n".join(appointments_message_lines)
                    print(appointments_message) # Print to console as well

                    # Send the notification email
                    send_notification(appointments_message)

                    # Optional: Exit after finding an appointment
                    # print("\nFound appointments. Exiting script as requested.")
                    # break # Uncomment this line to stop the script after the first notification

                else:
                    # No appointments matching criteria were found in this check
                    print(f"Result: No suitable appointments found during this check.")

            else:
                # The check function returned None, indicating an error occurred
                print("Result: The appointment check failed (returned None). Check logs for errors.")

            # --- Wait before the next check ---
            print(f"\n===== Loop End: Waiting for {CHECK_INTERVAL_SECONDS} seconds... =====")
            time.sleep(CHECK_INTERVAL_SECONDS)


        except KeyboardInterrupt:
            # Allow the user to stop the script gracefully with Ctrl+C
            print("\n--------------------------------------------------")
            print("KeyboardInterrupt detected. Stopping the checker.")
            print("--------------------------------------------------")
            break # Exit the while loop
        except Exception as e:
            # Catch any other unexpected errors in the main loop
            print("\n!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            print(f"FATAL ERROR in main loop: {e}")
            import traceback
            traceback.print_exc() # Print detailed traceback
            print("!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!!")
            # Wait longer before retrying after a major error
            wait_time = CHECK_INTERVAL_SECONDS * 2
            print(f"Waiting for {wait_time} seconds before retrying...")
            time.sleep(wait_time)

