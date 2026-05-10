"""
automation/messaging.py — WhatsApp & Instagram message automation
Uses Selenium for web-based automation + accessibility fallback
"""
import time
import pyautogui
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from typing import Optional
import os


# ══════════════════════════════════════════════
#  BASE AUTOMATION CLASS
# ══════════════════════════════════════════════
class BrowserAutomation:
    def __init__(self, headless: bool = False):
        self.driver: Optional[webdriver.Chrome] = None
        self.headless = headless

    def start(self):
        options = Options()
        if self.headless:
            options.add_argument("--headless=new")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)

        # Save profile so you stay logged in
        profile_dir = os.path.expanduser("~/.jarvis_browser_profile")
        options.add_argument(f"--user-data-dir={profile_dir}")

        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        print("[Browser] Chrome started")

    def quit(self):
        if self.driver:
            self.driver.quit()
            self.driver = None

    def wait(self, by, selector, timeout=15):
        return WebDriverWait(self.driver, timeout).until(
            EC.presence_of_element_located((by, selector))
        )

    def wait_clickable(self, by, selector, timeout=15):
        return WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable((by, selector))
        )


# ══════════════════════════════════════════════
#  WHATSAPP WEB AUTOMATION
# ══════════════════════════════════════════════
class WhatsAppAutomation(BrowserAutomation):
    WHATSAPP_URL = "https://web.whatsapp.com"

    def open(self):
        if not self.driver:
            self.start()
        self.driver.get(self.WHATSAPP_URL)
        print("[WhatsApp] Waiting for page load...")
        try:
            # Wait for the search box (means logged in)
            self.wait(By.XPATH, '//div[@contenteditable="true"][@data-tab="3"]', timeout=30)
            print("[WhatsApp] Logged in")
            return True
        except Exception:
            print("[WhatsApp] QR scan required - please scan the code in the browser window")
            # Wait for QR scan
            self.wait(By.XPATH, '//div[@contenteditable="true"][@data-tab="3"]', timeout=120)
            print("[WhatsApp] Logged in after QR scan")
            return True

    def send_message(self, contact_name: str, message: str) -> bool:
        """Send a WhatsApp message to a contact by name."""
        try:
            # Click search bar
            search = self.wait_clickable(By.XPATH, '//div[@contenteditable="true"][@data-tab="3"]')
            search.click()
            search.send_keys(contact_name)
            time.sleep(1.5)

            # Click first result
            first_result = self.wait_clickable(By.XPATH, f'//span[@title="{contact_name}"]')
            first_result.click()
            time.sleep(1)

            # Find message input and send
            msg_box = self.wait_clickable(By.XPATH, '//div[@contenteditable="true"][@data-tab="10"]')
            msg_box.click()
            msg_box.send_keys(message)
            msg_box.send_keys(Keys.ENTER)

            print(f"[WhatsApp] Message sent to {contact_name}")
            return True

        except Exception as e:
            print(f"[WhatsApp] Failed to send message: {e}")
            return False

    def send_to_phone(self, phone_number: str, message: str) -> bool:
        """Send message to a phone number directly."""
        url = f"https://web.whatsapp.com/send?phone={phone_number}&text={message}"
        self.driver.get(url)
        try:
            send_btn = self.wait_clickable(By.XPATH, '//button[@data-tab="11"]', timeout=15)
            send_btn.click()
            time.sleep(1)
            print(f"[WhatsApp] Message sent to +{phone_number}")
            return True
        except Exception as e:
            print(f"[WhatsApp] Failed: {e}")
            return False

    def get_unread_messages(self) -> list:
        """Get list of contacts with unread messages."""
        try:
            unread_spans = self.driver.find_elements(By.XPATH, '//span[@data-testid="icon-unread-count"]')
            results = []
            for span in unread_spans:
                try:
                    contact = span.find_element(By.XPATH, '../../..//span[@dir="auto"]')
                    results.append({
                        "contact": contact.text,
                        "count": span.text
                    })
                except Exception as err:
                    import logging
                    logging.getLogger(__name__).error("Exception swallowed: %s", err)
                    raise RuntimeError(f"Exception swallowed: {err}")
            return results
        except Exception:
            return []


