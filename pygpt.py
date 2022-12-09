import getpass
import json
import uuid
import sys
import optparse
import httpx
import logging
import time


class ChatGPT:
    email = None
    password = None
    session = None
    set_headers = {
        "user-agent": "Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/47.0.2526.111 Safari/537.36"
    }
    access_token = ""
    select_model = ""
    max_tokens = 0
    last_parent = ""
    last_uuid = ""

    def __init__(self, email: str, password: str):
        self.email = email
        self.password = password

    def auth(self):
        logging.info("Starting new session")
        self.session = httpx.Client(follow_redirects=True)
        # self.session.mount('https://chat.openai.com', HTTP20Adapter())
        logging.info("Authenticating as %s", self.email)
        self.session.get(
            "https://chat.openai.com/auth/login",
            headers=self.set_headers
        )

        self.session.get(
            "https://chat.openai.com/api/auth/session",
            headers=self.set_headers
        )

        get_providers = self.session.get(
            "https://chat.openai.com/api/auth/providers",
            headers=self.set_headers
        ).json()
        target = get_providers["auth0"]
        sign_in = target["signinUrl"]
        callback = target["callbackUrl"]
        logging.debug("Got signin url: %s", sign_in)
        get_csrf = self.session.get(
            "https://chat.openai.com/api/auth/csrf",
            headers=self.set_headers
        ).json()
        csrf_token = get_csrf["csrfToken"]
        logging.debug("Got CSRF token: %s", csrf_token)
        do_post_auth = {
            "callbackUrl": "/",
            "csrfToken": csrf_token,
            "json": "true"
        }
        time.sleep(5)
        get_login = self.session.post(
            sign_in,
            headers=self.set_headers,
            params={"prompt": "login"},
            data=do_post_auth
        )
        if get_login.status_code == 429:
            logging.warning("Request limit exceeded, retrying in 60 seconds")
            time.sleep(60)
            return self.auth()
        get_oauth_redirect = get_login.json()["url"]
        logging.debug("Got OAuth redirect: %s", get_oauth_redirect)
        get_login_html = self.session.get(
            get_oauth_redirect,
            headers=self.set_headers
        )
        get_state = get_login_html.url.params['state']

        logging.debug("Sending initial credential: %s", self.email)
        first_payload = {
            "state": get_state,
            "username": self.email,
            "js-available": "true",
            "webauthn-available": "false",
            "is-brave": "false",
            "webauthn-platform-available": "false",
            "action": "default"
        }

        do_post_login = self.session.post(
            "https://auth0.openai.com/u/login/identifier",
            params={"state": get_state},
            headers=self.set_headers,
            data=first_payload
        )
        if do_post_login.status_code == 429:
            logging.warning("Request limit exceeded, retrying in 60 seconds")
            time.sleep(60)
            return self.auth()
        time.sleep(6)

        logging.debug("Sending password")
        second_payload = {
            "state": get_state,
            "username": self.email,
            "password": self.password,
            "action": "default"
        }

        do_post_password = self.session.post(
            "https://auth0.openai.com/u/login/password",
            params={"state": get_state},
            headers=self.set_headers,
            data=second_payload
        )
        if do_post_password.status_code == 429:
            logging.warning("Request limit exceeded, retrying in 60 seconds")
            time.sleep(60)
            return self.auth()
        time.sleep(3)
        return "chat.openai.com" in do_post_password.url.host and "auth/login" not in do_post_password.url.path

    def get_auth_token(self, attempt=0):
        get_token = self.session.get(
            "https://chat.openai.com/api/auth/session",
            headers=self.set_headers
        )
        if get_token.status_code != 200:
            if attempt == 3:
                logging.error("Access token fetch failed 3 times, quitting")
                sys.exit(3)
            attempt += 1
            self.auth()
            return self.get_auth_token(attempt)
        logging.debug("Updated access token")
        self.access_token = get_token.json()["accessToken"]

    def headers_auth(self):
        new_headers = dict(self.set_headers)
        new_headers["authorization"] = f"Bearer {self.access_token}"
        return new_headers

    def headers_query(self, get_event_stream=False):
        new_headers = dict(self.set_headers)
        new_headers["authorization"] = f"Bearer {self.access_token}"
        new_headers["x-openai-assistant-app-id"] = ""
        new_headers["content-type"] = "application/json"
        new_headers["origin"] = "https://chat.openai.com"
        new_headers["referer"] = "https://chat.openai.com/chat"
        if get_event_stream:
            new_headers["Accept"] = "text/event-stream"
        return new_headers

    def get_models(self, custom=None):
        time.sleep(3)
        get_mods = self.session.get(
            "https://chat.openai.com/backend-api/models",
            headers=self.headers_auth()
        )

        for entry in get_mods.json()["models"]:
            if not custom or entry["slug"] == custom:
                self.select_model = entry["slug"]
                self.max_tokens = entry["max_tokens"]
                logging.debug("Selected model %s (max tokens %s)", self.select_model, self.max_tokens)
                return
        if custom:
            logging.warning("Custom model was not found, using default")
            return self.get_models()
        logging.error("No valid models found, quitting")
        sys.exit(3)

    def do_moderations(self, keywords, text_model="text-moderation-playground"):
        get_mods = self.session.post(
            "https://chat.openai.com/backend-api/moderations",
            headers=self.headers_query(),
            json={
                "input": keywords,
                "model": text_model
            }
        )
        if get_mods.status_code != 200:
            logging.warning("Moderation fetch failed, retrying in 5 seconds")
            time.sleep(5)
            return self.do_moderations(keywords, text_model)
        data = get_mods.json()
        if data["blocked"]:
            logging.warning("Keyword search %s was blocked by moderation", keywords)
            return False
        if data["flagged"]:
            logging.warning("Keyword search %s was flagged by moderation", keywords)
        return data["moderation_id"]

    def do_query(self, keywords, do_moderation=True, return_text=False):
        self.get_auth_token()
        self.get_models()
        if len(keywords) > self.max_tokens:
            logging.warning("Cannot process this query, exceeds max tokens %s", self.max_tokens)
            return None
        if do_moderation:
            self.do_moderations(keywords)

        if not self.last_uuid:
            self.last_uuid = str(uuid.uuid4())
        message_uuid = str(uuid.uuid4())
        query_target = {
                "messages": [
                    {
                        "content": {
                            "content_type": "text",
                            "parts": [
                                keywords
                            ]
                        },
                        "role": "user",
                        "id": message_uuid
                    }
                ],
                "action": "new",
                "parent_message_id": self.last_uuid,
                "model": self.select_model
            }
        if self.last_parent:
            query_target["conversation_id"] = self.last_parent

        with self.session.stream(
            "POST",
            "https://chat.openai.com/backend-api/conversation",
            headers=self.headers_query(get_event_stream=True),
            json=query_target,
            timeout=300
        ) as do_query:
            last = "{}"
            for line in [x.strip() for x in do_query.read().decode("utf-8").split("\n")]:
                if not line:
                    continue
                if line == "data: [DONE]":
                    do_query.close()
                    process = last.strip().lstrip("data: ")
                    parsed = json.loads(process)
                    self.last_parent = parsed['conversation_id']
                    self.last_uuid = parsed['message']['id']
                    if return_text:
                        return "".join(parsed['message']['content']['parts'])
                    return parsed['message']
                last = line

    @staticmethod
    def do_cli(email=None, password=None, do_moderation=False):
        print("Starting in CLI mode")
        print("Send 'reset' to discard the current conversation, 'exit' to quit")
        get_email = input("Account email: ") if not email else email
        get_password = getpass.getpass(prompt="Account password: ") if not password else password
        bot = ChatGPT(
            get_email,
            get_password
        )
        if bot.auth():
            logging.info("Authentication successful")
        else:
            logging.error("Authentication failed for account %s", bot.email)
            sys.exit(1)

        while 1:
            do_query = input("Query> ")
            if do_query.strip() == "reset":
                print("Resetting conversation")
                bot.last_parent = None
                continue
            if do_query.strip() == "exit":
                print("Quitting")
                sys.exit(0)
            query_result = bot.do_query(do_query,
                                        do_moderation=do_moderation, return_text=True)
            sys.stdout.write(query_result)
            sys.stdout.flush()
            print("")


if __name__ == "__main__":
    parser = optparse.OptionParser()
    parser.add_option(
        "-u", dest="email", default=None, help="The OpenAI account mail address"
    )
    parser.add_option(
        "-p", dest="password", default=None, help="The OpenAI account password"
    )
    parser.add_option(
        "-q", dest="query", default=None, help="Run this query and exit"
    )
    parser.add_option(
        "-v", dest="verbose", action="store_true", default=None, help="Show verbose information"
    )
    parser.add_option(
        "-m", dest="moderation", action="store_true", default=False, help="Enable moderation requests"
    )
    options, args = parser.parse_args()
    logging.basicConfig(level=logging.INFO if not options.verbose else logging.DEBUG)
    if options.query:
        bot = ChatGPT(
            options.email,
            options.password
        )

        if bot.auth():
            logging.info("Authentication successful")
        else:
            logging.error("Authentication failed for account %s", bot.email)
            sys.exit(1)

        result = bot.do_query(options.query, do_moderation=options.moderation)
        print(result)
    else:
        ChatGPT.do_cli(
            options.email,
            options.password,
            options.moderation
        )
