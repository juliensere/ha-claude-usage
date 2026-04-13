"""Config flow for Claude Usage integration."""
from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
import aiohttp

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.exceptions import ConfigEntryAuthFailed

from .const import CONF_CF_CLEARANCE, CONF_ORG_ID, CONF_SESSION_KEY, DOMAIN
from .coordinator import validate_credentials

_LOGGER = logging.getLogger(__name__)

STEP_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SESSION_KEY): str,
        vol.Required(CONF_CF_CLEARANCE): str,
        vol.Required(CONF_ORG_ID): str,
    }
)

REAUTH_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_SESSION_KEY): str,
        vol.Required(CONF_CF_CLEARANCE): str,
    }
)


async def _test_credentials(
    session_key: str, cf_clearance: str, org_id: str
) -> str | None:
    """Return an error key string, or None on success."""
    try:
        await validate_credentials(session_key, cf_clearance, org_id)
        return None
    except ConfigEntryAuthFailed as err:
        return str(err)
    except aiohttp.ClientError:
        return "cannot_connect"
    except Exception:  # noqa: BLE001
        return "unknown"


class ClaudeUsageConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial setup and re-authentication flows."""

    VERSION = 1

    # ── Initial setup ──────────────────────────────────────────────────────────

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}

        if user_input is not None:
            error = await _test_credentials(
                user_input[CONF_SESSION_KEY],
                user_input[CONF_CF_CLEARANCE],
                user_input[CONF_ORG_ID],
            )
            if error is None:
                await self.async_set_unique_id(user_input[CONF_ORG_ID])
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Claude Usage", data=user_input)
            errors["base"] = error

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_SCHEMA,
            errors=errors,
        )

    # ── Re-authentication (triggered by ConfigEntryAuthFailed) ─────────────────

    async def async_step_reauth(
        self, entry_data: dict[str, Any]
    ) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        reauth_entry: ConfigEntry = self._get_reauth_entry()

        if user_input is not None:
            error = await _test_credentials(
                user_input[CONF_SESSION_KEY],
                user_input[CONF_CF_CLEARANCE],
                reauth_entry.data[CONF_ORG_ID],
            )
            if error is None:
                return self.async_update_reload_and_abort(
                    reauth_entry,
                    data_updates=user_input,
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=REAUTH_SCHEMA,
            errors=errors,
            description_placeholders={
                "org_id": reauth_entry.data.get(CONF_ORG_ID, "")
            },
        )

    # ── Reconfigure (manual update via the integration page) ──────────────────

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        entry: ConfigEntry = self._get_reconfigure_entry()

        if user_input is not None:
            error = await _test_credentials(
                user_input[CONF_SESSION_KEY],
                user_input[CONF_CF_CLEARANCE],
                user_input[CONF_ORG_ID],
            )
            if error is None:
                return self.async_update_reload_and_abort(
                    entry,
                    data_updates=user_input,
                )
            errors["base"] = error

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_SESSION_KEY,
                        default=entry.data.get(CONF_SESSION_KEY, ""),
                    ): str,
                    vol.Required(
                        CONF_CF_CLEARANCE,
                        default=entry.data.get(CONF_CF_CLEARANCE, ""),
                    ): str,
                    vol.Required(
                        CONF_ORG_ID,
                        default=entry.data.get(CONF_ORG_ID, ""),
                    ): str,
                }
            ),
            errors=errors,
        )
