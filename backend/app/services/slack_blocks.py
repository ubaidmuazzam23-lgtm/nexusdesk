# File: backend/app/services/slack_blocks.py
# Block Kit helpers — replace hardcoded text questions with interactive buttons
# Only used by Slack; web chat uses plain text replies unchanged.

from typing import Optional


def _btn(text: str, value: str, style: str = "default") -> dict:
    """Single button element."""
    b = {
        "type":  "button",
        "text":  {"type": "plain_text", "text": text, "emoji": True},
        "value": value,
    }
    if style in ("primary", "danger"):
        b["style"] = style
    return b


def _blocks(question: str, buttons: list, block_id: str) -> list:
    """Section text + actions row."""
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*{question}*"},
        },
        {
            "type":     "actions",
            "block_id": block_id,
            "elements": buttons,
        },
    ]


# ─────────────────────────────────────────────────────────────────────────────
# One function per flow question
# ─────────────────────────────────────────────────────────────────────────────

def broken_or_consult() -> dict:
    return {
        "text":   "Is something actively broken right now, or do you have a question or need a consult from the network team?",
        "blocks": _blocks(
            "Is something actively broken right now, or do you have a question or need a consult from the network team?",
            [
                _btn("🚨  Something is Broken",   "broken",  "primary"),
                _btn("💬  Question / Consult",     "consult"),
            ],
            "block_broken_or_consult",
        ),
    }


def customer_impacting() -> dict:
    return {
        "text":   "Is this customer impacting? Are end users or customers unable to access services because of this?",
        "blocks": _blocks(
            "Is this customer impacting? Are end users or customers unable to access services because of this?",
            [
                _btn("✅  Yes, customers are affected",  "yes", "primary"),
                _btn("➖  No, internal only",            "no"),
            ],
            "block_customer_impacting",
        ),
    }


def multi_customer() -> dict:
    return {
        "text":   "Are more than one customer or user impacted by this?",
        "blocks": _blocks(
            "Are more than one customer or user impacted by this?",
            [
                _btn("👥  Yes — multiple users",   "yes", "primary"),
                _btn("👤  No — single user",       "no"),
            ],
            "block_multi_customer",
        ),
    }


def hard_deadline() -> dict:
    return {
        "text":   "Is there a hard deadline on this request?",
        "blocks": _blocks(
            "Is there a hard deadline on this request?",
            [
                _btn("📌  Yes, there is a deadline",  "deadline_yes", "primary"),
                _btn("➖  No fixed deadline",          "deadline_no"),
            ],
            "block_hard_deadline",
        ),
    }


def help_today() -> dict:
    return {
        "text":   "Do you need help with this today?",
        "blocks": _blocks(
            "Do you need help with this today?",
            [
                _btn("⚡  Yes, needed today",    "yes", "primary"),
                _btn("📅  Not urgently",          "no"),
            ],
            "block_help_today",
        ),
    }


def next_sprint() -> dict:
    return {
        "text":   "When should the network team pick this up?",
        "blocks": _blocks(
            "When should the network team pick this up?",
            [
                _btn("🔂  Next Sprint",              "next sprint"),
                _btn("🚀  Next Release",             "next release"),
                _btn("🔂  Next Sprint & Release",    "next sprint and release"),
                _btn("🕐  No Rush",                  "no rush"),
            ],
            "block_next_sprint",
        ),
    }


def mid_check_no_runbook() -> dict:
    return {
        "text":   "I have tried 3 troubleshooting steps so far and the issue is still not resolved. What would you like to do?",
        "blocks": _blocks(
            "I have tried 3 troubleshooting steps and the issue is still not resolved. What would you like to do?",
            [
                _btn("🔁  Continue Troubleshooting",   "continue"),
                _btn("🎫  Raise a Support Ticket",      "escalate", "danger"),
            ],
            "block_mid_check",
        ),
    }


def mid_check_runbook() -> dict:
    return {
        "text":   "I have gone through several troubleshooting steps and the issue is still not resolved. What would you like to do?",
        "blocks": _blocks(
            "I have gone through several troubleshooting steps and the issue is still not resolved. What would you like to do?",
            [
                _btn("🔁  Continue Troubleshooting",   "continue"),
                _btn("🎫  Raise a Support Ticket",      "escalate", "danger"),
            ],
            "block_mid_check",
        ),
    }


def ticket_confirm() -> dict:
    return {
        "text":   "I have exhausted all troubleshooting steps. Would you like me to raise a support ticket and escalate this to the network engineering team?",
        "blocks": _blocks(
            "I have exhausted all troubleshooting steps. Would you like me to raise a support ticket and escalate this to the network engineering team?",
            [
                _btn("🎫  Yes, Raise a Ticket", "yes", "primary"),
                _btn("❌  No",                  "no"),
            ],
            "block_ticket_confirm",
        ),
    }


def screenshot_confirm() -> dict:
    return {
        "text":   "Is this the issue you are facing?",
        "blocks": _blocks(
            "Is this the issue you are facing?",
            [
                _btn("✅  Yes, that's the issue",       "yes", "primary"),
                _btn("✏️  No, let me describe it",      "no"),
            ],
            "block_screenshot_confirm",
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# block_id → flow step mapping (used by action handler to route button clicks)
# ─────────────────────────────────────────────────────────────────────────────

BLOCK_TO_FLOW = {
    "block_broken_or_consult":  "waiting_broken",
    "block_customer_impacting": "waiting_impacting",
    "block_multi_customer":     "waiting_multi_customer",
    "block_hard_deadline":      "waiting_deadline",
    "block_help_today":         "waiting_help_today",
    "block_next_sprint":        "waiting_next_sprint",
    "block_mid_check":          "mid_check",
    "block_ticket_confirm":     "ticket_confirm",
    "block_screenshot_confirm": "waiting_screenshot_confirm",
}