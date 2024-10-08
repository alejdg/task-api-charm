#!/usr/bin/env python3
# Copyright 2024 Alexandre
# See LICENSE file for licensing details.

"""Charm the application."""

import logging
import os
from subprocess import check_call

import ops
import yaml
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)


class TaskAPICharm(ops.CharmBase):
    """Task API Charm."""

    CHARM_DIR = os.getenv("JUJU_CHARM_DIR")
    SERVICE_NAME = "task-api.service"
    CONFIG_FILE = "/etc/task-api.yaml"

    def __init__(self, *args):
        super().__init__(*args)
        self.framework.observe(self.on.install, self._on_install)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self.on.remove, self._on_remove)
        self.template_dir = os.path.join(self.CHARM_DIR, "templates")

    def _on_install(self, event: ops.InstallEvent):
        """Handle the install event."""
        # Initialize the config file
        self._update_config_file(self.CONFIG_FILE)
        # Install the service
        self._install_systemd()
        # Create the web server service
        if self._configured():
            self._open_ports()
            self.unit.status = ops.ActiveStatus("Ready")
        else:
            logger.info("Charm not configured")
            self.unit.status = ops.BlockedStatus("Charm not configured")

    def _on_config_changed(self, event: ops.ConfigChangedEvent):
        self._update_config_file(self.CONFIG_FILE)
        if self._configured():
            self._restart_service()
            self._open_ports()
            self.unit.status = ops.ActiveStatus("Ready")
        else:
            self.unit.status = ops.BlockedStatus("Charm not configured")

    def _on_remove(self, event: ops.RemoveEvent):
        """Handle the remove event."""
        self._remove_systemd()

    def _install_systemd(self):
        logger.info("Installing the api service")

        try:
            file_path = f"/etc/systemd/system/{self.SERVICE_NAME}"
            self._write_config_file(file_path, self._render_systemd_file())
            self._reload_systemctl()
            self._enable_service()
        except os.error as e:
            # If the command returns a non-zero return code,
            # put the charm in blocked state_install_systemd
            logger.debug("Setting up the api service failed with return code %d", e)
            self.unit.status = ops.BlockedStatus("Failed to install packages")

    def _remove_systemd(self):
        logger.info("Uninstalling the API service")

        try:
            self._disable_service()
            file_path = f"/etc/systemd/system/{self.SERVICE_NAME}"
            os.remove(file_path)
            self._reload_systemctl()
        except os.error as e:
            # If the command returns a non-zero return code,
            # put the charm in blocked state_install_systemd
            logger.debug("Uninstalling the API service failed with return code %d", e)
            self.unit.status = ops.BlockedStatus("Failed to uninstall packages")

    def _reload_systemctl(self):
        check_call(["sudo", "systemctl", "daemon-reload"])

    def _disable_service(self):
        check_call(["sudo", "systemctl", "stop", self.SERVICE_NAME])
        check_call(["sudo", "systemctl", "disable", self.SERVICE_NAME])

    def _enable_service(self):
        check_call(["sudo", "systemctl", "start", self.SERVICE_NAME])
        check_call(["sudo", "systemctl", "enable", self.SERVICE_NAME])

    def _restart_service(self):
        check_call(["sudo", "systemctl", "restart", self.SERVICE_NAME])

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
        """Validate the actions list."""
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
            self._write_config_file(file_path, "")
            self.unit.status = ops.BlockedStatus("Actions not configured")
            return

        # Check if the configuration is valid
        if not self._valid_actions(actions):
            self.unit.status = ops.BlockedStatus("Invalid actions structure")
            return

        auth_enabled = self.config["auth-enabled"]

        tokens = self.config["tokens"]

        if tokens is not None:
            try:
                tokens = yaml.safe_load(tokens)
            except yaml.YAMLError as e:
                logger.debug("Error parsing YAML file for tokens: %s", e)
                self.unit.status = ops.BlockedStatus("Invalid tokens configuration")
                return

            # Check if tokens is a valid dictionary
            if not isinstance(tokens, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in tokens.items()
            ):
                self.unit.status = ops.BlockedStatus("Invalid tokens structure")
                return

        port = self.config["port"]

        # Write the config file to disk
        self._write_config_file(
            file_path, self._render_config_file(actions, auth_enabled, tokens, port)
        )
        logger.info("New actions configured")
        self.unit.status = ops.ActiveStatus("Actions configured")

    def _write_config_file(self, file_path, file_content):
        with open(file_path, encoding="utf-8", mode="w") as f:
            f.write(file_content)
        os.chmod(file_path, 0o644)

    def _render_config_file(self, actions, auth_enabled, tokens, port):
        env = Environment(loader=FileSystemLoader(self.template_dir))
        template = env.get_template("task-api.jinja")

        config_data = {
            "port": port,
            "actions": yaml.dump(actions),
            "auth_enabled": auth_enabled,
            "tokens": tokens if tokens is not None else {},
        }

        return template.render(config_data)

    def _render_systemd_file(self):
        env = Environment(loader=FileSystemLoader(self.template_dir))
        template = env.get_template("systemd.jinja")
        context = {
            "charm_dir": self.CHARM_DIR,
        }

        return template.render(context)

    def _open_ports(self):
        try:
            self.unit.open_port("tcp", self.config["port"])
        except ops.model.ModelError:
            logger.exception("failed to open port")

    def _configured(self):
        """Check if the charm has been configured."""
        return not os.stat(self.CONFIG_FILE).st_size == 0


if __name__ == "__main__":  # pragma: nocover
    ops.main(TaskAPICharm)  # type: ignore