# ══════════════════════════════════════════════
#  INSTAGRAM AUTOMATION
# ══════════════════════════════════════════════
class InstagramAutomation(BrowserAutomation):
    INSTAGRAM_URL = "https://www.instagram.com"
    DM_URL        = "https://www.instagram.com/direct/new/"

    def __init__(self, username: str = "", password: str = "", headless: bool = False):
        super().__init__(headless)
        self.username = username
        self.password = password

    def login(self) -> bool:
        if not self.driver:
            self.start()
        self.driver.get(self.INSTAGRAM_URL)
        time.sleep(2)

        try:
            # Check if already logged in
            self.driver.find_element(By.XPATH, '//a[@href="/direct/inbox/"]')
            print("[Instagram] Already logged in")
            return True
        except Exception as err:
            import logging
            logging.getLogger(__name__).error("Exception swallowed: %s", err)
            raise RuntimeError(f"Exception swallowed: {err}")

        if not self.username or not self.password:
            print("[Instagram] No credentials provided. Please log in manually.")
            time.sleep(30)
            return True

        try:
            user_field = self.wait_clickable(By.NAME, "username")
            user_field.send_keys(self.username)

            pass_field = self.wait_clickable(By.NAME, "password")
            pass_field.send_keys(self.password)
            pass_field.send_keys(Keys.ENTER)
            time.sleep(3)

            print("[Instagram] Login attempted")
            return True
        except Exception as e:
            print(f"[Instagram] Login failed: {e}")
            return False

    def send_dm(self, username: str, message: str) -> bool:
        """Send a direct message to a user."""
        try:
            self.driver.get(self.DM_URL)
            time.sleep(2)

            # Search for user
            search_box = self.wait_clickable(By.NAME, "queryBox")
            search_box.send_keys(username)
            time.sleep(1.5)

            # Click user result
            user_result = self.wait_clickable(
                By.XPATH, f'//span[contains(text(), "{username}")]', timeout=8
            )
            user_result.click()
            time.sleep(1)

            # Click Next
            next_btn = self.wait_clickable(By.XPATH, '//button[text()="Next"]')
            next_btn.click()
            time.sleep(1.5)

            # Type message
            msg_box = self.wait_clickable(By.XPATH, '//textarea[@placeholder]')
            msg_box.send_keys(message)
            msg_box.send_keys(Keys.ENTER)
            time.sleep(1)

            print(f"[Instagram] DM sent to @{username}")
            return True

        except Exception as e:
            print(f"[Instagram] Failed to send DM: {e}")
            return False


# ══════════════════════════════════════════════
#  UNIFIED MESSAGING API
# ══════════════════════════════════════════════
class MessagingController:
    def __init__(self):
        self._whatsapp: Optional[WhatsAppAutomation] = None
        self._instagram: Optional[InstagramAutomation] = None

    def get_whatsapp(self) -> WhatsAppAutomation:
        if not self._whatsapp:
            self._whatsapp = WhatsAppAutomation()
            self._whatsapp.open()
        return self._whatsapp

    def get_instagram(self, username: str = "", password: str = "") -> InstagramAutomation:
        if not self._instagram:
            from core.config import INSTAGRAM_USERNAME, INSTAGRAM_PASSWORD
            self._instagram = InstagramAutomation(
                username or INSTAGRAM_USERNAME,
                password or INSTAGRAM_PASSWORD
            )
            self._instagram.login()
        return self._instagram

    def send_whatsapp(self, contact: str, message: str) -> bool:
        return self.get_whatsapp().send_message(contact, message)

    def send_instagram_dm(self, username: str, message: str) -> bool:
        return self.get_instagram().send_dm(username, message)

    def shutdown(self):
        if self._whatsapp:
            self._whatsapp.quit()
        if self._instagram:
            self._instagram.quit()


# Singleton
messaging = MessagingController()
