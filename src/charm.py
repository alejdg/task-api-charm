#!/usr/bin/env python3
# Copyright 2024 Alexandre
# See LICENSE file for licensing details.

"""Charm the application."""

import logging

import os
from subprocess import check_call

import yaml

import ops

from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)


class CharmAssistantCharm(ops.CharmBase):
    """Charm the application."""

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.start, self._on_start)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.template_dir = os.path.join(os.getenv("JUJU_CHARM_DIR"), "templates")

    def _on_start(self, event: ops.StartEvent):
        """Handle start event."""
        self.unit.status = ops.ActiveStatus()

    def _on_install(self, event):
        """Handle the install event"""
        self._install_systemd()
        self._reload_systemctl()
        self._enable_service()

    def _install_systemd(self):
        try:
            file_path = "/etc/systemd/system/charm-assistant-api.service"
            self._write_config_file(file_path, self._render_systemd_file())
        except ops.CalledProcessError as e:
            # If the command returns a non-zero return code,
            # put the charm in blocked state
            logger.debug("Setting up Flaks failed with return code %d", e)
            self.unit.status = ops.BlockedStatus("Failed to install packages")

    def _reload_systemctl(self):
        check_call(["sudo", "systemctl", "daemon-reload"])

    def _enable_service(self):
        check_call(["sudo", "systemctl", "start", "assistant-api.service"])
        check_call(["sudo", "systemctl", "enable", "assistant-api.service"])

    def _on_config_changed(self, event):
        self._update_config_file("/etc/charm-assistant-api.yaml")

    def _actions_is_list(self, actions):
        return isinstance(actions, list)

    def _action_is_dict(self, action):
        return isinstance(action, dict)

    def _valid_actions_struct(self, actions):
        for action in actions:
            if not self._action_is_dict(action):
                logger.debug("Action is not a dict")
                return False
            if "name" not in action or "cmd" not in action:
                return False
        return True

    def _valid_actions(self, actions):
        """
        Validates the actions list.

        Args:
            actions (list): The list of actions to validate.

        Returns:
            bool: True, False.
        """
        if not self._actions_is_list(actions):
            return False

        # Each action must be a dictionary and follow our structure
        if not self._valid_actions_struct(actions):
            logger.debug("Action structure is wrong.")
            return False
        return True

    def _update_config_file(self, file_path):
        try:
            actions = yaml.safe_load(self.config["actions"])
        except yaml.YAMLError as e:
            logger.debug("Error parsing YAML file: %s", e)
            self.unit.status = ops.BlockedStatus("Invalid actions configuration")
            return

        # Check if actions is configured
        if actions is None:
            self.unit.status = ops.BlockedStatus("Actions not configured")
            return

        # Check if the configuration is valid
        if not self._valid_actions(actions):
            self.unit.status = ops.BlockedStatus("Invalid actions structure")
            return

        # Write the config file to disk
        self._write_config_file(file_path, self._render_config_file(actions))
        logger.debug("New actions configured")
        self.unit.status = ops.ActiveStatus("Actions configured")

    def _write_config_file(self, file_path, file_content):
        with open(file_path, encoding="utf-8", mode="w") as f:
            f.write(file_content)
        os.chmod(file_path, 0o644)

    def _render_config_file(self, actions):
        env = Environment(loader=FileSystemLoader(self.template_dir))
        template = env.get_template("charm-assistant-api.jinja")
        actions_yaml = yaml.dump(actions)

        return template.render(actions=actions_yaml)

    def _render_systemd_file(self):
        env = Environment(loader=FileSystemLoader(self.template_dir))
        template = env.get_template("systemd.jinja")

        return template.render(os.getenv("JUJU_CHARM_DIR"))


if __name__ == "__main__":  # pragma: nocover
    ops.main(CharmAssistantCharm)  # type: ignore
