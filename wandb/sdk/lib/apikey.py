# -*- coding: utf-8 -*-
"""
apikey util.
"""

import getpass
import os
import stat
import sys
import textwrap

import requests
from six.moves import input
import wandb
from wandb.apis import InternalApi
from wandb.errors import term
from wandb.util import isatty


LOGIN_CHOICE_ANON = "Private W&B dashboard, no account required"
LOGIN_CHOICE_NEW = "Create a W&B account"
LOGIN_CHOICE_EXISTS = "Use an existing W&B account"
LOGIN_CHOICE_DRYRUN = "Don't visualize my results"
LOGIN_CHOICE_NOTTY = "Unconfigured"
LOGIN_CHOICES = [
    LOGIN_CHOICE_ANON,
    LOGIN_CHOICE_NEW,
    LOGIN_CHOICE_EXISTS,
    LOGIN_CHOICE_DRYRUN,
]


def _fixup_anon_mode(default):
    # Convert weird anonymode values from legacy settings files
    # into one of our expected values.
    anon_mode = default or "never"
    mapping = {"true": "allow", "false": "never"}
    return mapping.get(anon_mode, anon_mode)


def _prompt_choice():
    try:
        return int(input("%s: Enter your choice: " % term.LOG_STRING)) - 1  # noqa: W503
    except ValueError:
        return -1


def prompt_api_key(  # noqa: C901
    settings,
    api=None,
    input_callback=None,
    browser_callback=None,
    no_offline=False,
    no_create=False,
    local=False,
):
    """Prompt for api key.

    Returns:
        str - if key is configured
        None - if dryrun is selected
        False - if unconfigured (notty)
    """
    input_callback = input_callback or getpass.getpass
    log_string = term.LOG_STRING
    api = api or InternalApi()
    anon_mode = _fixup_anon_mode(settings.anonymous)
    jupyter = settings._jupyter or False
    app_url = api.app_url

    choices = list(LOGIN_CHOICES)
    if anon_mode == "never":
        # Omit LOGIN_CHOICE_ANON as a choice if the env var is set to never
        choices.remove(LOGIN_CHOICE_ANON)
    if jupyter or no_offline:
        choices.remove(LOGIN_CHOICE_DRYRUN)
    if jupyter or no_create:
        choices.remove(LOGIN_CHOICE_NEW)

    if jupyter and "google.colab" in sys.modules:
        log_string = term.LOG_STRING_NOCOLOR
        key = wandb.jupyter.attempt_colab_login(app_url)
        if key is not None:
            write_key(settings, key)
            return key

    if anon_mode == "must":
        result = LOGIN_CHOICE_ANON
    # If we're not in an interactive environment, default to dry-run.
    elif not jupyter and (not isatty(sys.stdout) or not isatty(sys.stdin)):
        result = LOGIN_CHOICE_NOTTY
    elif local:
        result = LOGIN_CHOICE_EXISTS
    elif len(choices) == 1:
        result = choices[0]
    else:
        for i, choice in enumerate(choices):
            wandb.termlog("(%i) %s" % (i + 1, choice))

        idx = -1
        while idx < 0 or idx > len(choices) - 1:
            idx = _prompt_choice()
            if idx < 0 or idx > len(choices) - 1:
                wandb.termwarn("Invalid choice")
        result = choices[idx]
        wandb.termlog("You chose '%s'" % result)

    api_ask = "%s: Paste an API key from your profile and hit enter: " % log_string
    if result == LOGIN_CHOICE_ANON:
        key = api.create_anonymous_api_key()

        write_key(settings, key)
        return key
    elif result == LOGIN_CHOICE_NEW:
        key = browser_callback(signup=True) if browser_callback else None

        if not key:
            wandb.termlog(
                "Create an account here: {}/authorize?signup=true".format(app_url)
            )
            key = input_callback(api_ask).strip()

        write_key(settings, key)
        return key
    elif result == LOGIN_CHOICE_EXISTS:
        key = browser_callback() if browser_callback else None

        if not key:
            wandb.termlog(
                "You can find your API key in your browser here: {}/authorize".format(
                    app_url
                )
            )
            key = input_callback(api_ask).strip()
        write_key(settings, key)
        return key
    elif result == LOGIN_CHOICE_NOTTY:
        # TODO: Needs refactor as this needs to be handled by caller
        return False
    else:
        # Jupyter environments don't have a tty, but we can still try logging in using
        # the browser callback if one is supplied.
        key, anonymous = (
            browser_callback() if jupyter and browser_callback else (None, False)
        )

        write_key(settings, key)
        return key


def write_netrc(host, entity, key):
    """Add our host and key to .netrc"""
    key_prefix, key_suffix = key.split("-", 1) if "-" in key else ("", key)
    if len(key_suffix) != 40:
        wandb.termerror(
            "API-key must be exactly 40 characters long: {} ({} chars)".format(
                key_suffix, len(key_suffix)
            )
        )
        return None
    try:
        normalized_host = host.rstrip("/").split("/")[-1].split(":")[0]
        if normalized_host != "localhost" and "." not in normalized_host:
            wandb.termerror("Host must be a url in the form https://some.address.com")
            return None
        wandb.termlog(
            "Appending key for {} to your netrc file: {}".format(
                normalized_host, os.path.expanduser("~/.netrc")
            )
        )
        machine_line = "machine %s" % normalized_host
        path = os.path.expanduser("~/.netrc")
        orig_lines = None
        try:
            with open(path) as f:
                orig_lines = f.read().strip().split("\n")
        except IOError:
            pass
        with open(path, "w") as f:
            if orig_lines:
                # delete this machine from the file if it's already there.
                skip = 0
                for line in orig_lines:
                    # we fix invalid netrc files with an empty host that we wrote before
                    # verifying host...
                    if line == "machine " or machine_line in line:
                        skip = 2
                    elif skip:
                        skip -= 1
                    else:
                        f.write("%s\n" % line)
            f.write(
                textwrap.dedent(
                    """\
            machine {host}
              login {entity}
              password {key}
            """
                ).format(host=normalized_host, entity=entity, key=key)
            )
        os.chmod(os.path.expanduser("~/.netrc"), stat.S_IRUSR | stat.S_IWUSR)
        return True
    except IOError:
        wandb.termerror("Unable to read ~/.netrc")
        return None


def write_key(settings, key):
    if not key:
        return

    # Normal API keys are 40-character hex strings. Onprem API keys have a
    # variable-length prefix, a dash, then the 40-char string.
    prefix, suffix = key.split("-", 1) if "-" in key else ("", key)

    if len(suffix) == 40:
        write_netrc(settings.base_url, "user", key)
        return
    raise ValueError("API key must be 40 characters long, yours was %s" % len(key))


def api_key(settings=None):
    if not settings:
        settings = wandb.setup().settings
    if settings.api_key:
        return settings.api_key
    if auth := requests.utils.get_netrc_auth(settings.base_url):
        return auth[-1]
    return None
