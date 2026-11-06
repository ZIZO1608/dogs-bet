import os

# Must be set before `app.config` is imported anywhere.
os.environ.setdefault("BOT_TOKEN", "42:TEST")
os.environ.setdefault("ADMIN_IDS", "999")
os.environ.setdefault("REQUIRED_CHANNELS", "@dogs_test")
os.environ.setdefault("SUPPORT_USERNAME", "dogs_support")
