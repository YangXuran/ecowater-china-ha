"""Config flow for Ecowater China."""
import voluptuous as vol
from homeassistant import config_entries
import homeassistant.helpers.config_validation as cv

from .const import DOMAIN, CONF_CUSTOMER_ID, CONF_PHONE_NUMBER


class EcowaterConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle config flow."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            return self.async_create_entry(
                title="Ecowater V80ECM",
                data=user_input,
            )

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_PHONE_NUMBER): str,
                vol.Required(CONF_CUSTOMER_ID): str,
            }),
            errors=errors,
        )
